#!/usr/bin/env python
"""Single-process test runner for the Sand Kings battery.

Why this exists: running each tests/test_*.py as its own `python file.py`
re-imports torch (via sandkings -> neural_hive) once PER FILE — ~38 cold torch
imports, minutes of wall-clock. This runner imports the heavy deps ONCE, then
executes every suite in-process.

It handles BOTH test styles in this repo:
  - plain module-level `test_*` functions with an `if __name__ == "__main__"`
    self-runner (most suites), and
  - `unittest.TestCase` classes (e.g. tests/test_wages.py).

Default-neutral hygiene: the feature gates that some suites flip
(CAPTURE_CHANCE, WAGE_ENABLED) are snapshotted at import and RESET before every
suite, so a suite that enables a feature cannot pollute the next one's
byte-identity assertions. The per-process battery remains the stricter final
gate if ever in doubt, but this is sound for iteration and CI.

Usage:  python run_tests.py            # run all suites
        python run_tests.py test_wages # run one suite by stem/substring
Exit code is nonzero if any suite fails.
"""
import importlib.util
import inspect
import io
import os
import random
import sys
import traceback
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(ROOT, "tests")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import sandkings  # torch imported exactly once here (via neural_hive)

# Feature gates suites may flip; reset before each suite for isolation.
_GATE_NAMES = ("CAPTURE_CHANCE", "WAGE_ENABLED", "BARGAIN_ENABLED",
               "HYDRO_SOURCES_ENABLED", "MAW_RL_ENABLED", "GUPPIES_ENABLED",
               "CRICKETS_ENABLED", "SNARES_ENABLED", "FISHING_ENABLED",
               "SHRUBS_ENABLED", "WINTER_BITE_ENABLED", "HOARD_PLANNING_ENABLED",
               "SCARCITY_WAR_ENABLED")
_GATE_DEFAULTS = {n: getattr(sandkings, n) for n in _GATE_NAMES if hasattr(sandkings, n)}


def _reset_gates():
    for name, value in _GATE_DEFAULTS.items():
        setattr(sandkings, name, value)


def _seed():
    random.seed(0)
    np.random.seed(0)


def run_suite(path):
    """Import one test module and run its suites. Returns (ok, detail)."""
    stem = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[stem] = mod
    _seed()
    spec.loader.exec_module(mod)  # module import must not raise

    # 1) unittest.TestCase classes defined in this module
    cases = [obj for _, obj in inspect.getmembers(mod, inspect.isclass)
             if issubclass(obj, unittest.TestCase) and obj.__module__ == stem]
    if cases:
        suite = unittest.TestSuite()
        loader = unittest.TestLoader()
        for case in cases:
            suite.addTests(loader.loadTestsFromTestCase(case))
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        if not result.wasSuccessful():
            bits = []
            for kind, items in (("FAIL", result.failures), ("ERROR", result.errors)):
                for test, tb in items:
                    last = tb.strip().splitlines()[-1] if tb.strip() else ""
                    bits.append(f"{kind} {test}: {last}")
            return False, "; ".join(bits)

    # 2) plain module-level test_* functions
    fns = [obj for name, obj in inspect.getmembers(mod, inspect.isfunction)
           if name.startswith("test_") and obj.__module__ == stem]
    for fn in fns:
        _seed()
        fn()

    if not cases and not fns:
        return False, "no tests found"
    return True, "ok"


def main():
    argv_filter = sys.argv[1] if len(sys.argv) > 1 else None
    files = sorted(f for f in os.listdir(TESTS)
                   if f.startswith("test_") and f.endswith(".py")
                   and (argv_filter is None or argv_filter in f))
    npass = nfail = 0
    for f in files:
        _reset_gates()
        _seed()
        try:
            ok, detail = run_suite(os.path.join(TESTS, f))
        except Exception as exc:  # import-time or uncaught in-test failure
            ok, detail = False, f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        if ok:
            npass += 1
        else:
            nfail += 1
            print(f"FAIL {f}: {detail}")
    print(f"==== passed={npass} failed={nfail} ====")
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
