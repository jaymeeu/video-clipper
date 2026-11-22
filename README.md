# clippers

Turn long videos and livestream recordings into short, **vertical (9:16), captioned clips**
for TikTok, Instagram Reels and YouTube Shorts, with the best moments **picked
automatically**.

Give it a video file or a link. It finds the moments that stand out (loud reactions, fast
excited talk, laughter, hype words in English and Nigerian Pidgin, and optionally an AI
model's judgement), cuts them at sentence boundaries, reframes them for phones, and burns in
TikTok-style captions where each word lights up as it's spoken.

Use it three ways:
- **Web app**: the team pastes a link, watches progress, previews the clips and
  downloads the good ones (password-protected).
- **Command line**: `clippers auto VIDEO` on your own machine.
- **HTTP API**: another backend (for example a Node.js app) submits a URL, polls the job
  and downloads the clips.

---

## Contents

1. [What you get](#what-you-get)
2. [How it works](#how-it-works)
3. [Quick start (command line)](#quick-start-command-line)
4. [Command reference](#command-reference)
5. [The moments file](#the-moments-file)
6. [Settings (.env)](#settings-env)
7. [The web app](#the-web-app)
8. [The HTTP service](#the-http-service)
9. [Calling it from Node.js](#calling-it-from-nodejs)
10. [Running with Docker](#running-with-docker)
11. [Deploying to a server (DigitalOcean)](#deploying-to-a-server-digitalocean)
12. [Project layout](#project-layout)
13. [Development](#development)
14. [Troubleshooting](#troubleshooting)
15. [Limitations and roadmap](#limitations-and-roadmap)

---

## What you get

Each clip is an MP4 that's ready to upload:

- **1080×1920 (9:16)**, H.264 + AAC, `yuv420p` (plays on every phone), `+faststart`
- **Framing:**
  - `blur` (default): the video sits in the middle, filling at least 3/5 of the
    height (landscape video is zoomed in and its sides trimmed), over a blurred copy of
    itself. Vertical phone streams fill the whole screen.
  - `crop`: fills the frame and cuts off the sides.
  - `original`: keeps the source shape (no captions in this mode).
- **Captions:** short 1–3 word chunks, bold white text with an outline, and the word
  being spoken highlighted in yellow
- **Smart edges:** clips start and end at sentence breaks instead of cutting someone
  off mid-word
- **A name and a reason for each clip**, for example
  `01-admit-you-re-freaked-out-cecilia.mp4` with
  *"AI 8/10: builds from sincere talk into a hilarious confrontation…"*

## How it works

```
video file or URL
      │
      ▼
 1. download        yt-dlp: YouTube, Twitch VODs, direct .mp4 links, 1000+ sites
      │             (≤1080p, H.264/AAC preferred; cached, so a URL downloads once)
      ▼
 2. transcribe      faster-whisper: words with exact timestamps (cached per video)
      │
      ▼
 3. score          each second of the video gets a score from up to four signals:
      │              • loudness     how much louder than the surrounding two minutes
      │              • speech       talking faster than usual
      │              • reactions    "omo", "chai", "no way", "let's go", laughter, "!"
      │              • AI (opt-in)  an OpenAI model reads the transcript and picks moments
      ▼
 4. pick moments    best-scoring windows, no overlaps, edges moved to sentence breaks,
      │             AI moment boundaries and titles used where they fit
      ▼
 5. render          ffmpeg: cut → 9:16 framing → burned-in captions → MP4
```

Detection writes a **moments file** (`moments.json`) between steps 4 and 5. You can edit
it by hand and re-render, or skip detection entirely and write one yourself.

## Quick start (command line)

### 1. Install the requirements

| Tool | Why | Install |
|---|---|---|
| Python 3.12+ | the program | via uv (below) |
| [uv](https://docs.astral.sh/uv/) | Python package manager (like npm) | `brew install uv` or see uv docs |
| **ffmpeg with libass** | cutting, reframing, captions | see below |
| Deno ≥ 2.3 **or** Node ≥ 22 | needed by yt-dlp for YouTube only | `brew install deno` |

**ffmpeg must include libass** (the subtitle renderer), or captions won't work:

```bash
ffmpeg -hide_banner -filters | grep subtitles    # must print a "subtitles" line
```

- **Linux (Debian/Ubuntu):** `sudo apt install ffmpeg` already includes it.
- **macOS:** Homebrew's standard `ffmpeg` does *not*. Use the full build instead:
  ```bash
  brew uninstall ffmpeg
  brew tap homebrew-ffmpeg/ffmpeg
  brew install homebrew-ffmpeg/ffmpeg/ffmpeg
  ```
  (On Intel Macs this compiles from source and can take a long time.)

### 2. Get the code and install

```bash
git clone https://github.com/jaymeeu/video-clipper.git
cd video-clipper
uv sync                       # creates .venv and installs everything (like npm install)
cp .env.example .env          # optional: add OPENAI_API_KEY for AI scoring
```

### 3. Make clips

```bash
# Find the 5 best moments and render them, in one go:
uv run clippers auto "https://www.youtube.com/watch?v=..." -n 5

# Same, from a local file, with AI scoring and English captions:
uv run clippers auto ~/Videos/stream.mp4 -n 5 --ai -l en
```

The clips land in `output/<video name>/`, next to the `moments.json` that produced them.

> **First run:** the Whisper speech model (~480 MB for `small`) downloads once and is
> cached. Transcription is the slow step: on a 4-core laptop CPU, expect roughly 3–4×
> real time (a 1-hour stream ≈ 15–20 minutes). Results are cached, so running again on
> the same video is fast.

## Command reference

Run `uv run clippers --help` or `uv run clippers <command> --help` for full details.
Put `-v` **before** the command for debug output: `uv run clippers -v auto ...`.

### `auto`: find the best moments and render them

```bash
uv run clippers auto VIDEO [options]
```

| Option | Default | Meaning |
|---|---|---|
| `-n, --count` | 5 | how many clips (fewer if nothing else stands out) |
| `-d, --duration` | 30 | typical clip length in seconds (AI moments may differ) |
| `-o, --output-dir` | `output/<video>/` | where clips and `moments.json` go |
| `-f, --framing` | `blur` | `blur`, `crop` or `original` |
| `--captions / --no-captions` | on | burn in captions |
| `--transcript / --no-transcript` | on | use speech + reactions (needs transcription) |
| `-m, --model` | `small` | Whisper model: `tiny`, `base`, `small`, `medium`, `large-v3`, `turbo` |
| `-l, --language` | auto-detect | spoken language code, e.g. `en` |
| `--ai / --no-ai` | off | also ask OpenAI (needs `OPENAI_API_KEY`, costs a little) |
| `--ai-model` | `gpt-5-mini` | which OpenAI model |

### `detect`: just pick the moments

Writes a moments file without rendering anything, so you can review or edit it first.

```bash
uv run clippers detect VIDEO -n 5 --ai          # → output/<video>.moments.json
```

### `batch`: render a moments file

```bash
uv run clippers batch output/stream.moments.json -l en
```

If one clip fails, the others still render, and the command exits with code 1 and lists
the failures.

### `cut`: one clip at a time you choose

```bash
uv run clippers cut VIDEO -s 1:23 -d 30 -o output/clip.mp4
```

`-s` accepts `83`, `1:23` or `1:01:23`.

### `download`: fetch a video without clipping it

```bash
uv run clippers download "https://..."           # → downloads/
```

**Output conventions:** finished file paths go to *stdout* and progress goes to *stderr*,
so scripts can capture results, e.g. `clip=$(uv run clippers cut ...)`. Bad arguments
exit with code 2, failures with code 1.

**Which Whisper model?** `tiny`/`base` are much faster but make more caption mistakes;
`small` (default) is a good balance; `medium`/`large-v3` are the most accurate and the
slowest on CPU.

## The moments file

A JSON list of moments to clip. `detect` writes one, `auto` saves one next to the clips,
and you can write or edit one by hand:

```json
{
  "source": "https://www.youtube.com/watch?v=...",
  "framing": "blur",
  "captions": true,
  "moments": [
    {"start": "1:23", "duration": 30, "title": "The big reveal"},
    {"start": 250, "duration": 20}
  ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `source` | yes | URL, or a file path (relative paths are relative to the JSON file) |
| `moments[].start` | yes | seconds (`250`) or a timestamp (`"4:10"`) |
| `moments[].duration` | no (30) | clip length in seconds, up to 600 |
| `moments[].title` | no | used for the file name: `01-the-big-reveal.mp4` |
| `moments[].score`, `reason` | no | filled in by `detect` (why it was picked) |
| `framing` | no (`blur`) | `blur`, `crop` or `original` |
| `captions` | no (true) | burn in captions |

Typos are caught: an unknown field like `"strat"` is an error, and every problem in the
file is reported at once with its location (`moments[1].start: invalid timestamp`).

## Settings (`.env`)

Copy `.env.example` to `.env` and set what you need. `.env` is gitignored and must never
be committed. Real environment variables take precedence over the file.

| Variable | Default | Used by | Meaning |
|---|---|---|---|
| `OPENAI_API_KEY` | none | AI scoring | your OpenAI key (only needed for `--ai` / `"ai": true`) |
| `CLIPPERS_AI_MODEL` | `gpt-5-mini` | AI scoring | OpenAI model to use |
| `CLIPPERS_API_KEY` | none | HTTP service | clients must send it as `X-API-Key`. **Always set this on a server** |
| `CLIPPERS_REDIS_URL` | `redis://localhost:6379` | HTTP service | the job queue (compose sets it for you) |
| `CLIPPERS_DATA_DIR` | `data` | HTTP service | job outputs and downloads (`/data` in Docker) |
| `CLIPPERS_RETENTION_DAYS` | `7` | HTTP service | how long jobs, downloads and caches are kept |
| `CLIPPERS_CACHE_DIR` | `~/.cache/clippers` | everything | cached transcripts and AI answers |
| `CLIPPERS_WEB_PASSWORD` | none (**required**) | web app | the team's login password; the web container won't start without it |
| `CLIPPERS_WEB_USER` | `team` | web app | the team's login user name |
| `CLIPPERS_API_URL` | `http://127.0.0.1:8000` | web dev server | where `npm run dev` sends `/api` requests |

**Cost of AI scoring:** one request per video (long streams are split into a few), well
under a cent per video with `gpt-5-mini` in our tests. Answers are cached, so re-running
on the same video costs nothing.

## The web app

A React app for the team, in [`web/`](web/). Three screens:

| Screen | What you do there |
|---|---|
| **Jobs** (`/`) | every video sent for clipping, newest first, with live status |
| **New clips** (`/new`) | paste a link; pick how many clips, length, framing, language, captions, AI |
| **Job** (`/jobs/:id`) | live progress through each step, then the clips: play them inline (one at a time), see *why* each was picked, download |

Run it with everything else:

```bash
# in .env: CLIPPERS_WEB_PASSWORD=<choose one>   (CLIPPERS_WEB_USER defaults to "team")
docker compose up -d --build
open http://127.0.0.1:8080        # log in with team / your password
```

How it's put together:

```
browser ──▶ web container (Caddy) ──/api/*──▶ API ──▶ worker
            • asks for the team login
            • serves the built React app
            • adds X-API-Key itself: the key never reaches the browser
```

- **Stack:** Vite, React 19, TypeScript, TanStack Query (polling that stops when jobs
  finish), React Router, Tailwind CSS.
- **Typed API calls:** TypeScript types are generated from the API's OpenAPI schema
  (`web/openapi.json`). After changing the API's models, run `npm run gen:api` in `web/`;
  a Python test fails if you forget.
- **No API key in the browser:** the app only calls `/api/...` on its own address; Caddy
  (production) or Vite (development) adds the key on the way to the API.

### Working on the web app

```bash
docker compose up -d redis api worker   # or run the API/worker with uv (see Development)
cd web
npm install
npm run dev            # http://localhost:5173, hot reload; /api goes to http://127.0.0.1:8000
npm test               # Vitest + Testing Library (fake API, no backend needed)
npm run typecheck && npm run build
npm run gen:api        # after changing the API's models
```

## The HTTP service

Three processes work together:

```
your backend ──POST /jobs──▶  API (FastAPI)  ──queue──▶  Redis  ──▶  worker (arq)
             ◀── 202 + id ──      │                                    │
             ──GET /jobs/id──▶    │ reads job status          downloads, transcribes,
             ◀── status, clips ───┘                           scores and renders; stores
             ──GET clip url──▶  the MP4                       clips in the data folder
```

Long videos never block a request: `POST /jobs` returns immediately and the worker does
the work in the background.

### Endpoints

All endpoints except `/health` need the header `X-API-Key: <CLIPPERS_API_KEY>` when a key
is set. Interactive docs are at **`/docs`** (try requests in the browser).

| Method & path | What it does |
|---|---|
| `POST /jobs` | queue a video. Returns **202** with the job and a `Location` header |
| `GET /jobs/{id}` | job status and, when done, the clips with download URLs |
| `GET /jobs/{id}/clips/{filename}` | download one clip (`video/mp4`) |
| `GET /health` | `{"status": "ok"}`; no key needed (for uptime checks) |

### `POST /jobs` body

| Field | Default | Limits | Meaning |
|---|---|---|---|
| `url` | (required) | public http(s) only | the video: a direct file link or a platform page |
| `count` | 5 | 1–20 | how many clips |
| `duration` | 30 | 5–180 | typical clip length (s) |
| `framing` | `"blur"` | `blur`/`crop`/`original` | |
| `captions` | `true` | | burn in captions |
| `language` | auto | e.g. `"en"` | spoken language |
| `ai` | `false` | | also score with OpenAI (needs `OPENAI_API_KEY` on the server) |

Unknown fields are rejected (`422`). For safety, URLs pointing at `localhost`, private
networks or cloud metadata addresses are refused (`422`), and local file paths are never
accepted.

### Job lifecycle

`state` goes `queued` → `running` → `done` (or `failed`). While running, `stage` shows
progress: `starting`, `downloading`, `transcribing`, `asking AI`, `detecting`, `rendering`.

```json
{
  "id": "5d37cd9650374b369021d49c0a789d8a",
  "state": "done",
  "stage": null,
  "error": null,
  "failed_clips": 0,
  "clips": [
    {
      "filename": "01-you-forgot-me-on-earth.mp4",
      "start": 378.84,
      "duration": 43.46,
      "title": "You Forgot Me On Earth!",
      "reason": "AI 8/10 \"You Forgot Me On Earth!\": High-emotion betrayal ...",
      "score": 3.2,
      "url": "http://127.0.0.1:8000/jobs/5d37.../clips/01-you-forgot-me-on-earth.mp4"
    }
  ]
}
```

- `failed`: `error` says why (e.g. `could not download ...: HTTP 404`).
- `done` with `failed_clips > 0`: some clips rendered, some didn't.
- Jobs and their clips are kept for `CLIPPERS_RETENTION_DAYS` (default 7), then deleted
  automatically (cleanup runs hourly). **Copy clips somewhere permanent if you need them
  longer.**

## Calling it from Node.js

```js
const CLIPPER = process.env.CLIPPER_URL;          // e.g. http://10.0.0.5:8000
const headers = {
  "Content-Type": "application/json",
  "X-API-Key": process.env.CLIPPERS_API_KEY,
};

export async function createClips(videoUrl) {
  // 1. Submit: returns immediately with a job id.
  const res = await fetch(`${CLIPPER}/jobs`, {
    method: "POST",
    headers,
    body: JSON.stringify({ url: videoUrl, count: 5, ai: true }),
  });
  if (res.status !== 202) throw new Error(`clipper refused job: ${await res.text()}`);
  const { id } = await res.json();

  // 2. Poll until done (a queue/webhook in your app works too).
  while (true) {
    await new Promise((r) => setTimeout(r, 10_000));
    const job = await (await fetch(`${CLIPPER}/jobs/${id}`, { headers })).json();
    if (job.state === "done") return job.clips;  // [{ title, reason, url, ... }]
    if (job.state === "failed") throw new Error(job.error);
  }
}

// 3. Download each clip.url (send the same X-API-Key header) and store it in your own
//    storage (S3, R2, ...): the clipper deletes it after the retention period.
```

## Running with Docker

The easiest way to run the whole service (Redis + API + worker + web app) on any machine:

```bash
cp .env.example .env          # set CLIPPERS_WEB_PASSWORD, CLIPPERS_API_KEY (+ OPENAI_API_KEY for AI)
docker compose up -d --build  # build and start everything
open http://127.0.0.1:8080        # the web app (team login)
open http://127.0.0.1:8000/docs   # the API's interactive docs
```

| Command | |
|---|---|
| `docker compose ps` | what's running |
| `docker compose logs -f worker` | watch jobs being processed |
| `docker compose up -d --build` | rebuild and restart after pulling new code |
| `docker compose up -d --scale worker=2` | process two videos at once (needs the cores) |
| `docker compose down` | stop (data is kept in Docker volumes) |
| `docker compose up -d redis` | only Redis, to run the API/worker with `uv` during development |

**What's in the image:** Python 3.12, ffmpeg (with libass), Deno (for YouTube), and an
Arial-compatible font for captions. It runs as a non-root user, and all state (clips,
downloads, caches, Whisper models) lives in the `data` volume at `/data`. Secrets come
from `.env` when the containers start and are never baked into the image.

The web app, API and Redis are bound to `127.0.0.1`, so they aren't reachable from other
machines until you deliberately put something in front (next section).

## Deploying to a server (DigitalOcean)

One Linux server running the Docker setup above is the recommended starting point. Any
provider works; these steps use a DigitalOcean Droplet with Ubuntu.

### 1. Choose a size

| Droplet (Basic) | Approx. price | Good for |
|---|---|---|
| 2 vCPU / 4 GB / 80 GB | ~$24/month | trying it out, a few videos a day (one at a time) |
| 4 vCPU / 8 GB / 160 GB | ~$48/month | regular use; room for two workers |

Smaller Droplets (≤ 2 GB RAM) are not enough for Whisper + ffmpeg. Check
[current pricing](https://www.digitalocean.com/pricing/droplets) before buying. Put the
Droplet **in the same region as your other servers and video storage**: downloads are
faster, and your backend can reach the clipper over the private network.

### 2. Install Docker and get the code

SSH in (`ssh root@<droplet-ip>`), then:

```bash
curl -fsSL https://get.docker.com | sh            # Docker Engine + compose plugin
git clone https://github.com/jaymeeu/video-clipper.git /opt/clippers
cd /opt/clippers
cp .env.example .env
nano .env       # set CLIPPERS_WEB_PASSWORD, CLIPPERS_API_KEY (openssl rand -hex 32),
                # and OPENAI_API_KEY if you want AI picks
docker compose up -d --build
curl http://127.0.0.1:8000/health                 # → {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080   # → 401 (login required)
```

### 3. Firewall: only SSH and HTTPS in

```bash
ufw allow OpenSSH
ufw allow 80,443/tcp
ufw enable
```

(The web app and API are published on `127.0.0.1` only, so they aren't exposed even
though Docker bypasses `ufw` for published ports.)

### 4. Block the worker from private networks

The app already refuses job URLs that point at private addresses. A public URL that
*redirects* to a private one can only be stopped at the network level. These rules stop
**containers** from opening new connections to the cloud metadata service and to private
networks, while replies to normal traffic still work:

```bash
iptables -I DOCKER-USER 1 -m conntrack --ctstate NEW -d 169.254.0.0/16 -j DROP
iptables -I DOCKER-USER 1 -m conntrack --ctstate NEW -d 10.0.0.0/8 -j DROP
iptables -I DOCKER-USER 1 -m conntrack --ctstate NEW -d 192.168.0.0/16 -j DROP
apt install -y iptables-persistent && netfilter-persistent save   # keep after reboot
```

Check it works (the first should fail, the job queue must still work):

```bash
docker compose exec worker python -c "import urllib.request; urllib.request.urlopen('http://169.254.169.254', timeout=3)"
curl -s http://127.0.0.1:8000/health
```

(`172.16.0.0/12` is left open on purpose: Docker's own networks use it, and the worker
needs Redis.)

### 5. Give the team HTTPS access to the web app

Point a domain (e.g. `clips.example.com`) at the Droplet and put
[Caddy](https://caddyserver.com) (automatic HTTPS certificates) in front of the web app:

```bash
apt install -y caddy
printf 'clips.example.com {\n    reverse_proxy 127.0.0.1:8080\n}\n' > /etc/caddy/Caddyfile
systemctl reload caddy
```

Open `https://clips.example.com` and log in with `CLIPPERS_WEB_USER` / `CLIPPERS_WEB_PASSWORD`.
The API is reachable *through* the web app (at `/api`, behind the same login), so it doesn't
need its own public address.

**If another backend should call the API directly** (e.g. your Node.js app): best over the
private network. Change the API's port in `compose.yaml` from `"127.0.0.1:8000:8000"` to
`"<droplet-private-ip>:8000:8000"`, run `docker compose up -d`, and call
`http://<droplet-private-ip>:8000` with the `X-API-Key` header. **Keep `CLIPPERS_API_KEY`
set.**

### 6. Day-to-day

```bash
cd /opt/clippers
git pull && docker compose up -d --build   # deploy a new version
docker compose logs -f worker              # watch jobs
docker system df                           # disk usage (cleanup runs hourly)
```

Jobs queued while the worker restarts are kept in Redis and processed when it's back.

## Project layout

```
src/clippers/
  cli.py          command-line interface (typer): auto, detect, batch, cut, download
  autoclip.py     the whole pipeline as library functions (used by the CLI and the worker)
  ingest.py       downloading via yt-dlp
  transcribe.py   faster-whisper wrapper + Transcript/Word models + transcript cache
  audio.py        per-second loudness, streamed from ffmpeg
  signals.py      loudness / speech / reactions / AI signals on a common scale
  highlights.py   picking the best non-overlapping windows (pure numpy)
  boundaries.py   snapping clip edges to sentence breaks
  ai.py           OpenAI scoring (structured output, chunking, caching)
  detect.py       signals + picking + refining → a MomentsFile
  moments.py      the moments file format (pydantic) and its validation messages
  batch.py        rendering every moment, file naming, per-clip error handling
  pipeline.py     one clip: cut → frame → captions
  framing.py      9:16 ffmpeg filter graphs (blur / crop)
  captions.py     word-highlighted ASS subtitles
  video.py        ffmpeg / ffprobe wrappers
  api.py          HTTP API (FastAPI)
  jobs.py         job model, Redis job store, running a job
  worker.py       background worker (arq) + hourly cleanup schedule
  cleanup.py      deleting expired jobs, old downloads and caches
  netguard.py     refusing URLs that point into private networks
  cache.py        small on-disk JSON cache (atomic writes)
tests/            pytest suite (no network, no real API keys needed)
web/              the team web app (React + TypeScript)
  src/pages/        Jobs, New clips, Job screens
  src/components/   clip card, progress steps, shared UI
  src/api/          typed API client (schema.d.ts is generated from openapi.json)
  Caddyfile         login + /api proxy for the production container
Dockerfile, compose.yaml, .env.example
```

## Development

```bash
uv sync                                   # install, including dev tools
docker compose up -d redis                # Redis for the API/worker
uv run uvicorn --factory clippers.api:make_app --reload    # API on :8000
uv run arq clippers.worker.WorkerSettings                  # worker (another terminal)
```

Checks (run all before committing):

```bash
uv run ruff format . && uv run ruff check . && uv run pyright && uv run pytest
uv run pytest -m slow        # also runs real Whisper on synthesized speech (macOS `say`)
```

- **ruff** formats and lints, **pyright** type-checks (strict for `src/`), **pytest**
  runs ~270 tests in under a minute.
- Tests never touch the network, your `.env`, your API keys or your real cache: a shared
  fixture isolates every test (fake DNS, temp folders, OpenAI pointed at a dead address).
- Media tests generate their own videos with ffmpeg; tests that need ffmpeg or libass
  skip themselves when they're missing.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ffmpeg failed: ... No such filter: 'subtitles'` | your ffmpeg lacks libass. See [install](#1-install-the-requirements) |
| `burned-in captions need vertical framing` | `-f original` can't have captions: use `blur`/`crop`, or add `--no-captions` |
| YouTube: *"No supported JavaScript runtime"* | install Deno ≥ 2.3 (or Node ≥ 22). The Docker image includes Deno |
| YouTube: *"Sign in to confirm you're not a bot"* | YouTube often blocks cloud servers. Direct video links (your own storage/CDN) aren't affected |
| Downloads suddenly fail on a site | update yt-dlp: `uv lock --upgrade-package yt-dlp && uv sync` (rebuild the Docker image after) |
| `OPENAI_API_KEY is not set` | add it to `.env`, or run without `--ai` |
| `no moment stood out` | the video is silent or evenly loud; try `--ai`, or write a moments file by hand |
| First run is slow | the Whisper model (~480 MB) downloads once; later runs use the cache |
| `uv sync` fails on an Intel Mac | `pyproject.toml` pins versions that still ship Intel-Mac wheels (`[tool.uv]` section) |
| API returns `401` | send `X-API-Key` matching `CLIPPERS_API_KEY` |
| Web container exits: *Set CLIPPERS_WEB_PASSWORD* | add `CLIPPERS_WEB_PASSWORD=...` to `.env`, then `docker compose up -d` |
| Web login keeps failing | a `$` in the password gets mangled by docker compose: avoid it or single-quote the value |
| Web app shows *"The API rejected our API key"* | `CLIPPERS_API_KEY` must be the same for the `api` and `web` services (both read `.env`) |
| Job `422`: *points to a private or reserved network address* | the URL resolves to localhost/private network; use a public URL |

## Limitations and roadmap

- **Transcription is CPU-only and is the slow step.** A GPU worker would be many
  times faster; for now choose a smaller Whisper model if speed matters.
- **`crop` framing doesn't follow faces yet**: off-centre speakers can be cut off.
  Speaker/face tracking is planned.
- **Pidgin accuracy needs real-world tuning.** The reaction word list, signal weights
  and caption accuracy should be checked against real ClapMi streams.
- **Clips are stored on the server's disk** and deleted after the retention period.
  Uploading them to object storage (S3/R2) is the next step for multi-server setups.
- **Planned:** ClapMi chat and gift-event signals, faster near-real-time processing of
  live streams.
