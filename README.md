# clippers

Turn long videos and livestream recordings into short, captioned, vertical (9:16) clips
for TikTok, Reels and Shorts, with the highlight moments picked automatically.

- **Input:** a video file or any URL yt-dlp supports (YouTube, Twitch VODs, direct links, ...)
  (YouTube needs a JS runtime: Deno >= 2.3 or Node >= 22; the Docker image includes Deno)
- **Highlight detection:** loudness spikes, speech rate, reactions (English and Nigerian
  Pidgin), and optionally an AI model reading the transcript (OpenAI)
- **Output:** 1080×1920 MP4s with burned-in, word-by-word highlighted captions
  (faster-whisper), cut at sentence boundaries
- **Use it** from the command line, or as an HTTP service with a background job queue

## Command line

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/) and an ffmpeg built with libass
(on macOS: `brew install homebrew-ffmpeg/ffmpeg/ffmpeg`).

```bash
uv sync
uv run clippers auto "https://www.youtube.com/watch?v=..." -n 5        # detect + clip
uv run clippers auto video.mp4 -n 5 --ai                               # also ask the AI
uv run clippers detect video.mp4 -n 5        # just pick moments -> moments.json
uv run clippers batch output/video.moments.json   # render a (hand-edited) moments file
uv run clippers cut video.mp4 -s 1:23 -d 30  # one clip at a given time
uv run clippers --help
```

Settings go in a `.env` file (copy `.env.example`); never commit it.

## HTTP service

```bash
cp .env.example .env               # set OPENAI_API_KEY (for "ai": true) and CLIPPERS_API_KEY
docker compose up -d --build       # Redis + API + worker
open http://127.0.0.1:8000/docs    # interactive API docs
```

```bash
# submit a job (returns 202 immediately)
curl -X POST http://127.0.0.1:8000/jobs \
  -H 'Content-Type: application/json' -H "X-API-Key: $CLIPPERS_API_KEY" \
  -d '{"url": "https://www.youtube.com/watch?v=...", "count": 5, "ai": true}'

# poll it: state goes queued -> running (stage: downloading, transcribing, ...) -> done
curl -H "X-API-Key: $CLIPPERS_API_KEY" http://127.0.0.1:8000/jobs/<id>
# each clip in the response has a download "url"
```

| Endpoint | |
|---|---|
| `POST /jobs` | `{url, count?, duration?, framing?, captions?, language?, ai?}` → `202` + job |
| `GET /jobs/{id}` | `state`, `stage`, `error`, `clips[]` (title, reason, score, url) |
| `GET /jobs/{id}/clips/{filename}` | the MP4 |
| `GET /health` | liveness (no API key needed) |

Job URLs must be public http(s) addresses: localhost, private networks and cloud metadata
addresses are refused.

## Deploying to a server

Any Linux machine with Docker works (a VPS, or a cloud VM):

1. Copy the repo and a `.env` with **`CLIPPERS_API_KEY` set** (otherwise the API is open).
2. `docker compose up -d --build`
3. Put a reverse proxy with HTTPS in front of port 8000 (e.g. Caddy or nginx). The compose
   file binds the API to 127.0.0.1, so only the proxy can reach it.
4. **Block the worker from private networks** (cloud firewall / security group egress
   rules, or a container network policy). The app already refuses private URLs, but a
   public URL that *redirects* to a private address can only be stopped at the network.
5. Plan disk space: clips, downloads and caches live in the `data` volume.

Sizing: transcription is the slow part. On CPU, Whisper `small` runs at roughly 3-4×
real time on 4 cores, so a 1-hour stream takes ~15-20 min. `--scale worker=N` processes
N videos at once if the machine has the cores; a GPU machine is the big speed-up.

## Development

```bash
docker compose up -d redis                            # just Redis
uv run uvicorn --factory clippers.api:make_app --reload   # API on :8000
uv run arq clippers.worker.WorkerSettings             # worker
uv run ruff format . && uv run ruff check . && uv run pyright && uv run pytest
uv run pytest -m slow                                 # also the real-Whisper test
```
