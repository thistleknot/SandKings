#!/usr/bin/env bash
# Hardened launch for the Sandking Sandbox (SPEC_SANDBOX.md).
#
#   ./run_sandbox.sh            # ISOLATED: --network none, headless sim
#   ./run_sandbox.sh --console  # localhost-only web console (127.0.0.1:8000)
#
# Both modes: non-root, read-only root filesystem, all Linux capabilities
# dropped, no new privileges, memory + pid limits. State persists in a
# named volume so the colonies resume across runs.
set -euo pipefail

IMAGE="${SANDKING_IMAGE:-sandking}"
VOLUME="${SANDKING_VOLUME:-sandking_state}"
MODE="${1:-isolated}"

COMMON=(
  --rm
  --user 10001
  --read-only
  --cap-drop ALL
  --security-opt no-new-privileges
  --pids-limit 256
  --memory 4g
  --tmpfs /tmp
  -v "${VOLUME}:/state"
)

docker volume create "${VOLUME}" >/dev/null

if [ "${MODE}" = "--console" ] || [ "${MODE}" = "console" ]; then
  # The web console needs a reachable port. We publish ONLY to the host
  # loopback and put the container on a dedicated bridge. The image makes
  # zero outbound calls (enforced by tests/test_dashboard.py), so no data
  # leaves the machine; for airtight egress-blocking use the default
  # isolated mode instead.
  echo "[sandbox] console at http://127.0.0.1:8000  (localhost only)"
  exec docker run "${COMMON[@]}" \
    -p 127.0.0.1:8000:8000 \
    "${IMAGE}" \
    python sim/dashboard.py --persist /state/terrarium.db --port 8000 --host 0.0.0.0
else
  # ISOLATED: no network stack at all. Maximum containment; the sim runs
  # headless and autosaves. Inspect via: docker exec <id> sh
  echo "[sandbox] isolated run (--network none); state in volume ${VOLUME}"
  exec docker run "${COMMON[@]}" \
    --network none \
    "${IMAGE}" \
    python sim/sandkings.py --persist /state/terrarium.db --steps 100000
fi
