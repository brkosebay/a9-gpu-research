# rc2 flight (2026-11-11, orchestrator)

rc2 = the rebased 0.4 publish set (PUBLISH-PLAN.md), sha256 `9bbdcad8…`, release `7.3.0-rc1-orchard-apple-16k-topic-rc2`,
Mesa `git-4543c70aef` (lane M stages + PBE + PBE2). Installed from the warm rc1 boot into `/var/tmp/orchard04rc2`,
then **cold-booted from DFU** with the PSCI launcher. (The first DFU attempt went black because the orchestrator's
foreground call was interrupted mid-launch. The clean relaunch worked.)

## Before rc2: rc1 by warm hop from h3
Bring-up OK, armed, state 12, AMC present, suspend_ready `ready`. glmark2 build 427–432 fps, bell 3 µs. **s2idle
refused silently**: EBUSY, no "PM: suspend entry", no suspend_stats step (signature B below).

## rc2 cold boot
| Check | Result |
|---|---|
| Bring-up | PASS: `autoboot complete: GPU up`, `self-park armed … pin=400/400`, state 12, suspend_ready `ready` |
| **s2idle / rtcwake (IP7)** | **FAIL 2/2 (signature A):** `PM: suspend entry (s2idle)` → +1.00 s `GPU-PM sleep refused: busy or no quiescent certificate` → exit, with the GPU parked (`pstate=0`, armed) and suspend_ready `ready` just before. Lane SLEEP. |
| glmark2 census (PBE + PBE2) | **PASS:** all 16 scenes rc 0, no refusals. Terrain 2 → **17 fps** (36.3 ms), refract 2 → **30 fps** (30.8 ms). Other scenes match h3's shipped stack (build 431 vs 438), so lane PBE's 0–9 % drop was noise. |
| Mip content check | grim captures fullscreen G5P clients as black, so this is moved to the owner's visual check (refract, `PVR_G5P_GPU_MIPBLIT=0` vs default) |

**Release blocker: s2idle.** A (cold) = GPU prepare's stage-1 drain times out after 1 s although the GPU is parked.
B (warm) = silent EBUSY before suspend entry. Owner rule: warm and cold must behave identically, so B is a bug of
its own. Both are handed to lane SLEEP (docs/release/orchard-0.4/lane-sleep/), with logs in `flight-rc2/sleep/`.
