# Lane SLEEP: s2idle never enters on rc2 (host only, not device-proven)

Bundle **`build/orchard-0.4/orchard-04-rc2s/orchard-04-rc2s.tar.gz`**, sha256
`a2e905a27161…`. Release
`7.3.0-rc1-orchard-apple-16k-topic-rc2s`. It is the kernel only: userspace, runner and tools are rc2's, byte for byte
(the packager asserts it), and the J71t DTB is identical to rc2's.
Device commands: `DEVICE-COMMANDS.txt` (not published) (also in the bundle dir).

**Status in one paragraph.**
- **SLEEP2 update (rc2s2):** rc2s's cold flight showed that 0035 was not sufficient. A second term, the boot-long
  render claim `accepted`, refused every attempt. drivers/drm/0037–0039 remove it and name every remaining
  reason. See [SLEEP2](#sleep2-rc2s-cold-refused-busyaccepted-cause-found-fixed-in-rc2s2-host-only-not-device-proven).
- **A (cold):** found a sufficient cause and fixed it (drivers/drm/0035). It is confirmed only when the cold flight
  prints `GPU-PM prepared` and `GPU-PM off`/`on`.
- **B (warm):** no warm-specific cause identified from the available data. The rc1 warm logs are not on the Mac, and
  their capture lost the `suspend entry` line. rc2s makes every refusal self-identifying.
- **New warm-only difference found, not fixed:** on a kexec boot `pmgr-pwrstate` keeps every S8000 power domain on
  (`keep_on`), so the GPU cannot be powered off in sleep. rc2s therefore *refuses* GPU sleep on warm boots by name
  (`warm-gfx-power-held`, drivers/drm/0036) instead of dirty-starting the firmware on resume.
- **So the owner rule (cold = warm) is NOT met yet.** Cold should sleep and warm refuses cleanly. Closing it needs a
  decision on `keep_on` (row 11 below).
- **Orchestrator ask:** the rc1 warm `dmesg`, unfiltered, and how it was captured.

| What | Where |
|---|---|
| Orchard | branch `lane-sleep/rc2s` = `publish04/rc2` (`23e8b2d`) + `a337852` + `a576895`, worktree `build/orchard-0.4/lane-sleep/orchard` |
| Linux | `build/orchard-pr2/cs/sleep-linux`, branch `lane-sleep/s2idle` on local base `lane-sleep/rc2-base` (`a30c8c86a` = `cee9395ac` + the rc2 series, patch-id identical to rc2's `kwork` tree) |
| Linux commits | `45bfd62b6` core/0006, `aedbd47d2` drivers/pci/0039, `9f8061751` drivers/usb/0015, `a714becbb` drivers/soc-apple/0019, `db74b228c` drivers/drm/0034, `c497628dd` drivers/drm/0035, `0347de210` drivers/drm/0036 |
| Build | `ORCHARD_KERNEL_TEST_SUFFIX=rc2s JOBS=6 scripts/orchard/build-orchard-kernel.sh build/orchard-0.4/lane-sleep/orchard out-rc2s j71t`: PASS, 77 modules, vermagic asserted per .ko; no new warnings (log) |
| Package | `python3 scripts/orchard/package-orchard04-rc2s.py` |
| Host tests | orchard `lane-sleep/rc2s`, Linux py3.12 clean bundle: Ran 735 tests, OK (skipped=20). Host tests are not hardware results. |

## Cause A: cold rc2, refused after a 1.0 s drain (sufficient cause found, fixed; device confirmation pending)

**Evidence.** `dmesg-full-cold.txt`:

```
[11.007919] RENDER-V3 close-defer slots=8/7 jobs=2: the PM may still write its state back; unbind once it has moved past it
[11.007922] RENDER-V3 close-defer2 slots=8/7 pm=last pending=1
[11.860069] RENDER-V3 pm-ctx seq=3 slots=10/9 how=new ...          <- labwc, the only context from here on
[44.187359] PM: suspend entry (s2idle)
[45.189915] GPU-PM sleep refused: busy or no quiescent certificate  <- +1.0026 s
```

No `close-deferred` line ever follows. Second attempt: +1.0030 s.

The log proves `close_deferred[0]` was set, which alone forces the refusal. It cannot prove that no other silent
busy term was also set. The candidate is `cu_sequence` (a compute job), which logs nothing. rc2s names whichever
term holds.

**Mechanism.**
- `g5p_sleep_idle()` (`system-sleep.inc:6`, from drivers/drm/0025) returned false while `rd->close_deferred[0]` was set.
- A deferred close releases only once the closed context is neither the PM's last nor its previous *distinct* context
  (`g5p_render_close_deferred()`, `drm-render-unbind.inc:413`; `pm_prev` moves only on a context switch,
  `drm-render-v3.inc:3544`).
- A boot-time client (slots 8/7) exited while it was `pm_last`. After that only labwc rendered, so `pm_prev` stayed
  8/7 for good.
- Every glmark2 run that exits re-creates the same state, so the lane-S matrix would hit it on every cycle.

**Timing.** Stage 1 polls `!g5p_sleep_idle()` up to `G5P_SLEEP_DRAIN_MS` = 1000. Stage 2 then refuses at the
state check under the core lock, about 2.6 ms later. That is short of the 20 ms host wait and the 50 ms certificate
wait, which rules both of them out.

**Why `suspend_ready` said `ready`.** `check()` returned 0 for any `!idle` state outside the never-park envelope
("prepare drains it"). It never sampled anything. This is the same unsampled branch GS4 described.

**Not a regression.** The term has been in the predicate since GS (0025). Before IP's 0031, the never-park firmware
refused anyway. h3 → rc2 is a consolidation only:
- 0031 and 0032 were merged and renumbered;
- 0033 changed in its headers only;
- the `system-sleep.inc` result is identical.

So no build has ever admitted G5P sleep on hardware. There is no known-good build to diff against: this is the first
flight of a never-flown path.

**Fix (drivers/drm/0035).** The deferred close is no longer a sleep-busy state. Its hazard is a PM write-back on a
**later job**. No job runs between the reservation and platform off:
- The client and host gates are shut.
- `g5p_system_suspend` detaches every slot the firmware holds. `g5p_ru_held_slots` includes the deferred context's.
- `g5p_rv3_rebuild_host()` clears `pm_last`/`pm_prev` and every context's `retained`. The pending close therefore
  releases after the first post-resume job with plan **release**, never an unbind of old-epoch slots
  (`g5p_ru_close_plan`: `!retained` → RELEASE). This is the sequence the in-boot recovery already uses.

The R1 quiescent certificate, the rings, the TA/3D stamps and every other busy state are unchanged. The GPU is never
unbound.

## Cause B: warm-hopped rc1, EBUSY with no "suspend entry" line (NOT found, NOT fixed; instrumented)

`pm_suspend()` prints `PM: suspend entry` **unconditionally, before** `enter_state()` (`kernel/power/suspend.c:794`).
An exit line without an entry line therefore means the capture lost lines. That capture cannot show that the GPU
line was absent either.

B may simply be A: a warm boot has the same desktop and the same boot-time client. That is unproven, and the B logs
are not on the Mac.

What the code does show is that silent `-EBUSY` paths existed. All of them now log:

| Path | Before | Now |
|---|---|---|
| `enter_state` trylock of `system_transition_mutex` | silent | `PM: suspend refused: another system transition holds the lock -16` |
| provider `prepare` error | silent | `PM: suspend refused: admission <dev> <errno>` |
| precheck notifier error | silent | `PM: suspend refused: precheck <symbol> <errno>` |
| PCIe S8003 precheck (nbd, late ports/work, no PD, storage port not powered, unreserved accelerator, not s2idle) | silent | `system sleep refused: <reason> late_ports=..` (attempt only) |
| dwc2 retained-gadget precheck | silent | `system sleep refused: <not-s2idle\|gadget-not-peripheral> op_state=N` |
| AOP precheck (`sleep_ready` false) | silent | `system sleep refused: AOP firmware not started` |
| G5P prepare: no core/drm/boot, failed epoch, client gate already shut, host gate already shut | silent | `GPU-PM sleep refused: stage=<entry\|client\|host> why=<token>` |
| G5P prepare: every later refusal | one generic line | `stage=<host\|lock\|state\|drain\|certificate> why=<token> ms=N`; the certificate refusal carries `r1_1000/r1_0/r1_8` |
| G5P suspend pre-detach `-EBUSY` | silent | `GPU-PM suspend refused: why=<token>` |
| G5P suspend/resume failures | `GPU-PM frozen ret` | plus `GPU-PM suspend failed step=<...>` / `GPU-PM resume failed step=<...>` |

Precheck notifiers receive `PM_SUSPEND_PRECHECK_ATTEMPT` as `data` for an attempt and `NULL` for the readiness query.
Polling `suspend_ready` therefore stays quiet.

## Cold vs warm differences in the sleep/admission path (owner rule: none allowed)

| # | Difference | Status |
|---|---|---|
| 1 | B's capture lacks `PM: suspend entry`. Code: always printed. A log-capture difference, not kernel behaviour. | Device commands now capture unfiltered `dmesg` before and after, plus `suspend_stats` and the rtcwake elapsed time, identically on both boots, and diff a normalised summary. |
| 2 | Silent `-EBUSY` paths (table above) hid whichever check differed after a hop. | **Fixed** (logged). |
| 3 | G5P DS108 boot mode 1 (cold) vs 3 (kexec): strict origin checks in mode 3. Resume feeds `RECOVER`, which sets `reset_ok_gen = gen`, so `g5p_ds_origin_trusted()` holds in both modes and the claim gate opens the same way. | Checked in code, no change. Device: `GPU-PM on` must appear on both boots. |
| 4 | AOP: a kexec boot takes the SPI0 reload/refuse branch (`aop.c:510`, `uncertified-kexec` → probe `-EPERM`). `sleep_ready` is only set after a successful start. A refused warm AOP leaves no notifier (devm), not a silent refusal. A warm AOP that is still starting refuses. | By design. **Now named** if it refuses. |
| 5 | PCIe/ANS: a kexec boot takes `apple_s8003_powered_reset()` instead of the full power-up. Both keep `REFCLK_NOGATE` (set by `apple_h9p_s8003_shutdown()` on the outgoing side and `apple_s8003_port_power_on()` on cold), which `apple_s8003_port_powered()` requires. The late-port (Wi-Fi) retry timing can differ, and `late_ports`/`late_work` refuse while it runs. | Checked, no change. **Now named** (`late-ports` / `late-work` / `storage-port-not-powered`). |
| 6 | The close-deferred state depends on which client last exited before labwc. That ordering can differ between a cold boot and a warm session start. | **Fixed** (cause A). |
| 7 | `suspend_ready` vs `prepare`: `check()` answered `ready` for busy states that prepare can never drain. | **Fixed:** `check()` refuses non-draining states (`compute-epoch`, `terminal`, `dc-pending`) as `busy/<token>`, and prepare's drain stops early on them. `stuck`/`recovering` still get the 1 s drain. The old `never-park/busy` token is now `never-park/<token>`; there are no consumers in orchard or omarchy-a. |
| 8 | `cu_sequence` (any compute job) refuses sleep for the rest of the epoch. GS left it deliberately: there is no CDM stamp certificate. Workload-dependent, not boot-dependent. Whether the shipped desktop/glmark2 path submits SUBMIT_COMPUTE_TYPED was not established; the refusal line will say. | **Not fixed.** Now named `compute-epoch`, and `suspend_ready` reports it. Follow-up: a CDM retirement certificate. |
| 9 | `dc_pending` (an unconsumed bind DC3 pair) never drains at idle. | Not fixed. Now named `dc-pending` and refused at once. |
| 10 | Outside the path: the cold cmdline already carries `pcie_apple_h9p.ans_keep_power=1 ans_boot_mode=handoff apple_pmgr.kexec_keep_on=1`. These are kexec-named module parameters on a cold boot; behaviour is keyed on `linux,booted-from-kexec`. They are hardware-behaviour module parameters (against PLAN's rule) predating this lane. | Noted, not touched. |

| 11 | **pmgr-pwrstate `keep_on` on a kexec boot.** `ps->keep_on = ps->warm` for every `apple,s8000-pmgr-pwrstate` node when `linux,booted-from-kexec` is set: `apple_pmgr_ps_power_off()` returns -EBUSY and clock-gate disable is a no-op for the whole boot (drivers/pmdomain/0001 "retain the tethered warm boot state"; documented in docs/power/s2idle-test-plan.md: "On a warm boot this inhibits genpd power-off"). genpd ignores that error, so a sleep would report success with gfx (and every other domain) still powered, and the G5P resume would boot the firmware over a GPU that was never power-cycled. That is the dirty start that DS108 only admits through its single bounded reset at probe. This is the largest cold/warm behavioural difference in the path, and it also affects every other domain's sleep and runtime power on warm boots. The `apple_pmgr.kexec_keep_on=1` cmdline token matches no code in this tree: the hold is unconditional on kexec. | **Not fixed** (needs an owner/RE decision). Interim: drivers/drm/0036 refuses GPU sleep on kexec boots, reversibly and by name, before any gate is shut, and `suspend_ready` reports it. Proposed fix: end the hold once the handoff is done (genpd's own `sync_state`/stay-on model, or clear `keep_on` after the consumers probe), or have the G5P cycle gfx through PMGR the way `kexec_gpu_cycle` does at probe. Read the hang history in docs/gpu/experiments/gpu-warm-kexec-hang-proof.md first. |

Apart from row 11's interim refusal, the fix build has no warm-specific code. The device command diffs a normalised
summary of each run. The only expected difference is the warm `warm-gfx-power-held` refusal.

## BELL 0033 (doorbells in park epochs)

0033 changes how the sleep detach's DC kick rings a parked firmware (`dc-kick did=rang-parked`): no 2 ms GPC settle
wait. Whether the firmware parks again after the detach is the open question. rc2s logs it: `GPU-PM suspend parked
again after detach us=N`, or on failure `step=park-after-detach` with the R1 words.

## Draft PR text (orchard, follow-up to publish04/g5p-suspend + publish04/suspend; not published)

- **Problem.** On J71t with an idle labwc desktop, every s2idle attempt drained for 1 s and the GPU refused. A
  boot-time client's deferred close stayed the PM's previous context for good. Several refusal paths in the PM core
  and in drivers returned `-EBUSY` with no log line.
- **Changes.**
  - core/0006: log every admission, precheck and transition-lock refusal; precheck notifiers get an attempt cookie.
  - pci/0039, usb/0015, soc-apple/0019: name the precheck reason, during an attempt only.
  - drm/0034: G5P names every sleep refusal and failing step, and `suspend_ready` refuses non-draining states.
  - drm/0035: admit sleep with a deferred close pending.
  - drm/0036: refuse GPU sleep on a kexec boot while pmgr holds gfx powered.
- **Other devices.** core/0006 changes only logging and the precheck `data` argument; the existing notifiers ignored
  it. The PCIe, dwc2 and AOP logs are attempt-only and their decisions are unchanged. G5P is J71t only.
- **Depends on / order.** After g5p-suspend (0025–0033) and suspend (core/0003–0005).
- **Device test still required.** `DEVICE-COMMANDS.txt` (not published): warm, then cold, the identical
  rtcwake with an empty summary diff; then lane S's matrix.
- **CHANGELOG.** "J71t: s2idle is no longer refused by the GPU after a GPU client exits; every sleep refusal names
  its reason in the kernel log. After a warm (kexec) restart the GPU still refuses sleep; cold boot to sleep."

## SLEEP2: rc2s cold refused `busy=accepted` (cause found, fixed in rc2s2; host only, not device-proven)

Bundle **`build/orchard-0.4/orchard-04-rc2s2/orchard-04-rc2s2.tar.gz`**, sha256
`5048374bf5cd…`. Release
`7.3.0-rc1-orchard-apple-16k-topic-rc2s2`. As with rc2s, only the kernel changed: userspace, runner and tools are
rc2's byte for byte, and the DTB is rc2's (the packager asserts both). Device commands:
`DEVICE-COMMANDS-rc2s2.txt` (not published) (also `DEVICE-COMMANDS.txt` in the bundle dir).

| What | Where |
|---|---|
| Linux `lane-sleep/s2idle` | `b6277b2bb` drivers/drm/0037, `dc485fab0` drivers/drm/0038, `73810a71c` drivers/drm/0039, on `0347de210` (rc2s) |
| Orchard `lane-sleep/rc2s` | `f35ba56`: the 3 patches (`tools/kernel-tree/export.py`, which reports that they reproduce the branch exactly) plus one line each in `chips/s8003.toml` and `devices/j71t/device.toml`; the matrix is unchanged |
| Build | `ORCHARD_KERNEL_TEST_SUFFIX=rc2s2 JOBS=6 scripts/orchard/build-orchard-kernel.sh build/orchard-0.4/lane-sleep/orchard out-rc2s2 j71t`: PASS, 77 modules, vermagic asserted per .ko. The warning set is identical to rc2s's (log). Build volume: 5.6 GiB free afterwards |
| Package | `python3 scripts/orchard/package-orchard04-rc2s2.py` (rc2s's packager, plus asserts for 0037–0039 and that the `accepted` token is gone from the Image: rc2s 1, rc2s2 0) |
| Host tests | Clean `git archive` in `python:3.12-slim` with `PYTHONPATH=src`: Ran 735, failures=28, errors=24, skipped=26. The failure set is **identical** at `a576895` (rc2s) and `f35ba56` (diffed by name). It is mostly `ManifestError not raised`, so it comes from the environment and not from this lane. The G5P tests (`test_agx_g5p`) load and pass. This is not lane SLEEP's 735/OK environment. Host tests are not hardware results. |

### Cause (evidence)

- **The busy token is a latch, not a count.** `g5p_sleep_busy()` refuses on `atomic_read(&d->accepted)`. `d->accepted`
  has exactly one writer: `atomic_cmpxchg(&d->accepted, 0, 1)` in `g5p_render_device_claim()` (`drm-render.inc:2093`),
  on the **first** accepted job of the boot. It is cleared only by `atomic_set(..., 0)` at probe (`a9-gpu-drm.c:1180`).
  The driver says so itself: "The first accepted job claims the device for render until reboot" (`drm-render.inc:2061`);
  "One render attachment per boot: accepted stays held" (`drm-render.inc:1749`). So once any client has rendered
  (labwc does at login), every sleep attempt for the rest of the boot was refused, whatever the GPU state.
- **The intended term already exists.** lane GS's design (lane-gs/README.md: "in-flight or accepted work (prepare drains
  it)") means jobs accepted but not yet signalled. That count is `d->r8_queued`: incremented at accept
  (`drm-render.inc:2361`, compute `drm-compute-v1.inc:657`), decremented right before `dma_fence_signal`
  (`drm-render.inc:1204`). It is already the next term in the predicate.
- **History.** The term was in the 0025 predicate (`rd->cu_sequence || atomic_read(&d->accepted) || ...`) from the
  start. `close_deferred` was ORed into the same expression, so rc2's refusal could not tell them apart. Lane SLEEP
  noted that "the log cannot prove no other silent busy term was also set". 0035 removed `close_deferred`, and 0034's
  first-match order then exposed `accepted`. Neither 0026, 0031 nor 0035 uses `d->accepted`, and nothing depends on
  the claim for sleep. Resume keeps the claim on purpose: the same `g->boot`, `render_claimed` and
  `g5p_rv3_rebuild_host()` contexts, the path 0035's rationale already relies on. This was never a regression: no
  build has ever admitted G5P sleep after a client rendered.
- **Log fit** (`flight-rc2s/dmesg-cold-sleepcheck.txt`). At 468.71 the close completes (`plan=unbind ... claimant=0`)
  and at 468.72 the context is released. 5 s later, 1000 ms of drain (`client_users=0 busy=accepted`), then
  `stage=state why=accepted`. The term never changes because nothing can change it. The second cycle (485.4) shows
  the same pattern.

**Why `suspend_ready` said `ready`.** check() runs the same predicate. It got `accepted` with `drains=true` (it is
neither static nor never-park), and so answered 0: "prepare drains it". The criterion was the same, but its premise
was wrong: a drainable state with nothing in flight never drains.

### Fix

- **drm/0037: do not refuse system sleep on the render claim.** The `accepted` term is gone; `r8_queued` remains. The
  R1 certificate, the rings, the TA/3D stamps and every other busy state are unchanged. The quiescence criterion is
  not loosened: only a term that never measured work is removed.
- **drm/0038: name every held sleep busy state.**
  - The predicate is now a mask. Refusal lines (`drain bound`, `stage=state`, `GPU-PM suspend refused`,
    `suspend_ready`) print every held reason at once, '+'-joined so each stays one token.
  - First-match hid a term behind another twice in a row (`close_deferred` hid `accepted`). The terms after it
    (`stamp-*`, `unconsumed-*`, `unretired-*`) have never been evaluated on hardware. One flight now names them all.
  - The stamp and per-context reads still run only when nothing is in flight and no failure or recovery can replace
    the boot, as before.
  - Prepare's decision is unchanged.
- **drm/0039: answer the readiness query with prepare's criterion.**
  - A drainable reason counts as "in flight" only while `r8_queued > 0`. Otherwise check() answers
    `not-ready 201000000.gpu:busy/<reasons> -16`, as prepare's state check will after its 1 s drain.
  - Prepare itself is unchanged. A transient snapshot (a close item still queued without a job) may read busy for a
    moment, which is harmless.
  - Ordering checked: `executing` clears and `retired[]` is set before the `r8_queued` decrement.
- **Locking.** `rd->lock` is a leaf lock: allocations only, no `g->lock` or firmware wait under it. It is taken in the
  same cases as before.
- **Not touched:** `g5p_sleep_gfx_power_held()`/`keep_on` (lane KEEPON), 0034–0036 (rc2s flew them).

**The other busy terms, audited statically** (none of them has run on hardware after `accepted`):
- `queued`: an entity leaves `sched.run` when its last job is picked, or after its close item runs
  (`g5p_rs_pick()`, `g5p_rs_closed()`). Not a latch.
- `unconsumed-*` / `unretired-*`: flags are cleared at prepare and set at TA/3D completion. The completion sets them
  only `if (rd->sequence == seq)`, but an ahead job is always the same context's (`g5p_rv3_ahead_next(d, r, ..)`
  reads `r->entity`) and clears that context's flags at its own prepare. A released context leaves `rd->contexts`
  (`g5p_render_release()`). Not a latch.
- `stamp-ta/3d`: both engines' stamps must equal `rd->sequence`, and every render job writes both.
  - Open, error path only: `rd->sequence` advances at prepare, before the TA publish. A publish that fails without
    making the epoch terminal would leave `stamp-*` held. On a healthy idle desktop this is not expected.
  - If it happens, 0038 names it.
- `executing` / `ahead`: they clear before the job's `r8_queued` decrement or do not outlive it.

Only the flight can show the firmware-side terms: the stamp values themselves, the rings, `boot-drain` and the R1
certificate.

### `device_pinned` ≈ 400 MB: not a glmark2 leak (answer for lane RAM2)

The premise "after the last client exits" does not hold: `device_pinned` and `live_bo_bytes` are **device-wide**
(rc2-ram-20261111.md), and labwc and its peers stay open. Over the run:

| When | live_bos | device_pinned |
|---|---|---|
| 463.11, before glmark2 | 57 | 375712K |
| 468.55–468.74, during glmark2's close | 64 → 59 | 400896K → 412592K |
| 475.03, 6 s later | 57 | **375728K** |

After glmark2's close the counter rose to 412592K, with labwc still allocating. 6 s later it was back to 375712K,
16K (one 16 KiB page) above the starting value. The 485 s cycle shows the same shape. So glmark2's pins come back; the
roughly 25 MB still held at its release are buffers that labwc (its dma-buf importer) holds until it drops the
surface.

The log itself shows three things:
- `live_bo_bytes == device_pinned` at both idle baselines (375712K, 375728K).
- The rise at VM release, 400896K → 412592K, is identical in both cycles.
- The close of glmark2 leaves 59 BOs / 400896K live in both cycles.

The rest is **inferred, pending the `g5p_bos` captures**:
- that labwc allocated the extra 11.7 MB;
- that labwc holds the ~25 MB at release as dma-buf imports;
- that the ~375 MB baseline is the open clients' standing set (Mesa arena, BO caches, scanout).

Whether it is cache or leak cannot be decided from this log. The one-page drift after one cycle is too small to call.
DEVICE-COMMANDS-rc2s2 captures `debugfs dri/*/g5p_bos` (owner, size, vm_pins) at idle before, after glmark2, after
resume and at final idle for each of cold and rtc-1..3. A baseline that grows per cycle is a leak; a flat one is cache.

### Device test (exact lines)

Cold boot of `orchard-04-rc2s2` (DFU → PSCI launcher), `sleep-check.sh cold`, then lane S's matrix (RTC ×3,
Home ×3, charger in/out) with glmark2, NVMe, USB and touch after each resume.

Pass: `suspend_ready.before` = `ready`, then:

```
PM: suspend entry (s2idle)
GPU-PM prepared: admission reserved ms=<small>       (no "drain bound" line)
GPU-PM suspend detach held=.. contexts=.. deferred=../0
GPU-PM suspend parked again after detach us=..
GPU-PM off: stable-off epoch=..
GPU-PM on: fresh ALIVE gen=.. epoch=..
GPU-PM complete failed=0
PM: suspend exit                                     rtcwake rc=0, ~20 s
```

**If it still refuses, the line now names every reason**, e.g. `stage=state why=stamp-3d+unretired-3d`. Everything
from `stage=drain` / `stage=certificate` onward has never run on hardware. If it says `accepted`, the old kernel
booted.

Warm: unchanged (`warm-gfx-power-held`, row 11; lane KEEPON).

### Draft PR text addendum (not published)

- **Changes**, added to the list above:
  - drm/0037: the sleep busy predicate no longer reads the boot-long render claim as work.
  - drm/0038: every held busy reason is logged at once.
  - drm/0039: `suspend_ready` refuses a drainable reason with no job in flight.
- **Other devices:** none; G5P is J71t only.
- **Order:** after drm/0036.
- **CHANGELOG** (replaces the first clause of the line above): "J71t: s2idle is no longer refused by the GPU once
  any GPU client has run".
