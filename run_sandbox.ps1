# Hardened launch for the Sandking Sandbox (SPEC_SANDBOX.md), Windows.
#
#   .\run_sandbox.ps1            # ISOLATED: --network none, headless sim
#   .\run_sandbox.ps1 -Console   # localhost-only web console (127.0.0.1:8000)
#
# Both modes: non-root, read-only rootfs, all capabilities dropped, no
# new privileges, memory + pid limits, state in a named volume.
param([switch]$Console)

$ErrorActionPreference = "Stop"
$Image  = $env:SANDKING_IMAGE  ; if (-not $Image)  { $Image  = "sandking" }
$Volume = $env:SANDKING_VOLUME ; if (-not $Volume) { $Volume = "sandking_state" }

docker volume create $Volume | Out-Null

$common = @(
  "--rm", "--user", "10001", "--read-only",
  "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
  "--pids-limit", "256", "--memory", "4g", "--tmpfs", "/tmp",
  "-v", "${Volume}:/state"
)

if ($Console) {
  Write-Host "[sandbox] console at http://127.0.0.1:8000  (localhost only)"
  & docker run @common `
    "-p" "127.0.0.1:8000:8000" `
    $Image `
    python sim/dashboard.py --persist /state/terrarium.db --port 8000 --host 0.0.0.0
} else {
  Write-Host "[sandbox] isolated run (--network none); state in volume $Volume"
  & docker run @common `
    "--network" "none" `
    $Image `
    python sim/sandkings.py --persist /state/terrarium.db --steps 100000
}
