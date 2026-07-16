# The Sandking Sandbox (SPEC_SANDBOX.md) — a self-contained terrarium.
#
# 100% LOCAL: the GloVe embedding space and the WikiText corpus are
# downloaded ONCE on the host and baked into the image by COPY - the
# build performs NO data downloads (only pip from PyPI). The runtime is
# meant to run with NO network at all (`docker run --network none ...`),
# non-root, read-only source.
#
#   # one-time host prep (fetches the pieces locally):
#   ./prepare_corpus.sh
#   docker build -t sandking .
#
# See run_sandbox.sh / run_sandbox.ps1 for hardened launch.

FROM python:3.11-slim
WORKDIR /opt/sandking

# libgomp1 is the only system lib torch needs at runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# The useful libraries (the user asked for these): torch from the CPU
# wheel index (that index serves only torch), the rest from PyPI. pyarrow
# lets pandas read parquet; TabPFM can be added here as a drop-in
# regression backend (telemetry.REGRESSION_BACKENDS).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir \
        numpy pandas scikit-learn pyarrow pillow \
        "fastapi==0.115.14" "uvicorn==0.44.0" httpx pygame tqdm matplotlib

# the game + the pre-fetched local data (GloVe .gz and corpus/wikitext/
# must exist on the host - run ./prepare_corpus.sh first). COPY bakes
# them; nothing is fetched at build time.
COPY . /opt/sandking

# fail loudly at build if the local pieces are missing, so a broken image
# is never shipped silently
RUN test -f glove-wiki-gigaword-50.gz \
      || (echo "MISSING glove-wiki-gigaword-50.gz - run ./prepare_corpus.sh" && exit 1)

# a dedicated unprivileged user; the terrarium state lives in a volume
RUN useradd -m -u 10001 keeper && mkdir -p /state && chown keeper /state
USER keeper
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 SANDKING_STATE=/state

# default: run the sim headless, autosaving to the mounted /state volume.
# (The web console is opt-in via run_sandbox --console.)
CMD ["python", "sim/sandkings.py", "--persist", "/state/terrarium.db"]
