# Apple-way GPU idle power and context lifecycle: design + probe (2026-11-09)

Design lane, host only (Ghidra 20H350 j71t, retained iOS capture `build/gpu/ios-capture-bundle/20261101T154856Z`,
tree `build/orchard-pr2/cs/skiptiles-kwork`). [V] code/Ghidra, [P] device/capture bytes, [I] inference.
Folds in the orchestrator's 2026-11-09 F0/F1/F2/H1 results: freed tables, freed render memory and post-loss code
are ruled out. Every freeze lands 0.3–3 s after a **PM-involved close** (`close_run … pm=prev` or the deferred
`park`), followed by a fresh bind.

## 1. Bottom line

- **iOS idles at two levels, and Level 1 runs between every burst.** The firmware parks itself whenever its rings go empty: full cache and MMU
  flush, GPC 0, halt. Live iOS bytes: at idle it is parked 96.6 % (65 ms parked / 2.5 ms awake cycles). Under Metal
  stress it parks for 1.3 ms between **every** ~131 ms command buffer (146 parks in 19 s) [P, `*-series.csv`
  `policy+0x34`]. So every iOS app switch, kill or context destroy happens across a firmware park.
- **Our stack never runs that path.** The production pin (ctrl+0x1040 = policy+0x6f4 = 400, sampler off) keeps
  the firmware awake forever [V `perf-envelope.h`]. `gpc=00000004` appears on every kick of F0/F2 [P].
- **iOS has no "park" (our parking-PC DC3), no pm_prev deferral and no close hold.** Its context teardown is
  refcount-driven, and its PM state is flushed by the firmware's own park. Our close machinery is an invented substitute
  for that park (perf60-clock.md:874, hendrik A2 fault 4), and it is now the common factor of every freeze.
- **Headline of the spec:** turn the firmware's own park back on, the iOS way (Level 1). Then retire our
  `park`/`pm_prev`/close-defer path in favour of iOS's refcounted detach (§4 B). The host PMGR-off (Level 2) comes
  last.

## 2. iOS mechanism (cited)

**Level 1: firmware self-park. The firmware decides.**
- The idle tail `0x10009bd8` calls the try-park wrapper `0x1000968c`, which calls `0x1001cec8`. It runs only when every veto is clear: engine busy
  words 0, all four root rings empty, `priv+0x188`/`policy+0x34` ≠ 0, and `[GbP+100]+0xfc` = 0 [V clock-mechanisms §1.1].
- `0x1001cec8` first runs the full drain `0x1001b638`:
  - `11f00 = 1`;
  - `688 = 7`, then poll;
  - `1720 = 0x1f`, then poll `1728`;
  - **SLC all-context `e230 = c03`**, then poll `e238`;
  - **`MMU_CTRL_INVAL` ALL_CONTEXTS|PC `e138 = 0x804`**, then poll.

  It then writes `R1+0x1004` = wake target and sets `R1+0` bit 29. Finally it either parks (`setter(0)`, then the self-branch `0x1001d074`) or aborts if work arrived
  (`R1+0 = 0x40000000`) [V perf60-clock §0].
- The wake is host-driven at submit. `AGXMetaFirmware_submitDeviceControl` `6ca05d4` does fender vt+0x80, i.e. **`R1+0x14 = 7` and a read-back**
  (`6ca6644`). It then reads the nibble (vt+0x18). At nibble 0 it only inspects `R1+0`/`R1+0x14` (`6ca6618`, `6ca6658`).
  `forcePowerCycleAndReboot` would run only if `acc+0x510` bit 0 is clear, and j71t has 0x00200545 [P]. Then it does
  **`R0+0xb00 = 0x10` at any nibble** [V].
- The re-powered firmware reboots from retained RAM. Its boot sampler `0x1000aa80` applies `policy+0x28`. That is the
  only place iOS changes clock: `policy+0x34` goes 4→0→4 under load and 1↔0 at idle [P].

**Level 2: host PMGR-off. The host decides, but only after Level 1.**
- Arming: `drainFirmwareEventRing` `6c99788` / `6c856b8` arms a **40 ms** timer (`acc+0x56c`, re-arm 5 ms `+0x56d`; live
  40/5 [P]) once every stamp slot has reached its target (`6c58ea8`).
- `idlePowerOffTimerFired` `6c83d88` → `powerDownIfQuiescent` `6c81b18` requires all of: firmware booted (`fw+0x210`),
  alive (`cad && !cae`), event ring drained, all stamps reached (`6c58f1c`), and Fender `isQuiescent` `6ca66e4`
  (`R1+0[30:29] == 11`, nibble 0, `R1+8 == 0`).
- If those hold, the power-down is, in order:
  1. Fender mode 3 (`R1+0x10 = 0`).
  2. `stopFirmwareForPowerDown` `6c9fa10`: `R1+0x20000 = 0`, wait for bit 4, `R1+0x1000 = 0x10`, `cad = 0`.
  3. Event sources off (`6c80d34`).
  4. `setPlatformPower(0)` `6ca0f78`: panics unless `isStableOff` `6ca6684`; clock off, then power off (provider +0x568/+0x570), `fender+0xc = 0`.
  5. `d21 = 2`, kdebug `0x85930c14`.
- **Resume** happens at the next submit: `ensurePoweredForWork` `6ca60c8` → `powerUpPlatformAndBootFirmware` `6c83b18` runs
  `setPlatformPower(1)` → `prepareHardwareForBoot` `6c9fc10` (MSLV preload) → event sources on → `bootFirmwareAndWait`
  `6c9f954` (core 0, GPC 0x11, sleep on ALIVE). There is **no root reinit and no context reset**: it reboots over retained
  shared memory [V r108 §3].
- Live evidence: the `after-b` sample shows d21 = 2, cad = 0, cc8 = −1 [P]. With `acc+0x510` bits 3/4 = 0, recovery does **not**
  PMGR-cycle on j71t [P, settles freeze-doc §5.3]. `fw+0x190` ≠ 0 means the Fender arm is live [P].

**Context create/destroy and the PM (the orchestrator's first-class question).**
- **Owner:** the host kext creates the PM per **work queue**, i.e. per Metal command queue. `AGXWorkQueue_initAndAttachPM`
  `6c90774` → `createPM` `6cbc194` links it into the PM list `acc+0x2f8`, with users counted in `PM+0x1f8`. Queues may share queue 0's PM
  when `PMconfig+0x24 == 0`. Each PM has its own control, state and aux pages, and a ParamBuffer ID from a 127-entry
  pool. The ID is **sticky** (`PM+0x10`), and the firmware's PM bind `0x80009a3c` skips reprogramming
  `R0+0x210..0x224` when the requested identity equals the bank's stored one [V freelist-lifetime §2.3–2.8].
- **Holders:** the TA descriptor holds the PM ID, the wired PM backing and the kind-0 context slot from prepare to its
  **own retirement** (`6cb9fec`). The 3D descriptor holds no PM reference.
- **Destroy:** PM teardown `6cb2064` only frees block lists. It sends **no firmware command and does no wait**. The free list
  is re-initialised only on GPU restart (`resetContextAndDependencyState` `6c83630` → PM vt+0xe0).
- **Address-space destroy:** `AGXGart_detachSlotsAndDestroyAddressSpace` `6caef14`. For each of the 4 slot kinds it bumps
  the slot generation `acc+0x1208[s]++`, clears owner `+0x1210`, sets state `+0x1230 = 4` and pushes the slot on a free
  stack `+0x1220/+0x1228`. It then publishes PA/tag 0 by DC, waits `waitDeviceControlConsumed` `6c9a4d0`, and frees the tables.
  It runs when the last reference drops, after every descriptor of that context has retired [V].
- **iOS has no equivalent of our `park`** (a parking PC so the pair can be unparked later). It also has no pm_prev deferral.
  - It does not need the deferral: the PM write-back of the previous context ("two switches later",
    `render-user-pmset.h`) completes inside the firmware park that follows every burst, before any host release.
  - **iOS does not power-cycle between apps on purpose.** The "cycle" is the Level-1 park, which happens anyway at every
    gap ≥ ~1 ms. Level 2 happens only after ≥ 40 ms of quiet.

## 3. Why we are never-park, and what we skipped

1. **Speed.** In park mode (state 2) the firmware parked around every job. TA was 8–10 ms and 3D 32 ms, against 2/4 ms with bells
   and pin [P perf60.md §Clock]. That was at 340 MHz and slow memclk, with no hysteresis because the sampler was off.
2. **R0 hangs.** An R0 read at or toward GPC 0 hangs the bus: r74, r95, perf60c, rung5 (749/983 completions saw bit 29)
   [P mmio-access §1]. The fix was the licence, and rung5's `g5p_mmio_r0_regime_ok` keyed on `gpu_perf >= 100`.
3. **A parked/state-0 firmware ignored an unrung DC3** (70 s bind timeout). The fix was ring every DC.
4. **Pin ≥ 200 needs park→reboot→sampler.** With park removed, the pin needed the seed path [P clock-mechanisms].
5. **`6d4 = 1` did not wedge.** `policy+4 = 16` did (latency123 boots 2/3). `6d4` alone is fine, and iOS has `6d4 = 0`.
6. **Multi-context faults surfaced only under never-park.** These were shared PM, per-job free-list rebuild, PM ID aliasing and
   PM write-back into a closed slot (hendrik A2). Faults 1–3 were fixed the iOS way. Fault 4 got the non-iOS
   deferral.

**What iOS initialises that we skip:**
- policy coefficient table + 37 init words (`idle-policy.h`, built as patch 0027 `idle_fw_policy`, **never flown**);
- `policy+4 = 16` (sampler);
- ctrl+0x1038/0x1040 = 0 and policy+0x68c/0x6f4 = 0 (no override);
- ctrl+0x1028 = 3851 (we use 3348);
- Fender mode writes `R1+0x10` (vt+0x20: mode 0 when deferring, mode 3 at power-down);
- the 40 ms host timer and the whole Level-2 path;
- an unconditional `b00` after the kick.

## 4. File-level spec (branch base `orchard-pr-g5p-20261108/vdm-warmport`, worktree `build/orchard-release/hw`, new patches `kernel/patches/drivers/drm/0034..0036`)

All flags are module params (0400) and default to the current behaviour. Codex: build and stop.

**A. Level 1, firmware self-park (patch 0034).**
- `drivers/gpu/apple-g5p/boot.inc`, the `idle_fw_policy` branch (`:437–445`, `:663`):
  - Keep `g5p_idle_policy_install()` as built.
  - Add `b->park_epoch = idle_fw_policy` and set `b->gpu_perf` as today.
- `mmio-licence.h`: `g5p_mmio_r0_regime_ok(gpu_perf, override)` → `g5p_mmio_r0_regime_ok(gpu_perf, park_epoch,
  override)`, which returns `override || (!park_epoch && gpu_perf >= 100)`. Update the call in `mmio.inc:144`.
  - Today an `idle_fw_policy` epoch latches `gpu_perf = 400` and would **license R0 reads in a park epoch**: the rung5 freeze.
- `drm/apple-g5p/drm-render-v3.inc` `g5p_rv3_dc_kick` (`:893`) and the TA/3D bell (`g5p_rv3_wk_*`):
  - When `b->park_epoch`, use Apple's order from `6ca05d4`: `R1+0x14 = 7`, read it back, read `R1+0x1000` once for the log, `wmb()`,
    then `R0+0xb00` **at any nibble**.
  - Keep the 2 ms settle loop only for `!park_epoch`. Never `skip-gpc` in a park epoch.
  - No R0 read anywhere in a park epoch except the fault bank at a fault event (already licensed).
- `render-user-wake.h`: add the reason `"rang-parked"` when the nibble read 0.

**B. Retire our park / pm_prev / close-defer in a park epoch (patch 0035), the iOS lifecycle.**
- **Not flown until A shows `pol34 = 0` samples between jobs on Linux** (`idle_power_status`, L123 `pol34`; RAM only).
- `drm-render-unbind.inc`, `drm-render-sched.inc` (close item), `render-user-close.h`, `render-user-pmset.h`:
  - With `b->park_epoch`, a close waits until the context's **last submitted TA and 3D have retired** (stamps,
    as `6cb9fec`).
  - **Release gate, iOS's actual mechanism:**
    - Record `ctx->last_job_ns`.
    - Publish PA/tag 0 and free the PM pages only after a firmware park has been **observed in RAM since that job**:
      `policy+0x34 == 0` (its park-time writer is `setter(0)` in `0x1001cec8`), sampled by the close worker every 1 ms.
    - Fallback when no park is seen within `close_park_ms` (default 50): today's condition, "another context's job ran".
      That keeps hendrik fault 4 / M-B covered if the firmware does not park in that gap.
  - Then issue the existing unbind DC3 (PA/tag 0, `g5p_rv3_unbind_slots`), wait for it to be consumed, and free the VM and the PM pages.
  - **No `g5p_rv3_park` and no unpark.** pm=prev / close-hold become only the fallback above.
- `g5p_ru_slot_pair` (`drm-render-v3.inc`):
  - Freed pairs go on a LIFO free stack with a per-pair generation counter (`acc+0x1208`'s analogue).
  - The generation is folded into the bind tag `g5p_vm_generation()` (`vm-mutation.h`), so a new owner never presents
    the old owner's tag to the firmware's tag compare `10017ac4`.
  - The PM ID is per context and sticky. A freed PM ID returns to the pool only after its context's last TA retired.
- Lines: `RENDER-V3 close-ios slots= waited_ms= dc=` and `bind … gen=`.

**C. Level 2, host PMGR-off and retained resume (patch 0036; gated `idle_pmgr_off`, needs `idle_fw_policy`).**
- New `drivers/gpu/drm/apple-g5p/idle-gate.inc`, replacing `runtime-idle.inc` for render epochs:
  - Timer: a delayed work queued 40 ms after the event drain saw every ring empty and every job retired (`g5p_boot_drain` tail). If the
    preconditions fail, re-arm at 5 ms.
  - Preconditions under `g->lock` + `event_lock` (`6c81b18`):
    - alive, not stopped/failed, event ring empty;
    - `accepted`/queued == 0, no close or bind in flight;
    - R1 (safe with PMGR on): `(R1+0 & 0x60000000) == 0x60000000`, `(R1+0x1000 & 0x1f) == 0`, `R1+8 == 0`.
  - Power-down sequence:
    1. `R1+0x10 = 0` (mode 3).
    2. `g5p_fender_idle()`, i.e. `R1+0x20000 = 0`, poll bit 4, `0x1000 = 0x10`.
    3. `b->alive = false`.
    4. `g5p_kq_irq_off()`.
    5. Poll `isStableOff` (as freeze-doc §4.4).
    6. `g5p_mmio_gate()`, `fender_ready = false`, `pm_runtime_put_sync_suspend()`.
    7. `d->idle_gated = true`.
  - On any failure: keep power, fail admission, no cycle.
- Resume, from `g5p_rv3_execute` before the first publish (`6ca60c8`):
  1. `pm_runtime_get_sync()`.
  2. `g5p_boot_program_stream(g, true)` over the **retained** `g->boot`.
  3. IRQ on.
  4. Core 0, GPC 0x11 (`g5p_fender_start_observed_q`).
  5. ALIVE wait.

  Bindings and PM state stay as RAM.
  - **Never call `g5p_recover()`**: it builds a new `g5p_boot`, drops bindings and leaks devm.
  - The ALIVE gate `g5p_ds_hook_claim` is unchanged.
- Line `G5P idle-gate off|on ms= why=`. The status goes in `idle_power_status`.

**Expected cost.** A Level-1 park means each job after a gap pays a firmware reboot plus the sampler. That is ~1.3 ms on iOS;
with bells and seeded q it should be single-digit ms, not state 2's 8–32 ms. This is the latency trade-off the owner
is choosing. Measure GPU ms/frame on the desktop and Aquarium.

**Flight order.**
1. **Flight 1:** patch 0034 alone (A; close machinery untouched), with `idle_fw_policy=1`, on `identity-churn.sh`, 48 launches.
   - Clean, with `pol34` reaching 0 between jobs: the freeze is the missing park, and B is licensed.
   - Freeze with parks observed: M-C class. Stop and read the crumbs.
   - No `pol34 = 0` ever: the veto (U5) blocks the park. RE `priv+0x188` before anything else.
2. Then B, then the iOS probe's U2 answer for the slot/PM-ID policy.
3. C last, after A+B soak clean.

## 5. iOS probe package (one session, ≈ 7 min device time)

Built (Mac): `sh scripts/gpu/build-apple-idle-power-probe.sh` → `build/gpu/apple-idle-power/{bin,SHA256SUMS}`.
*(Passage removed: boot-chain or iOS-side tooling detail, out of scope for this repository.)*
- `ios-agx-kdebug`, `power-session.sh`, `allow-sudo-pt.sh`, `metal-triangle`, `ios-ioreport`.

Runner `scripts/gpu/apple-idle-power-probe.sh`:

| phase | time |
|---|---|
| `preflight` | 10 s |
| `upload` | 20 s |
| `IPAD_PW=… install` | 10 s |
| `main` | ~4.5 min |
| `pull` | 20 s |
| `analyze` | host |
| `r1` (optional, last) | 1 min |
| `pull` | 20 s |
| `health` | — |

Output: `build/gpu/apple-idle-power/<stamp>/device`, with `summary.txt` from `scripts/gpu/analyze-apple-idle-power.py`.
- **main (RAM only, no MMIO):**
  - S0: full `fw-blocks` snapshot. This gives the init-time policy/meta/control words and acc/fw objects.
  - S1: 30 s idle.
  - S2: Metal launch, then exit.
  - S3: 10× (A runs 2 s, `kill -9`, B starts at once), with whole firmware-RAM + acc/fw snapshots `c{0,1,2}-{pre,kill,post}`
    around the first three kills. Those include the **DC ring entries**, i.e. the firmware commands of the teardown and of B's first submits.
  - S4: 3× Safari WebGL open/kill (needs `uiopen`; skipped otherwise).
  - The timeline samples every 500 µs: `acc+0xd20/d21`, idle timer `+0x498`, `+0x4e0`, `fw+0x210/0xcad/cae/cc8`,
    `fender+0x8/+0xc`, policy `+4/+8/+0xc/+0x28..0x38`, TA/3D/CL ring cursors.
  - At every mark it dumps iOS's slot tables (`acc+0x1200/1208/1210/1220/1230`: asid, generation, owner, free stack,
    state; `+0x1228` depth; `+0x2f8` PM list head), each read bounded to one heap page. The PM-ID table is in the
    `acc-object` snapshots (`+0x11b0` region).
  - kdebug `0x8593xxxx` runs throughout. IOReport "GPU Stats" (Fender State, restarts) runs at 10 Hz.
- **r1:** idle + 4 churn cycles with Fender `R1+0/8/10/14/1000/1004` loads.
  - Loads happen only while `d21 == 1 && cad == 1 && fender+0xc` (Apple's own R1 state), with cad re-read just before the loads.
  - This remap path has never run on a device: it **may panic iOS**, so run it last. R0 is never mapped.

**What the probe settles:**
- **U1:** across kill → launch, does iOS park (`pol34 → 0`) before B's first ring advance, and does `d21` reach 2 in a 1 s gap?
- **U2:** on destroy, does iOS issue the detach DC, bump the slot generation, and give B a different slot pair and PM ID from A's, or the same?
- **U3:** `R1+0` bits 29/30 and the nibble at a self-park (from r1).
- **U4:** whether every wake reboots the firmware. kdebug `0x85930c18` logs host-waited boots only. A Level-1 self-wake shows as the ring
  consumer advancing after `pol34` 0→N.

**Still unknown until the run:**
- **U5:** the exact veto that blocks the park in our pinned epoch (`priv+0x188`?);
- who reads `acc+0x1208` (generation → tag?);
- the firmware-side retained-state contract for the Level-2 resume. iOS proves it works; our ring cursors must survive it.
