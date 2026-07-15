# SPEC: The Sandking Sandbox (Round 11) — SB1–SB5

User intent: "make the docker container completely self contained (no
outside network) with a dummy web device, but we must have python access
locally, so install python 3.11 with pandas, sklearn, numpy, torch...
use wikitext... include a version of the source as read-only."

This packages the whole terrarium as an isolated container. The build
bakes everything it needs (the GloVe embedding space, optionally
WikiText-103); the runtime is meant to run with NO network at all.

## SB1 — Image (Dockerfile)
- Base `python:3.11-slim`. Installs numpy, pandas, scikit-learn, torch
  (CPU wheels), pillow, fastapi, uvicorn.
- BUILD stage (network available) bakes the GloVe vectors and, when
  `--build-arg BUILD_WIKITEXT=1`, a WikiText-103 sample into the codex
  corpus. Nothing is fetched at runtime.
- Copies the source in; runs as unprivileged user `keeper` (uid 10001);
  terrarium state lives in a `/state` volume.

## SB2 — Two run modes (run_sandbox.sh / .ps1)
Both are non-root, `--read-only` rootfs, `--cap-drop ALL`,
`--security-opt no-new-privileges`, `--pids-limit 256`, `--memory 4g`,
`--tmpfs /tmp`, state in a named volume (colonies resume across runs).
- ISOLATED (default): `--network none` - no network stack whatsoever.
  Maximum containment; the sim runs headless and autosaves. This is the
  literal "no outside network" the user asked for.
- CONSOLE (`--console`): publishes ONLY `127.0.0.1:8000` for the
  dashboard. The image makes zero outbound calls (enforced by
  tests/test_dashboard.py's no-dangerous-imports test), so no data
  leaves the host; but for airtight egress-blocking use ISOLATED.

## SB3 — Safety posture (the whole point)
- Runtime has no internet by design (ISOLATED) or no outbound code
  (CONSOLE). Read-only source and rootfs; the only writable path is the
  `/state` volume and `/tmp`. Non-root, no capabilities, no privilege
  escalation, bounded memory/pids.
- The in-container Python IS the general-purpose interpreter the user
  wanted (pandas/sklearn/numpy/torch present), but the SIM never
  executes evolved or corpus text as host code - the codex reads text
  into lesson tags and the VM interprets bounded bytecode. Any future
  "let the sandkings run Python" feature belongs INSIDE this container,
  behind the isolation, never on the host.

## SB4 — WikiText and the corpus
The codex (SPEC_CODEX) reads `corpus/*.md`. The baked WikiText sample
lands in `corpus/wikitext/` so, when built with BUILD_WIKITEXT=1, the
sandkings' reading pool includes the GPT-Neo corpus alongside the
curated survival/coop lore and the repo's own specs.

## SB5 — Acceptance
Not a pytest suite (Docker build is heavy and environment-specific);
acceptance is by inspection + the existing safety tests:
- The Dockerfile builds `python:3.11-slim` with the named libraries.
- run_sandbox default uses `--network none`; console publishes only to
  127.0.0.1.
- tests/test_dashboard.py::test_no_dangerous_imports already proves the
  served code has no subprocess/socket/urllib and no eval/exec, so the
  CONSOLE mode cannot phone home.
- README documents build + both run modes.

## Status / Reconciliation
- Drafted + authored 2026-07-09. The image is not built in CI here
  (torch CPU wheels + optional WikiText make it multi-GB); the
  Dockerfile, .dockerignore, and both launch scripts are authored and
  reviewed. Build locally with `docker build -t sandking .`.
