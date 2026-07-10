#!/usr/bin/env bash
# One-time host prep: fetch the corpus pieces LOCALLY so `docker build`
# performs no data downloads (SPEC_SANDBOX SB4, 100%-local build).
# Idempotent: skips anything already present.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f glove-wiki-gigaword-50.gz ]; then
  echo "[prepare] GloVe wiki-gigaword-50 (~66MB)..."
  curl -fsSL -o glove-wiki-gigaword-50.gz \
    https://github.com/piskvorky/gensim-data/releases/download/glove-wiki-gigaword-50/glove-wiki-gigaword-50.gz
fi

if [ ! -f corpus/wikitext/wikitext103_sample.md ]; then
  echo "[prepare] WikiText-103 (public HF parquet) -> corpus/wikitext/..."
  mkdir -p corpus/wikitext
  # public dataset; no HF token required. Set HF_TOKEN to use a mirror
  # behind auth if you prefer.
  auth=()
  [ -n "${HF_TOKEN:-}" ] && auth=(-H "Authorization: Bearer ${HF_TOKEN}")
  curl -fsSL "${auth[@]}" -o _wt.parquet \
    "https://huggingface.co/datasets/Salesforce/wikitext/resolve/main/wikitext-103-raw-v1/train-00000-of-00002.parquet"
  python -c "import pandas as pd; df=pd.read_parquet('_wt.parquet',columns=['text']); open('corpus/wikitext/wikitext103_sample.md','w',encoding='utf-8').write(chr(10).join(df['text'].astype(str).tolist())[:6000000])"
  rm -f _wt.parquet
fi

echo "[prepare] corpus ready: $(ls -la glove-wiki-gigaword-50.gz corpus/wikitext/ | wc -l) items."
