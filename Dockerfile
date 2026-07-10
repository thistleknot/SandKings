# The Sandking Sandbox (SPEC_SANDBOX.md) — a self-contained terrarium.
#
# Two-stage: the BUILD stage has network (to bake GloVe + optionally
# WikiText-103 into the image); the RUNTIME is meant to be launched with
# NO network (`docker run --network none ...`), non-root, read-only
# source. Nothing inside ever needs the internet - the corpus is baked.
#
#   docker build -t sandking .
#   # optional: bake WikiText-103 (the GPT-Neo corpus, ~181MB):
#   docker build --build-arg BUILD_WIKITEXT=1 -t sandking .
#
# See run_sandbox.sh / run_sandbox.ps1 for hardened launch.

FROM python:3.11-slim AS build
WORKDIR /opt/sandking

# system libs torch/pillow need, then the Python stack the user asked for
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl unzip libgomp1 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        numpy==2.2.6 pandas==2.2.3 scikit-learn==1.5.2 \
        torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir \
        pillow==10.4.0 fastapi==0.115.14 uvicorn==0.44.0

# the game itself (source copy; the runtime mounts it read-only too)
COPY . /opt/sandking

# bake the shared embedding space (GloVe wiki-gigaword-50, ~66MB). Done
# AFTER the COPY so the build context (which .dockerignore's the .gz) can
# never clobber it.
RUN curl -fsSL -o glove-wiki-gigaword-50.gz \
    https://github.com/piskvorky/gensim-data/releases/download/glove-wiki-gigaword-50/glove-wiki-gigaword-50.gz

# optionally bake WikiText-103 (the corpus GPT-Neo trained on) into the
# codex corpus dir - AFTER the COPY, so it survives; the codex reads
# corpus/**/*.md recursively (SB4). Opt-in to keep the default image lean.
ARG BUILD_WIKITEXT=0
RUN if [ "$BUILD_WIKITEXT" = "1" ]; then \
        curl -fsSL -o /tmp/wt.zip \
          https://s3.amazonaws.com/research.metamind.io/wikitext/wikitext-103-v1.zip \
        && unzip -q /tmp/wt.zip -d /tmp \
        && mkdir -p corpus/wikitext \
        && head -c 6000000 /tmp/wikitext-103/wiki.valid.tokens \
             > corpus/wikitext/wikitext103_sample.md \
        && rm -rf /tmp/wt.zip /tmp/wikitext-103 ; \
    fi

# a dedicated unprivileged user; the terrarium state lives in a volume
RUN useradd -m -u 10001 keeper && mkdir -p /state && chown keeper /state
USER keeper
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 SANDKING_STATE=/state

# default: run the sim headless, autosaving to the mounted /state volume.
# (The web console is opt-in via run_sandbox --console; under
# `--network none` it is reachable only through `docker exec`.)
CMD ["python", "sandkings.py", "--persist", "/state/terrarium.db"]
