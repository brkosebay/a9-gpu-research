# Lane SLEEP: s2idle never enters on rc2 (host only, not device-proven)

Bundle **`build/orchard-0.4/orchard-04-rc2s/orchard-04-rc2s.tar.gz`**, sha256
`a2e905a27161…`. Release
`7.3.0-rc1-orchard-apple-16k-topic-rc2s`. It is the kernel only: userspace, runner and tools are rc2's, byte for byte
(the packager asserts it), and the J71t DTB is identical to rc2's.
Device commands: `DEVICE-COMMANDS.txt` (not published) (also in the bundle dir).

**Status in one paragraph.**
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
