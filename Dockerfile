# One image for both processes:
#   API:     uvicorn --factory clippers.api:make_app --host 0.0.0.0 --port 8000  (default)
#   worker:  arq clippers.worker.WorkerSettings
FROM python:3.12-slim-trixie

# System tools the pipeline shells out to:
# - ffmpeg: Debian's build includes libass, so burned-in captions work out of the box
# - fonts-liberation2: Liberation Sans is metric-compatible with Arial (what captions ask
#   for), so caption layout matches what we see on a Mac
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-liberation2 \
    && rm -rf /var/lib/apt/lists/*

# uv, pinned to the version the lockfile was made with.
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/uv

# Deno: yt-dlp's (default) JavaScript runtime, needed to download from YouTube. Not
# Debian's nodejs: it's Node 20 and yt-dlp requires Node >= 22 (or Deno >= 2.3), so with
# it YouTube downloads silently ran without a JS runtime. Fail the build if it's missing.
COPY --from=denoland/deno:bin-2.6.6 /deno /usr/local/bin/deno
RUN deno --version

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, in their own layer: it's only rebuilt when the lockfile changes,
# not on every code edit. (Same idea as copying package-lock.json before `npm ci`.)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Then the code itself.
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Never run as root. Everything the app writes goes under /data (mount a volume there):
# job outputs, downloads, cached transcripts and AI answers, Whisper model files.
RUN useradd --create-home --uid 10001 clippers \
    && mkdir -p /data \
    && chown clippers:clippers /data
USER clippers
ENV CLIPPERS_DATA_DIR=/data \
    CLIPPERS_CACHE_DIR=/data/cache \
    HF_HOME=/data/huggingface

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["uvicorn", "--factory", "clippers.api:make_app", "--host", "0.0.0.0", "--port", "8000"]
