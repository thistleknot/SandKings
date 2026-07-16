# SPEC_LAYOUT — repository layout contract (hygiene 3/3)

## Purpose

The repo root had accumulated ~27 loose simulation modules. This spec fixes the
directory contract so the root stays navigable: entrypoints and packaging at
root, simulation code in `sim/`, everything else in its existing home.

## Layout (Structural)

| Location | Owns | Examples |
|---|---|---|
| `/` (root) | Entrypoints, packaging, top-level docs only | `run_tests.py`, `run_sandbox.sh/.ps1`, `prepare_corpus.sh`, `Dockerfile`, `requirements.txt`, `README.md`, `CHANGELOG.md`, `INSPIRATIONS.md`, `objective.md`, `progress.md`, `LICENSE` |
| `sim/` | All simulation runtime modules + their tracked data artifacts | `sandkings.py`, `politics.py`, `tech.py`, `neural_hive.py`, `dashboard.py`, `thought_vocabulary.json`, playtest harnesses, legacy `1pageskirmish.py` / `sandkings_gpu.py` |
| `src/` | Upstream DRQ corewar code (SakanaAI fork) — untouched | `drq.py`, `corewar/` |
| `tests/` | Test battery | `test_*.py` |
| `tools/` | Offline utilities | `fit_learned_basis.py`, `measure_objective.py` |
| `docs/` | Docs; specs in `docs/specs/` | `SPEC_*.md` |
| `corpus/` | Downloaded corpus (gitignored contents) | wikitext sample |

## Import contract (Behavioral)

- `sim/` is a plain script directory, NOT a package: modules keep importing
  each other flat (`import politics`). No `__init__.py`, no import rewrites.
- Every entrypoint that imports sim modules MUST put `sim/` on `sys.path`:
  - `run_tests.py` and each `tests/test_*.py` insert `<root>/sim`.
  - `tools/*.py` insert `<root>/sim`.
  - Direct runs (`python sim/sandkings.py`) work because Python puts the
    script's own directory on `sys.path`.

## Root-relative artifacts (Behavioral)

Modules in `sim/` that reference files OUTSIDE `sim/` resolve them via the
PARENT of their own directory (`dirname(dirname(__file__))`), never via cwd:

- `codex.py` — `glove-wiki-gigaword-50.gz`, `corpus/`, `docs/specs/` (root)
- `thought_vocabulary.py` — GloVe cache `glove-wiki-gigaword-50.gz` (root);
  `thought_vocabulary.json` stays module-relative (it lives in `sim/`)
- `neural_hive.py` — `learned_basis.npz` at root (where
  `tools/fit_learned_basis.py` writes it)

## Acceptance criteria

1. `python run_tests.py` passes the full battery (same pass count as before
   the move, zero failures).
2. Repo root contains at most one `.py` file (`run_tests.py`).
3. `Dockerfile` CMD and `run_sandbox.sh/.ps1` reference `sim/` paths.
4. No module resolves a root artifact via cwd.
