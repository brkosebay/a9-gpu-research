# perf60 clock: the GPU off pstate 1 (340 MHz) toward iOS's P4 (723 MHz)

2026-11-02 night. Part of perf60.md (Hyprland at 60 fps). This note owns the GPU clock; the fill-rate lane is
`a9/perf60-fill` (separate agent, `perf60-fillrate.md`). Kernel branch here: `a9/perf60-clock`. Background: D1's
`nopatch.md` (the policy-state writer, rungs C/C1/C2/E/F).

## 1. What keeps the firmware at pstate 1 on Linux

The firmware chooses its own pstate. The host powers the GPC up at pstate 1 (`R1+0x1000 = 0x11`) and never writes a
pstate itself; on iOS the kext doesn't either (`governor-gate-wait-re.md` §2.11: no host DVFS request/answer). So
"run at P4" means "make the firmware want P4, let it get there, and let the host keep working once it is there".

| # | blocker | status |
|---|---|---|
| B1 | **No perf envelope and no pstate table.** The policy-state writer `0x10008218` and the governor's state-0 arm compute `x = min(policy+0x6f0, policy+0x688, ctrl+0x102c)` and request pstate `q = x / 100` (`policy+0x28`); `x < 100` parks the policy in state 2. Linux writes no table (`meta+0x710..`; only `meta+0x71c = 340` via `boot_meta71c`) and no limits (`L123 boot … limits=0/0/0`), so `x = 0`. | [V] decode (`nopatch.md` §"the writer is a min()", pinned by `nopatch-check.py` §5); rung A/C/E pre-bell `+8=2 +28=0 +38=0`; iOS raw `+0x38 = min(…)` in 6/6 snapshots |
| B2 | **The firmware recomputes `+0x6f0` and `+0x688` from its coefficient block** (10 and 8 store sites, `0x1000a4c8..0x1000cebc`), unless the override words `+0x6f4` / `+0x68c` are nonzero. Seeding the two words alone did not survive (rung E: seeded 100/400, read `+38=0`). | store sites [V]; that they ran before the writer [I] (E); the override fix is rung F, **never flown** |
| B3 | **Every host R0 access requires `(R1+0x1000 & 0x1f) == 1`** (16 sites in the production path: the TYPED_V3 bell `boot-r74f.inc:79`, `g5p_prepare_kick`, both first-ALIVE reads, the control submit, MMU/attach and observe guards). At pstate 2–4 every bell returns -EHOSTDOWN and the desktop stops. Apple's `submitDeviceControl` (`6ca05d4`) accepts any nonzero state nibble. | [V] source; Apple's rule [V] (`wake112-r74e-static-contract.md` §2) |
| B5 | **Load-driven DVFS (iOS's governor) needs the sampler** (`policy+4 = 16`). On the patched path that wedged TA (latency123 boots 2/3, T2/T3: TA consumed, never started), and with the iOS inputs the GPC parks at pstate 0 when idle (B2-flight `state=00000000`), which needs Apple's zero-nibble power arm, which Linux doesn't have. | wedge [V]; parking [I] |

**Can release7 (r73f-patched) take the iOS envelope + full pstate table today, without D1? Yes, with B1–B3 fixed
in the host.** The readiness patch only forces `0x1000d044`'s dispatch verdict; the pstate *request* still comes
from the same writer/governor, so the patched path needs exactly the same envelope as the unpatched one. Its
advantage is that a failure of the envelope (B2) can't stop dispatch: the desktop keeps running at pstate 1. D1's
unmodified-firmware work is not needed for the clock. B5 (real load-driven DVFS) is not attempted here: this step
**pins** the request (no sampler), which is enough to measure what the clock buys.

## Pin 100 on hardware (2026-11-02, `build/gpu/perf60-clock/measure-20261102T213945Z/`): the pin did not hold

- Hop PASS, desktop fine, `bad_lines=0`. `GPUPERF boot pin=100 … limits=3348/100/400 policy688=400/400
  policy6f0=100/100 … q=1`, read from the staging buffer before the copy. Every job from `seq=1` on: `pol8=2/2 q=0
  x=0 req=0/0 ceil=0/0` (706/714; 8 with `pol8=2/1`). `ta_ms` median 10, `td_ms` median 32 (pstate 1, as before).
- **Cause [V decode, I order]: the firmware owns the override words and reloads them from the control object.** On
  every pass it stores `policy+0x6f4 = ctrl+0x1040` (`0x1000a1e4`, `0x1000b388`, `0x1000c568`) and `policy+0x68c =
  ctrl+0x1038` (`0x1000a74c`, `0x1000b10c`, `0x1000c2fc`). The preceding `ctrl+0x103c`/`ctrl+0x1034 != 0` tests choose
  only `+0x6dc` / `+0x674` (`+0x674 = ctrl+0x1034 ? : ctrl+0x1028`); both branches fall through to the override
  stores. Our boot left both control words 0, so the overrides were cleared, `+0x6f0`/`+0x688` were recomputed from
  the empty coefficient block, and the writer saw `x = 0`. Neither the kernel nor the firmware stores to
  `ctrl+0x1034..0x1040` anywhere else. iOS: `ctrl+0x1038 = ctrl+0x1040 = 0` too, with `+0x688 = 400` and `+0x6f0 =
  100..500` computed by its sampler from its coefficients. This also explains rung E, and rung F (overrides in the
  record) would have failed the same way.
- **`ps=ffffffff` = not sampled.** `pstate_probe=3` reads `R1+0x1000` once per job, only at a fresh busy rise
  (previous sample idle, this one busy); `U32_MAX` is the per-job reset value (`drm-latency123.inc:135`). 203 of 714
  jobs had no such rise.
- **`pol34=0` = the firmware's requested pstate.** `policy+0x34` is written by the setter (the requested index), the
  sampler and the post-transition target, not by the host. In state 2 the firmware requests pstate 0 (park) and back.
  Fender at job start showed `0x10` (request for 0 in flight) 22 times and `0x11` (request for 1 in flight) 80 times,
  never a settled 0: a park / re-wake churn around each job, with our bell's `R1+0x14 = 7` wake pulling it back to 1
  [I]. A bell that lands on bit 4 is refused (`-EHOSTDOWN`) under either rule. **This churn is a candidate part of
  the fixed ~8–12 ms TA cost** (perf60 hypothesis 3; for the fill lane). It should disappear once the policy holds
  state 0 at pstate 1 (`pol34=1 ps=00000001` steady).

**Fix: `a9/perf60-clock@4a0eafe14b`** (second commit) writes `ctrl+0x1038 = 400` and `ctrl+0x1040 = pin` before
release, the firmware's own input for its overrides; the boot line prints them as `ovr=400/<pin>`. **Package (DEVICE-READY):** `build/boot/m1n1-linux-perf60clk-4a0eafe14b.bin`, sha256
`46c1aad2d8d3…`, entry `perf60clk-4a0eafe14b`, release
`7.3.0-rc1-perf60clk-g4a0eafe14baa`; config, DTB, initramfs and cmdline = release7's (entry renamed). It supersedes
`perf60clk-9d732490c2`; `build/gpu/perf60-clock/entry` points here, so `perf60-clock-device.sh hop 100` uses it.

## Pin 100 with the control words (4a0eafe14b) on hardware: the pin holds, job 1 never runs

`build/gpu/perf60-clock/device-20261102T221625Z/`, netconsole `build/omarchy/logs/netconsole.log` (~1187090..1187700).

- Boot: `GPUPERF boot pin=100 … ovr=400/100 … q=1`; `R74E ALIVE submit … state=00000001 … ret=0`. **The pin holds:**
  `GPUPERF seq=1 pol8=0/0 q=1 x=100 req=100/100 ceil=400/400 pol34=1`.
- Job 1, 17 s later: DC3 attach published, its bell rang at once (`R74F bell kind=dc3 … path=immediate
  first_state=00000001`) and the firmware consumed it within ~1 ms (`attach-consumed … dc=3/3`). The TA was then
  published **without a bell** (`ta_doorbell=grace-owned`). The grace ended by the 20 ms wall with no ALIVE
  (`R74G ta grace_end=wall … grace_alive=0`), the fallback bell was cancelled unrung (`ta-fallback ret=-125`,
  `R74F bell kind=ta … state=cancelled path=none attempted=0`), and the job stopped at `ta-publish` (`ta_ring=0/0`).
- **`events=1` for the whole boot**: after its first ALIVE the firmware posted no event at all.

**What the firmware waits on: an MTS doorbell, not a poll [V for this boot].** It was not stuck: it consumed the
rung DC3 at once. What changed is the ALIVE stream. In policy state 2 the firmware's loop runs continuously, posts
type-0 ALIVEs (~31/s) and drains its rings by itself. The whole TYPED_V3 path is built on that: job 1's TA bell is
owned by "the first ALIVE after the grace", and jobs ≥ 2 and every 3D phase are published **with no doorbell at all**
(`drm-render-v3.inc`: "both rings are published with no doorbell at all"). In state 0 the firmware behaves as on iOS
(whose kext handles only the first ALIVE): it stays quiet until a doorbell, and we never ring one. [I, worth
knowing for perf60] The no-doorbell, self-drain design, and with it the firmware polling RAM it can't see until the
SLC line is evicted (STATUS "slow frames"), may be artifacts of state 2.

`ps=ffffffff` here is again "not sampled": the probe reads `R1+0x1000` only at a fresh busy rise, and the TA never got
busy. It is not an all-ones read of a powered-down block. Every R1 read in this boot that did happen returned 1
(`first_state=00000001`, the ALIVE submit's `state`/`after`).

**Next rung (low-risk, pin 100): the host rings every phase, Apple's submit model.**
`a9/perf60-clock@9ec288b868` adds `ta1_host_bell` (0600, default 0, read at the job). When job 1's grace ends with the
TA pending, the host takes the bell itself, in the same lock section a decoder would, and rings the same fenced r74f
sequence (`R1+0x14 = 7`, GPC check, `R0+0xb00`). Jobs ≥ 2 and the 3D phases use the existing `render_user_wake=2`
(wake110: the same sequence after every other publish; it has run on hardware, latency113 §3). Tuple:
`perf60-clock-device.sh hop 100 bell` = the pin-100 tuple + `render_user_wake 2` + `ta1_host_bell 1`.
**Package (DEVICE-READY):** `build/boot/m1n1-linux-perf60clk-9ec288b868.bin`, sha256
`4ccc4eed21c9…`, entry `perf60clk-9ec288b868`, release
`7.3.0-rc1-perf60clk-g9ec288b868c2` (W=1: 0 warnings; config, DTB, initramfs and cmdline = release7's; checkpatch 0
errors). `build/gpu/perf60-clock/entry` points here; all knobs default 0, so `hop 100` (no bell) still reproduces the
previous run on it.

- Holds and dispatches: `GPUPERF seq=N pol8=0/… x=100` on every job, `R74F bell kind=ta … state=rang
  path=immediate`, `RENDER-V3 wake … did=rang` lines, `bad_lines=0`, the desktop renders. Then compare `ta_ms`/`td_ms`
  with the state-2 pin-100 run (10/32 ms) and with release7: the cost of polling vs. ringing.
- A GPC that is not on at a bell refuses without an R0 access. For job 1: `ta-window-missed`, `bell_state=` shows
  the state. For later jobs: `RENDER-V3 wake … skip=gpc` and the phase waits to its timeout. That would mean
  state 0 parks the GPC between jobs (Apple's zero-nibble power arm is then the missing piece).
- **MMIO audit for `hop 100 bell` (2026-11-02, after the fill lane's R1 freeze):**
  - `pstate_probe` bit 2 did an unguarded `readl(R1+0x1000)` (no wake write) from the RAM wait loop, at a "busy rise"
    judged from RAM idle words that can stay set after a job retired (tahang1): the freeze class. bit 1 reads the
    PMGR gfx word at job end. The runner now sets `pstate_probe 0`. `ps=` then always reads `ffffffff`, and `pol34`
    (RAM) is the pstate readback.
  - Every remaining GPU-register access is a bell: `g5p_wk_ring()` (`render_user_wake=2`) and the r74f ring
    (`ta1_host_bell`). Both run right after a phase's producer store and before that phase runs. Both do Apple's
    sequence: `R1+0x14 = 7`, read it back, read `R1+0x1000`, and `R0+0xb00` only if the state reads 1.
  - Both are skipped with no access when the phase is already consumed or retired (stamp or type-1), the device
    has faulted or is terminal, or another bell is pending.
  - They can run while the GPC is idle or parked (between jobs, and between a TA's completion and its 3D) [I safe].
    That is Apple's own submit path, and iOS parks at idle. One data point on Linux: the job-1 DC3 bell after 17 s
    idle in state 0 read `first_state=00000001`, no hang.
  - Everything else (`lat123_log` with probe 0, `GPUPERF`, `measure`) is RAM, sysfs or dmesg only.
- Before pin 200: `g5p_wk_ring()` (`render-user-wake.h`) still requires GPC state exactly 1. It must take the
  `gpc_any_pstate` rule too.

## Pin 100 + bells (9ec288b868) on hardware: ~6× faster jobs, one unrung bind

`build/gpu/perf60-clock/device-20261102T225941Z/`, netconsole lines 1303129–1341620 (orchestrator's summary).

- Pin held on 2438/2438 jobs (`pol8=0/0 q=1 x=100 pol34=1`). Bells rang: `R74F bell kind=dc3 … state=rang`,
  `kind=ta … state=rang`, `RENDER-V3 wake … did=rang/rang power=7f/7f gpc=1/1`. Every bell that ran read GPC state 1.
- **2437 labwc jobs: TA median 2 ms (p90 3), 3D median 4 ms (p90 5, max 7), fin median 6 ms**, against 8–10 ms /
  32 ms in state 2 at the same 340 MHz. Polling (state-2 self-drain) cost most of each phase; ringing removes it.
- **Failure at 70.15 s:** a second client's bind, `RENDER-V3 bind slots=10/9 ret=-110 consumed_us=-1 … dc=3->3/5
  mode=ram-dc3`. That DC3 is published in RAM with no doorbell, and the state-0 firmware slept through it. Later the
  kexec unbind did the same (`ret=-110 bad=0x11`). No freeze.
- On the bind job's wake line, `power=00/00 gpc=0/0` sat next to `arm=none/none did=none/none`: the wake never ran
  for that job, so those fields are unset defaults, not a parked-GPC reading.

**RAM-only publications in the TYPED_V3 path** (each store of a ring producer, `ctl[4]`/`ring[4]` of shared
objects `0x6c` DC, `0x60` TA, `0x64` 3D):

| publication | bell before | in bell mode now |
|---|---|---|
| job 1 DC3 attach (`g5p_rv3_attach`) | r74f immediate bell (self-drain if the read is not on) | the same + 2 ms settle of the state read (`gpc_any_pstate`) |
| job 1 TA (`g5p_rv3_publish_ta`, first) | r74g grace, ALIVE-owned fallback | `ta1_host_bell` (9ec288b868) + the same settle |
| TA/3D of jobs ≥ 2, 3D of job 1 | none | `render_user_wake=2` (wake110) + 2 ms settle in its GPC read |
| **DC3 bind** (`g5p_rv3_bind`) | **none** | **`g5p_rv3_dc_kick(…, "bind")`** |
| **spare-pair batch** (`g5p_rv3_spares`, off in the tuple) | **none** | **`g5p_rv3_dc_kick(…, "spares")`** |
| **unbind** (`g5p_rv3_unbind_slots`: client close, kexec quiesce, recovery) | **none** | **`g5p_rv3_dc_kick(…, why)`** |
| boot cmd8, compute attach/server (`lifecycle.inc`, `compute.inc`) | `g5p_prepare_kick` + `R0+0xb00` | unchanged (already rang) |

The legacy fixed/compute DC paths in `drm-render.inc`/`drm-attach.inc`/`render-fixed.inc` are not used by the
desktop and already ring.

**Fix: `a9/perf60-clock@001f8b09c0`.**
- `g5p_rv3_dc_kick()` runs right after the producer store of every bind, spare batch and unbind when
  `render_user_wake=2`. It takes the wake path's guards: event lock, power proof (`g5p_wk_power_ready`), no fault or
  terminal latch, no r74f bell owning a ring, the ring holding exactly this publication.
- Then Apple's order: `R1+0x14 = 7` and its read-back, `R1+0x1000` re-read every 10 µs for ≤ 2 ms until
  `g5p_gpc_ok()`, and `R0+0xb00 = 0x10` only then. One `RENDER-V3 dc-kick why=… did=rang|skip-guard|skip-fence|skip-gpc
  … gpc=… settle=<re-reads>` line per publication.
- The same bounded settle goes into the TA/3D wake's GPC read and, under `gpc_any_pstate`, into `g5p_r74f_ring()`.
  An in-flight read there used to send the job-1 DC3 down the never-ringing r87b self-drain.

**Parked GPC: not written.** If after the wake and 2 ms the state still reads nibble 0, every path skips the R0
write and says so (`skip-gpc`, `ta-window-missed`, `wake … skip`). Two reasons:
- an R0 write to a power-gated RGX is the documented SoC-hang class;
- Apple's zero-nibble recovery arm in `submitDeviceControl` (`6ca05d4`) is not decoded, and a guessed host power
  write (`R1+0x1000 = 0x11`) mid-session under meta6c8=1 is the wake111 hang class.

No run so far has shown a parked read after the wake: 2437/2437 bells read 1. If `skip-gpc` ever appears, decoding
that arm is the next RE item. The post-retirement rule holds: every R1 access is preceded by the wake write, and
R0 only follows a settled powered read.

## Pin 200/400-ready: every R0 guard takes Apple's rule (`a9/perf60-clock@b2881642b8`)

**Package (DEVICE-READY):** `build/boot/m1n1-linux-perf60clk-b2881642b8.bin`, sha256
`3321786a73bb…`, entry `perf60clk-b2881642b8`, release
`7.3.0-rc1-perf60clk-gb2881642b80a`. It carries the DC kick (4th commit) and the guards (5th). Config, DTB,
initramfs and cmdline are release7's (entry renamed); no G5P warnings in the build. `build/gpu/perf60-clock/entry`
points here, so `hop 100 bell` / `hop 200 bell` / `hop 400 bell` all use it.

With `gpc_any_pstate=1`, every check that licenses an R0 access or a bell accepts any settled powered pstate
(`g5p_gpc_ok()`: bit 4 clear, nibble 1..15). A parked GPC (nibble 0) never qualifies.

| check | file | how |
|---|---|---|
| TA/3D bell of `render_user_wake` (`g5p_wk_ring()`) | `render-user-wake.h` | `G5P_GPC_ON()` (5th commit) + 2 ms settle in its R1 read (4th) |
| DC kick: bind, spares, unbind, kexec quiesce (`g5p_rv3_dc_kick()`) | `drm-render-v3.inc` | `g5p_gpc_ok()` + 2 ms settle (4th) |
| job-1 DC3 attach and TA bell (`g5p_r74f_ring()`) | `boot-r74f.inc` | `g5p_gpc_ok()` (1st) + 2 ms settle under `gpc_any_pstate` (4th) |
| `g5p_prepare_kick()` (boot cmd8, compute DC) | `kick.inc` | `g5p_gpc_ok()` (1st) |
| first-ALIVE submit, control submit, policy sample | `lifecycle.inc` | `g5p_gpc_ok()` (1st) + release7's settle |
| DS108 ALIVE proof of the first-ALIVE state | `dirtystart108.h` | `G5P_GPC_ON()` (5th) |
| deferred R74E power proof (`g5p_px_on()`) | `r74e112.h` | `G5P_GPC_ON()` (5th) |
| R0 readback count | `readback.h` | `G5P_GPC_ON()` (5th) |
| compute DC3 attach / kick / server (the bootstrap) | `compute.inc` (7 sites) | `g5p_gpc_ok()` (5th) |
| DC work submit | `work.inc` | `g5p_gpc_ok()` (5th) |
| r21 compute (off) | `drm-compute-r21.inc` | `g5p_gpc_ok()` (5th) |
| fault stage, release ack, MMU readback, r22 snapshot/mmu/observe, render mmu/snapshot/observe | `boot.inc`, `mmu-tables.inc`, `render-fixed.inc`, `drm-render.inc` | `g5p_gpc_ok()` (1st) |
| **left at `== 1` on purpose:** the host's own power-up polls after it writes `R1+0x1000 = 0x11` | `boot.inc:874`, `boot-r74f.inc:176` | the host asked for pstate 1 there |
| **left, off in the tuple:** lab observers | `boot-r80.inc`, `boot-r74h.inc`, `boot-experiment-r27.inc`, `render-r*.inc`, `render-observe-*`, `render-content-r27.inc` | not reached |

The pure headers judge through `G5P_GPC_ON()`. Its default is the old `== 1`, because the host tests compile them
alone. `core.inc` redefines it as `g5p_gpc_ok()` ahead of every include. Host tests on the changed headers:
`test_wake111` 98013090/0, `test_power_guard` PASS, `test_recovery108` 29808587/0, `test_render_recover` 56/0.
`test_wake110` was already stale on release7 (`struct g5p_wk_in` lost `powered` in wake111).

**End to end at pin 200/400** (`hop 200 bell` / `hop 400 bell`):
- Boot: iOS's table `{0, 340, 474, 550, 723}`, limits `3348/pin/400`, overrides `ctrl+0x1038/0x1040 = 400/pin` →
  the firmware's `+0x68c/+0x6f4` → `+0x688/+0x6f0` → `x = pin`, state 0, `q = pin/100`.
- The transition is the firmware's own: its setter `0x1001c88c` writes `Fender+0x1000 = q | 0x10` and polls for
  `q` with no timeout. **Nothing on our side is needed or known:** the iOS kext has no host DVFS answer
  (`governor-gate-wait-re.md` §2.11), and voltage follows in hardware (`power-words-init-re.md` §6). Whether the
  Fender wrapper completes it on Linux is exactly what this run measures.
- Our side only has to accept the new state: every guard above does, and the settle waits out bit 4 while the
  transition is in flight.

**Commands** (one session, after the DC3 fix passes at pin 100):
1. `scripts/gpu/perf60-clock-device.sh hop 100 bell`, `measure 30` (baseline: TA 2 / 3D 4 ms medians).
2. `scripts/gpu/perf60-clock-device.sh hop 200 bell`, `measure 30`.
3. If 200 passes: `scripts/gpu/perf60-clock-device.sh hop 400 bell`, `measure 30`. Then `hypr` and the FPS run (with
   `lat123_log` set to 0 for the FPS number).

**PASS (per pin):**
- `GPUPERF boot pin=<p> … ovr=400/<p> … q=<p/100>`;
- job lines `pol8=0/… q=<p/100> x=<p> pol34=<p/100>`;
- `summary.txt` shows `wake did=rang/rang gpc=0000000<q>/0000000<q>` and `dc-kick … did=rang gpc=0000000<q>`;
- `td_ms` median below the same session's pin-100 value (ideal ×340/474 at 200, ×340/723 at 400);
- `bad_lines=0`, and the desktop renders.

**STOP (hop back with `perf60-clock-device.sh rollback`, unless SSH is gone):**
- `q=2 pol34=1` (or `q=4 pol34=1`) for the whole window, and bells reading `gpc=00000001`: the firmware asked and
  the power controller never moved. Clock blocked, no harm; stay at pin 100.
- A `skip-gpc` storm, or bells reading `gpc=0000001x` with stalls: a transition the Fender wrapper never completes
  (the firmware is stuck in its setter poll). Jobs time out and recovery may fire.
- `pol34=<q>` but `td_ms` not lower: the clock moved and the 3D is not clock-bound (the fill lane's problem).
- SSH and netconsole silent: SoC freeze (e.g. the clock without the voltage). **DFU.**

Risk: **DFU-risk at 200 and above** (a new pstate on Linux; no host power write is added, but the firmware's own
clock/voltage change has never run here). Pin 100 + bell: low.

## Ladder on b2881642b8: pin 100 PASS, pin 200 stops at boot (2026-11-03)

- Pin 100 + bells: PASS (`measure-20261102T232253Z`): 47/47 `pol34=1 x=100`, bells `did=rang gpc=1`, TA 2 / 3D 4 ms.
  The second client's bind `dc-kick why=bind did=rang … gpc=00000001` → `bind ret=0 consumed_us=1001`; the close
  rang too. **Pin 100 + bell is the production setting.**
- Pin 200: `GPUPERF boot pin=200 … ovr=400/200 … q=2 mhz=474`, `R74E power … raw=00000001`, `R74E ALIVE submit …
  state=00000001 after=00000001 ret=0` (so the cmd8 doorbell rang on the first-ALIVE path), a second ALIVE, then
  `DC timeout consumer=0 producer=1 target=1` at the bootstrap's `control-wait`. No job ran. No freeze.

**(b) "the boot control-submit isn't rung at q=2": ruled out.** The cmd8 goes out on the first-ALIVE fast path
(`g5p_r73e_irq_submit`), whose two state reads passed (`state/after=00000001`) right before the doorbell. The later
`command control-submit` returns at once because `control_submitted` is already set. The firmware received a rung
cmd8 and never consumed it. At pin 100, with the same path, it consumed it. Something the firmware does after
release, only when `q = 2`, never finishes.

**(a) what the firmware is stuck on: two candidates, one read decides the first.**
1. **The GPU PSINFO records for states 2–4 are not what the hardware needs on our boot path [I, lead].**
*(Passage removed: boot-chain or iOS-side tooling detail, out of scope for this repository.)*
   - The firmware's setter (`0x1001c88c`, mode 2) writes `Fender+0x1000 = 2 | 0x10` and polls for 2 with no
     timeout. A record Fender can't apply (zero PLL, valid = 0, or missing rail codes) leaves the firmware in
     that poll forever, which is exactly a cmd8 never consumed.
   - The SOC rail's records at `0x68000` are intact on Linux (memclk read 1), so the PMGR init ran in part.
2. **The firmware's clock-change path hangs before Fender completes [I].** Per `power-words-init-re.md` §0.2,
   `Fender+0x1004` (the GPU clock) is written only in `0x1001cec8`, whose first action is the SLC/BIF/MMU drain
   `0x1001b638`. Pin 100 (q = 1, the current state) may never take that path; q = 2 must. If that drain waits on
   an RGX condition that behaves differently on Linux, the firmware stops there.
   - The voltage sequencer is not the suspect: Linux reads `0xa0000 = 0` (automatic, iOS's runtime mode) and the
     SOC rail moved under it (perf60-hendrik §3). Its routing word `0x1782` should be checked in the same read.

**Device check, read-only, safe at any GPU state** (always-on PMGR only, `/dev/mem` O_RDONLY + PROT_READ, no GPU
MMIO), runnable now on the pin-100 production boot:

*(Device/host command block omitted; it targets the private workspace.)*

It prints:
- the 16 GPU PSINFO records, raw and decoded (MHz, PLL valid, core and buck8 codes and mV);
- for each of idx 1–4, iOS's view from the live ADT `sgx/perf-states` (which iBoot decodes from these same
  registers) and the word0 the LLB writer would leave (`48255022`, `6a24f021`, `75313042`, `8a2f1041` for
  340/474/550/723 MHz at 675/781/815/881 mV);
- the sequencer words `0xa0000..0xa003c` (mode, routing, live codes), the SOC state and the GPU power gate;
- a final `RESULT psinfo_states_1_4=MATCH|DIFFERS <idx>` line.

**Fix proposals, by outcome:**
- **`DIFFERS` for idx 2–4** (zero, `valid=0` or other values) → cause 1. The Apple way is to do what LLB does:
  write the GPU PSINFO records before the GPU is first powered.
  - The place is m1n1 (our LLB stand-in), or the kernel's PMGR setup before `boot_gpu_perf` releases the firmware.
  - Values: the PLL triples from the LLB descriptor table (§4.2, proven) and the core codes from iOS's ADT
    (106/117/138).
*(Passage removed: boot-chain or iOS-side tooling detail, out of scope for this repository.)*
  - Until then: pin 100.
- **`MATCH`** → cause 2 (or a Fender-side handshake). The next build adds one RAM-only line at the bootstrap's DC
  timeout: `policy+8/+0x28/+0x34/+0x38`. `pol34 = 2` means the firmware reached the setter: Fender/hardware didn't
  complete. `pol34 = 1` means it stopped earlier: the `0x1001cec8` drain. Then RE that drain's wait against an
  RGX register.
- Either way, nothing on our side writes the GPU clock or a voltage; neither iOS's kext nor the firmware does.

## psinfo MATCH → the clock-change drain; Hyprland's 3D fault on the bell path (2026-11-03)

**PSINFO is not the cause:** `RESULT psinfo_states_1_4=MATCH`. Every record equals LLB's and iOS's (`[2] 6a24f021` core
106 / buck8 77, `[4] 8a2f1041` core 138 / buck8 124). The sequencer is automatic with routing `0x1782`, and the GPU gate
`PMGR+0x80340 = 0x1ff`.

**What the firmware's clock change waits on [V decode, I that it is the stall].** `0x1001cec8` calls
`0x1001b638` (the SLC3 flush/invalidate), then `0x1001cce0`, then the Fender write/read (`0x10007a44`/`0x10007a6c`).
`0x1001b638`:
- `R0+0x688 = 7`, then `0x100018c8(0x688, expect 0, mask 7)`: poll until the three flush bits clear;
- `R0+0x1728 = [GbP+68]`, then `0x100018c8(0x1728, expect 0, mask 1)`.
`0x100018c8` re-reads `RGX[reg]` until `(v & mask) == expect`, and checks an abort function (`0x1000d138`) on each
miss. If one of the three caches behind `0x688` never acknowledges on Linux, the firmware sits there. That would also
explain why `meta+0x6d4 = 1` (a tick-rate caller of the same routine) wedged TA in latency123, and why pin 100 (no
clock change) never enters it.

The `0x688` flush (`1 << n`, n = 0..2) appears elsewhere only in `finish24`'s unused L5 arm. Whether iOS ever runs it:
iOS's `meta+0x6d4 = 0`, but iOS changes pstate under load, so it must run it on every clock change.

**Package (DEVICE-READY): `build/boot/m1n1-linux-perf60clk-36fda56931.bin`, sha256
`e41938b3372f…`, entry `perf60clk-36fda56931`, release
`7.3.0-rc1-perf60clk-g36fda5693161`** (`a9/perf60-clock@36fda56931`; no G5P warnings; release7's config, DTB,
initramfs and cmdline). It carries the A/B gates below and the dc-timeout line. `hop 100 bell` uses it.

**Next device step (built, `a9/perf60-clock` 6th commit).** With `boot_gpu_perf` set, a DC timeout now prints `GPUPERF
dc-timeout pin=… pol8=… q=… x=… pol34=…` from RAM.
- `pol34 = 2` means the firmware reached the setter, so the drain finished and Fender didn't complete.
- `pol34 = 1` means it stopped before the setter, i.e. in this drain.
- If it is the drain, the next rung is one guarded R0 read of `0x688`/`0x1728` at the stall (wake, `g5p_gpc_ok`,
  then the read; the firmware is alive and the GPC on, no job retired). That shows which flush bit never clears.
  The fix side is then the SLC configuration Linux never makes (iBoot/the kext), RE item.

**Hyprland's 3D fault on the bell path.**
- Facts:
  - perf60cm `hypr-adbe-20261102T233624Z` and `…233736Z` each faulted once (`G2 type=4 word1=0x200`, MMU page
    fault, `state=00000008/81810581`, quickshell's slots 10/9, the 3D right after consume).
  - The five Hyprland sessions on state-2 kernels (perf60, perf60n ×4, perf60c, perf60clk-9d732490c2: 700–1071 jobs
    each) have `why=3d-fault` = 0. labwc alone on the bell path never faulted.
  - The same state word was Hyprland stage 1's fault on desk-next (border shader, inferred, refused in Mesa since).
- **No fault address is available** without breaking §9.7. The event carries only `EVENT_STATUS.MMU_PAGE_FAULT`
  (`dsx-nx70-event-bit9.md`). Requester, context and VA are in RGX `0xE150/0xE158/0x12B0/0x12C0`, readable only
  after the fault.
- **No 3D overlap on the host.** Jobs are serialized: a job's TA is published only after the host decided the
  previous 3D complete. What the bells remove is the firmware's polling gap:
  - 4406 (labwc, 8/7) 3D event at 217.7695;
  - 4407 (quickshell, 10/9) TA published at 217.7708 and done at 217.7721;
  - its 3D published at 217.7737 and faulted at 217.7739.
  So the suspects are work the firmware still does after the 3D event (PM/region deallocation, the slot or MMU
  context switch, its own SLC maintenance) racing the next context's job [I].
- **A/B knobs** (6th commit, runtime, 0600, read at every bell, default 0 = today's bell mode, active only with
  `render_user_wake=2`; between a phase's producer store and its bell; RAM, sleeps and barriers only):

  | arm | knob | meaning |
  |---|---|---|
  | (a) | `bell_gap_us` (e.g. 2000) | the TA bell no sooner than this after the previous job ended |
  | (a) | `bell_idle_ms` (e.g. 5) | the TA bell first waits up to this for the 3D engine idle words to clear |
  | (b) | — | not built: the state-0 firmware does not drain unrung phases (job-1 TA and DC3 bind proved it); every 3D would hit its timeout |
  | (c) | `bell_3d_delay_us` (50 / 200) | `mb()` and this delay before the 3D bell |
  | (c) | `bell_touch=1` | the Normal-NC read of the firmware pages right before each bell |
  | (d) | `bell_ctx_gap_us` (e.g. 2000) | `mb()` and this delay before the TA bell of a job whose context differs from the previous job's |

  One `RENDER-V3 bellgate seq=… engine=… waited_us=… idle_ok=… switched=…` line per gated bell. Set with
  `echo N | sudo tee /sys/module/a9_gpu_drm/parameters/<knob>` on the live boot; no reboot between arms. Order:
  (d) 2000 → (a) `bell_gap_us` 2000 → (a) `bell_idle_ms` 5 → (c) delay 200 → (c) touch. One arm at a time, each for a
  Hyprland minute or until the first `why=3d-fault`. In-boot recovery brings the session back after a fault
  (`GPU-RECOVER … ret=0`); a terminal fault needs a hop.

## Flight (b): never-park + bells is the lever; the multi-context fault is not Hyprland's (2026-11-03)

- Fixture v3 on perf60cm pin 100 + bell (labwc only, `build/gpu/perf60/flight-b/`): the "uniform throttle" is gone.
  `fill_clear` 3D 12 → 2 ms, `solid` 18 → 2, `blit` 36 → 4, `solid_alu16` 62 → 8. A full-panel clear runs at
  ≈ 650–780 Mpx/s.
- In the mem-12 arm, labwc's own context (8/7) faulted **in the TA right at consume** (`why=ta-fault`), with the
  fixture as the second context. So: two active contexts plus back-to-back jobs, and a fault at consume on the next
  context's job, TA or 3D.

**Where the race most likely is [I]: the host's own per-job writes, not the doorbell.** Every TYPED_V3 job ≥ 2
starts, before anything is published, by rewriting pages the firmware also uses:
- `g5p_rv3_pm_rebuild()` rebuilds the device's single PM pool, list and free pages ("whichever context the job
  belongs to");
- `g5p_ru_job()` rewrites the one shared TA work-record page and the one shared 3D page.

With bells this happens about 1 ms after the previous 3D event; in state 2 the firmware's park gap (several ms)
separated them. Whatever the firmware still does after posting the 3D event (PM free-list or parameter-buffer
teardown, its stamp/finish bookkeeping) can then meet a rewritten PM pool or record page. The next TA allocates from
that pool (a TA page fault at consume), and the next 3D reads that record (a 3D page fault).

**The 36fda56931 bell gates can't test this:** they run after those writes, so they only test the doorbell's timing
and ordering. `a9/perf60-clock` 7th commit adds the decisive arm, gates **at job start, before the first host write**:
- `job_gap_us`: wait until this long after the previous job ended;
- `job_idle_ms`: then wait up to this (RAM) for the TA and 3D engine idle words to read zero, as the retire predicate
  reads them.
One `RENDER-V3 jobgate seq=… waited_us=… idle_ok=…` line per gated job.

**Package (DEVICE-READY):** `build/boot/m1n1-linux-perf60clk-f93ad3e997.bin`, sha256
`0f544339024e…`, entry `perf60clk-f93ad3e997`, release
`7.3.0-rc1-perf60clk-gf93ad3e9976e` (`a9/perf60-clock@f93ad3e997`; no G5P warnings; release7's config, DTB,
initramfs and cmdline). It supersedes `perf60clk-36fda56931` and carries every bell gate as well.

**A/B order on the new package** (one arm at a time, the previous knob back to 0):
1. `job_idle_ms 5`
2. `job_gap_us 2000`
3. `bell_ctx_gap_us 2000`
4. `bell_idle_ms 5`
5. `bell_3d_delay_us 200`
6. `bell_touch 1`

A job-gate arm that holds while the bell gates don't means the host rewrote shared pages under the firmware. A
`job_idle_ms` arm whose lines read `idle_ok=0` (the 5 ms expired) says the idle words stay set after the work, the
tahang1 pattern. Then `job_gap_us` is the arm that tells.

**The proper fix (the Apple way, not a delay).** iOS never rewrites a shared job record or a shared PM pool between
jobs: each submission has its own command memory, and the firmware owns PM allocation. Our r22-era layout reuses one
TA page, one 3D page and one rebuilt PM pool for every job of every context. That only works while something
guarantees the firmware is done with them, and state 2's polling gap did that by accident. Two options:
- Structural: per-job record slots, ring-indexed like the work rings (the firmware reads the record the ring entry
  points at), and the PM pool set up once per context or device, never rebuilt per job.
- If the rebuild has to stay: the firmware's completion signal for the PM teardown. RE item: the store order after
  the 3D completion event in the 3D finish path, i.e. which RAM word the firmware writes last (the PM save serial
  `pm+0x80` is already required, so the remaining work is after it).

The A/B result tells which of the two writes matters (PM pool vs records). On a context switch itself, the firmware's
per-slot work is the catalogue-tag compare at dispatch: `host_generation[N]` vs `cached_generation[N]`, and an `e138`
invalidation it waits for, as in the DC3 handler. That work is synchronous inside dispatch, so it is less likely to
be the race.

## Structural fix: per-job record slots and the PM pool built once (`a9/perf60-clock@456b65d52b`, 2026-11-03)

The 8th commit on `f93ad3e997` adds two knobs. Both are latched at the epoch's first TYPED_V3 attach and both are
default off, so the r22 layout is unchanged unless they are set. A `RENDER-V3 layout job_slots=… pm_once=… slot1=…`
line records which layout the epoch uses.
- `render_user_job_slots 2`: job `seq` writes its command, its W record and its microsequence into slot
  `(seq − 1) % 2` of the channel page:
  - slot 0 = the r22 offsets (`CMD +0x300`, `W +0x400`, SKU);
  - slot 1 = `+0x1c00 … G5P_RU_SLOT1_END`, clear of TQ, the stamps, the dependency object and the r25 holder.
  The job's two pointer-ring entries name its own slot. So a job never rewrites the record that the firmware used
  for the job before it. Every reader follows the slot: the retire sample, the `td_why` command, the refusal print,
  the publish lines and the receipt dumps.
- `render_user_pm_once 1`: the PM pool, list and F are built only at the epoch's first attach, and never by the host
  between jobs. `g5p_rv3_pm_rebuild()` is skipped. The TA's tag6 record makes the firmware rebuild F, as iOS does
  (iOS creates the PM once per work queue; `freelist-lifetime-production-fix.md`).
- The `job_*` and `bell_*` gates of `36fda56931`/`f93ad3e997` stay as A/B knobs.
- §9.7 holds: nothing here touches a register; the new code is RAM layout only.

**Host tests.** `scripts/gpu/perf60-host/test_job_slots.c`: 1310 checks, 0 failures (gcc with ASan/UBSan, in the
kbuild container):
- Two contexts (slots 8/7 and 10/9) alternate 64 jobs with zero gap. Before each write, the slot of the job still in
  flight is snapshotted; it is byte-identical after the write.
- Slot 0 is byte-identical to the legacy `g5p_ru_job()`.
- The ring entries name the job's own slot.
- Retirement is read through the right slot.
- The legacy layout rewrites the in-flight record on all 2 × 63 jobs. This is the hazard the slots remove.

The desk-next suite on `456b65d52b` is green (`build/gpu/perf60-clock-check9.log`).

**The audit exception for the bell-mode unbind (accepted by the orchestrator).** In state 0 the firmware consumes
only rung commands, so the unbind that a close publishes must be rung. `g5p_rv3_dc_kick` is Apple's submit sequence,
in bell mode only:
- `R1+0x14 = 7` and its read-back;
- `R1+0x1000` re-read until a settled powered pstate (≤ 2 ms);
- then, and only then, `R0+0xb00 = 0x10`.

It runs under the wake path's guards: the event lock, power proof, no fault or terminal latch, no r74f bell pending,
and the ring holding exactly this publication. It never touches a retired job's state. On skip-gpc it logs and
returns, with no fallback register write.
- `multiclient2-host/audit_mc2.py`: listed in BOUNDARY with this justification.
- `mcfold2-host/audit_kq.py`: listed in `NARROW`, which is not walked as RAM-only. Instead the audit checks its shape
  mechanically:
  - the bell-mode return (`render_user_wake != G5P_WK_ALWAYS`) comes before the first register access;
  - there is exactly one `->rgx` access, and it comes after the `if (!g5p_gpc_ok(gpc)) { … goto out; }` skip.
  Two planted mutants are each caught: the return removed, and an R0 write before the skip.
- **The kexec quiesce path stays bounded.** The unbind's wait is `g5p_rv3_dc_wait()`, bounded by `G5P_RU_BIND_MS`.
  On a timeout it returns `-ETIMEDOUT`, marks `dc_pending`, and the quiesce goes on to its power cycle. The bell run
  logged `unbind ret=-110` and the hop proceeded. The kick adds at most the 2 ms settle. If the firmware never
  consumes, kexec still proceeds after the bound.

**Package (DEVICE-READY):**
- payload `build/boot/m1n1-linux-perf60clk-456b65d52b.bin`, sha256
  `b8a1b77a88b2…`;
- entry `perf60clk-456b65d52b`, release `7.3.0-rc1-perf60clk-g456b65d52b9a`;
- no G5P warnings; release7's config (byte-identical), DTB, initramfs and cmdline.

`perf60clk-662bdbc980` (next section) contains it with every knob at its default. The layout of this package is kept in
`build/gpu/perf60clk-456b65d52b-pkg/` (`PERF60_CLOCK_PKG=build/gpu/perf60clk-456b65d52b-pkg`). Run plan: §3a.

## MMU invalidation: what the park did for free, and the A/B arm (`a9/perf60-clock@662bdbc980`, 2026-11-03)

Job-gate A/B part 1 (orchestrator, `build/gpu/perf60/jobab/`): neither `job_idle_ms 5` (idle within 56–121 µs, then
`lost … slots=10/9 why=3d-silent`) nor `job_gap_us 2000` (`terminal kind=fault why=3d-fault`) prevents the fault. A 2 ms
gap at job start would cover any firmware tail after the 3D event. This argues against a host-rewrite timing race and
for stale state that the park cycle used to wipe.

**What invalidates a user MMU context: the firmware, statically [V]** (`build/gpu/firmware-re/10000000.minim.dis`,
`80000000.minim.dis`). Every `e138` write goes through `80009030(ctx, all, type)`: type 1/2/3 = mask 4/2/1 (PC/PD/PT),
`all` adds `0x800`, then `e138 = (ctx << 3) | mask` and a poll. Its callers:

| caller | when | what |
|---|---|---|
| `10017ac4` | at each TA kick for the TA slot, at the 3D tag1 handler for the 3D slot | `diff = host ^ cached`: bits 31:22 → PC, else 21:12 → PD, else 11:0 → PT, else nothing; then `cached = host`. **One** invalidate per kick, the highest changed field (`10017b3c..10017bd8`) |
| DC op 3 (`1000218c`) | bind/unbind | CBASE from `0x86[S]`, tag copy, PC invalidate of S |
| DC op 4 (`10002014`) | host DC command | `80009030(0, 0, 1)` = **context 0** (the firmware's own VM) PC, plus a D-cache range flush (`1001eef0`) and `control+0x1024++`. Not a user-context command |
| `1001873c`, `10018e5c`, `100193a8` | TA/3D PM paths | the PM requester triples (contexts 1..6), firmware-owned |
| `1001b638` (direct `e138 = 0x804`) | boot (`1000515c`); **every clock change** (`1001cec8`); the tick when `meta+0x6d4 ≠ 0` (iOS: 0 live); the DM queue scan (no static caller) | the full flush: `11f00 = 1`, `688 = 7` + poll, `1728 \|= 0x1f` + poll, SLC all-context (`e230 = c03`), then **all-context PC** `e138 = 0x804` |

DC ops 5/7/8 sync and complete (`10021d48`, `1001fea0`); ops 6/9 (`10005f78`, `10005d04` + `1001ee50`) don't reach
`80009030`.

**Answers.**

1. *Our VM_BIND/unmap path* already runs Apple's protocol:
   - PTE edit, then `g5p_table_clean_page` of the root and every table, then `dsb(sy)`;
   - the packed PC/PD/PT generation tag goes into `0x84[S]` for both slots, then `dma_wmb()`;
   - the firmware invalidates at each slot's next kick.

   Resident VMs never prune tables (`g5p_vm_prune()` runs only before attach), so table pages are not recycled under
   the walker. **There is no Rogue-style MMUCACHE command for user contexts in this firmware**; the table above is the
   complete set. iOS sends nothing extra; the only extra flushes on iOS are the clock changes and the power gating
   between bursts. The never-park bell path at a pinned pstate has **neither**: no clock change, no park. So if a walker
   cache goes stale, nothing else drops it.

   Both halves of Apple's protocol (the host producer `6cabe70` bumps one field per publication; `10017ac4` issues
   one) assume that a PC or PD invalidate also drops the levels below it [I, by design]. If that holds for our
   hardware, the edit path has no hole.
2. *The context switch.* MMU caches are tagged by context (the `e138` context field). Each client has its own slot
   pair, its own tag and its own CBASE, and the compare is per slot. So a switch between two bound VMs needs no
   invalidate **if** that tagging holds; nothing in the firmware does one either. Two gaps found:
   - **Spare adoption** (`g5p_rv3_adopt`) copies the new VM's catalogue into the spare's root page, so the CBASE is
     the same and the content changes. It then relies on the VM's tag having a PC field different from `SPARE_TAG =
     0x00400000` (PC = 1). If the VM's PC count is 1, the firmware takes only PD/PT and the PC cache keeps the spare
     root's lines. This is rare, and bit 1 of the arm closes it.
   - **The PM's requester contexts 1..6 are shared by every VM** and are managed only by the firmware's own
     per-job triple invalidates. The host can't reach them. They stay open.

**The arm: `render_user_mmu_inval` (bitmask, default 0, read at each use, so it can also be set live in sysfs).**
All of it is RAM only, through the firmware's own compare (no host `e138`, §9.7):

| bit | what |
|---|---|
| 1 | every edit publication (MAP/UNMAP, RT edits, spare adoption) advances the VM's PC counter, so both slots' next kick takes the PC-level invalidate (`e138 = (S<<3)\|4`) |
| 2 | a bound context's job after another context's job moves its slots' host tag to a fresh PC field before it publishes anything |
| 4 | an NC read of every table line before the tag store (`g5p_rv3_fw_touch()`'s visibility read, for the VM's tables) |
| 8 | the bit-2 retag on every job of a bound context |

The retag leaves `vm->mutation` alone: VM_BIND of a render VM takes no core lock, and an edit still checks its own tag
only against the cached tags. Field-local wrap is safe: the firmware only XORs, and the helper never returns 0 or a
cached tag. Lines:
- `RENDER-V3 mmu-retag seq=… why=switch|every host=… cached=… tag=…`;
- `RENDER-USER tag=… mmu_inval=… cached=…` per edit (the default-0 line is unchanged).

**Tests:**
- `scripts/gpu/perf60-host/test_mmu_inval.c`: 698373 checks, 0 failures. It covers:
  - exhaustive PC fields;
  - the edit counter advance (1..3, landing on the helper's tag);
  - 4096 alternating jobs of two contexts, every kick a PC kick in a model of `10017ac4`;
  - the due table.

  Two planted mutants are caught.
- `audit_ram_only` and `audit_mc2` pass; `g5p_ru_mmu_pc_tag` (pure) is on their allow lists. The desk-next suite on
  `662bdbc980` is in `build/gpu/perf60-clock-check11.log`.

**Package:** `perf60clk-662bdbc980` (§3a).

### 3a. Run plan (orchestrator; pin 100 + bell, the owner's session, Hyprland + quickshell)

The faulting setup is fixed for every arm: `scripts/gpu/perf60-clock-device.sh hop 100 bell <layout> [mmu<N>]`, then
`hypr`, then 10 min of Hyprland + quickshell, then `measure 30`. Arms, one at a time:

1. **`hop 100 bell none mmu15`**: every MMU-side invalidation the host can ask for. If it holds 10 min with 0 faults,
   the mechanism is a walker cache (or table visibility). Bisect with `mmu1`, `mmu2`, `mmu4`, then `mmu8`. Bits are
   live (`echo N | sudo tee /sys/module/a9_gpu_drm/parameters/render_user_mmu_inval`), so a bisect needs no hop.
2. If arm 1 still faults: the MMU caches are not it, under the hierarchical-PC assumption. Next, **`hop 100 bell
   both`** (the structural layout), then `both mmu15`.

**PASS** = 10 min of Hyprland + quickshell, `bad_lines=0`, ta/td medians ≈ 2/4 ms. The retags cost an MMU refill per
kick; `measure` reports the ta/td change. `summary.txt` has the `mmu-retag why=` counts, `edit_tags_mmu=` and the
`RENDER-V3 layout` line.

**Risk:** the same as `hop 100 bell` (pin 100 proven warm-recoverable). The arm writes RAM words only and adds no
register access.

## Results on 662bdbc980, and what they narrow (2026-11-03)

Device (orchestrator, `build/gpu/perf60/mmu/`, `jobab2/`):
- every job/bell gate still faults;
- `mmu_inval=15` engaged (100 retags, `every`/`switch`; 69 edit tags with `mmu_inval=f`, including the failing job's
  own `why=switch` retag) and still lost seq 4260 (`3d-silent`);
- `both` (slots + pmonce) faults at about 1 min; `both` + `mmu15` at about 4.5 min.

Offline, from the same logs and the earlier `perf60-clock/hypr-adbe-*` runs:
- **Every failure is the 3D of slots 10/9 (quickshell), on the first job after another context's job.** In the control
  run, Hyprland ↔ es2gears (8/7 ↔ 12/11) switched about 177 times each way with no failure. Its one 8/7 → 10/9 switch
  failed.
- Edits to 10/9's tables since its last job don't matter: 4260 (bell-idle run), 4480 and 12280 failed with none. So
  that context's own translations were unchanged from a job that had just succeeded.
- The idle gap doesn't matter either (0 ms or 5.8 s).
- In state 2 (park on, `hypr-adbe-20261102T213852Z`) the same switch into 10/9 passed 191 times. Bell runs that get
  past 10/9's first 6–7 jobs survive 30–39 of them.
- The event ring loses nothing (the only index jump is the epoch reset). At `3d-silent` the 3D idle words still read
  busy with the job's W (`00000001,c0258000`).
- Every render context's targets start at the same private VA (`r->private_mm` over `[G5P_RU_PRIVATE_VA, +SIZE]`,
  aux pages at the base), with different PAs.

## Fault address, the Apple way (`a9/perf60-clock`, 11th commit)

**(1) Does the firmware keep the address in RAM? No [V].** Its fault path (source 4 → `1001a494`):
- reads `e150` and then `e158` with a 64-bit load;
- classifies the requester (bits 11:6) through `[GbP+340]`;
- writes only the class and state into the companion record (root+0x3980/0x3994/0x3998);
- posts event 4 with state words (`8/81810581`), which are not the status. Read as an `e150`, they would give context
  24, which no live slot has.

`100219b4` (the event post) is called only on its unknown-requester paths, with the requester number. iOS's kext reads
the banks itself by MMIO in its fault handler (`6ca5c14`, accelerator virtual+740).

**(2) The guarded read.** `render_user_fault_read` (live, default 0): bit 1 = at a TA/3D fault event, bit 2 = also at a
silent/timeout phase. It runs in the failed-phase branch, before the loss decision and the terminal latch, at most 8
times per boot:
- bell mode only, under the event lock;
- the wake path's power proof and `!stopped`. The fault has already latched `b->failed`, so that flag is not a guard
  here;
- Apple's wake: `R1+0x14 = 7` and its read-back, then `R1+0x1000` re-read until a settled powered pstate (≤ 2 ms);
- only then four reads, `R0+0xe150/e154/e158/e15c`. Earlier kernels (r52/r56/r57/r68) read the same registers while
  powered. Every skip logs and leaves.

**Risk: DFU-risk-low (owner accepted).**

Lines:
- `RENDER-V3 fault-read … did=read|skip-* power= fence= gpc= settle= e150=hi:lo e158=hi:lo`;
- per valid bank, `RENDER-V3 fault-decode … va= read|write type= level= requester=N/NAME sideband= context=`. Names
  come from the iOS table `6ff5ed8`, read from the kernelcache: 56 units, META … PBE1_TEXAS5;
- the incoming context's RT list;
- the **VM edit log**: a device-wide ring of 1024 MAP/UNMAP/RT-create/RT-destroy records, each with pid, comm, VM, VA,
  size, handle and offset, recorded whenever the knob is nonzero. On the read it prints the edits whose range covers the
  fault VA (any VM, newest first, with `ago_ms`), then the faulting VM's last 16.

Host test: `scripts/gpu/perf60-host/test_fault_decode.c`, 100006 checks, 0 failures. It covers the README's two
hardware faults (CDM read at 0x1_0005_c000; PBE0_TEXAS0 write at 0), a field round trip, the range test and the
names. Audits pass; the log's `strscpy` was added to the allow lists of `audit_ram_only` and `audit_mc2`.

**Also in the 10th commit (A/B arms, default off):**
- `render_user_switch_park_ms` (live): before a switch, `ctrl+0x1040 = 50` for N ms (state 2: the firmware may park),
  then the pin back, with a `switch-park` timeline line;
- `boot_meta6d4`: the firmware's full flush every tick. DFU-risk: unbounded firmware polls;
- with `lat123_log`, a `RENDER-V3 switch … rts=` line per switch.

**Run (orchestrator):** `perf60-clock-device.sh hop 100 bell both mmu15 fread3`, then `hypr`, then the owner's session
until the fault, then `measure 30` (its `fault.txt` keeps the read, the decode and the edit log). Use
`PERF60_CLOCK_PKG=` for the 11th commit's own package directory (below); the shared `build/gpu/perf60-clock/` is left
on 662bdbc980 while the campaign runs.

**Packages (DEVICE-READY; release7's config byte-identical, DTB, initramfs and cmdline; no G5P warnings; desk-next
check green):**
- `perf60clk-c3f63fc64f` (11 commits, everything above): payload `build/boot/m1n1-linux-perf60clk-c3f63fc64f.bin`,
  sha256 `2a4dc8dc220c…`, release
  `7.3.0-rc1-perf60clk-gc3f63fc64f13`, `PERF60_CLOCK_PKG=build/gpu/perf60clk-c3f63fc64f-pkg`.
- `perf60clk-c7a5fae87f` (10 commits): sha256 `95dec7854bbc…`,
  `build/gpu/perf60clk-c7a5fae87f-pkg`.

## The fault named: the PM's ALIST1 at VA 0; per-context PM state (12th commit, 2026-11-03)

Device (orchestrator, `build/gpu/perf60/fread/`):
- `e150 = 00000000:0060d199`: a **read, page invalid, level 1, requester 6 = PM, context 6, VA 0**, at quickshell's
  first 3D after its startup edits. It is deterministic.
- `tick7` changes nothing. `DEFER_FREE` changes nothing (buffer lifetime ruled out).
- The faulting context varies (10/9 and 8/7, TA and 3D).
- It never happens in state 2.

**What context 6 is [V].** `f090 = 0x060405` = {VCE1 = 5, TE1 = 4, **ALIST1 = 6**}. That is the 3D bank's PM
allocation-list requester, a firmware-owned PM translation, not a user slot. Level 1 means the walk got past the
catalogue: the PM context's tables exist and hold no mapping for VA 0. So it is a null pointer in the PM's own
context data. The lane base itself is not 0.

**What the PM context is, and how it is shared [V].** The PM record:
- control is `pm+0..0x7f` (`g5p_ru_pm_pool`, rewritten per job unless `pm_once`);
- the selected state **S** is `pm+0x80..0x13f`;
- the aux backing is 5 pages (S+a8 = aux, S+a0 = aux+0x80, S+b0 = aux+0x10080, S+b8 = list+0x40;
  README "Proven sizing").

The fresh TA loads the PM context from aux (`240/248/2d8 ← S.a8/b0/a0`, then `290/198/258 = 1`) and clears S+bc. TA
finish saves bank 0 into S (`1001886c`) and adds `S[8] + 4·S[0]` to S+bc (`80003350`). The 3D start restores bank 1
from S (`10018e5c`, the `10018f20` copy loop, nx69 §3). S is built once at attach (`g5p_ru_pm_state`) and **never
rewritten by the host**: `pm_rebuild` touches only control, the list and F. So every context's job starts from the PM
state the previous job, of any context, left in S and aux.

iOS acquires a ParamBuffer ID per prepare from a 127-entry pool (`6cb9afc`) and builds control/S/aux per PM
(`6cb2378`). This was risk R3 of `docs/gpu/multi-client-design.md`: "PM ID 0 and record 0 serve every VM … Fallback:
a PM record per context."

The firmware also has a resident-PM fast path [I]. The TA-side engine state machine `80002f5c` caches a record
pointer (`+0x828`) and the value it points at (`+0x82c`), and skips the PM load (`8000a9e4 → 10005ea8`) while that
value is unchanged. A power-down resets such a cache, and never-park doesn't. Which word it caches is not yet pinned.

**The arm: `render_user_pm_switch` (live, default 0).** RAM only, between jobs (the previous job retired, this one
has published nothing):
- **1:** a context's job after another context's job starts from attach's fresh state (S rebuilt by
  `g5p_ru_pm_state`, aux zeroed and cleaned);
- **2 (iOS-shaped):** each context keeps its own S + aux, saved after each of its completed jobs and restored when it
  follows another context's job; fresh the first time.

Line: `RENDER-V3 pm-switch seq= slots= mode= how=fresh|restore bc_before=`. Mode 2 still shares PM ID 0, control and
the pool. If it holds, the full fix is a PM ID + record + pool per context (stage 4), which removes the copies.

**The dump.** With `render_user_fault_read`, every job snapshots S, PM control, the aux windows S points at and each
aux page's head, at three points: start (after the switch handling), TA done and end. They are kept in a ring of 9
and as the last job per slot pair. The fault read prints them as `RENDER-V3 pmsnap`, so the faulting job, its
context's last good job and the other context's jobs sit side by side.

**Package (DEVICE-READY):** `perf60clk-6cee8a04c5` (12 commits), payload
`build/boot/m1n1-linux-perf60clk-6cee8a04c5.bin`, sha256
`1158a76462d7…`, release `7.3.0-rc1-perf60clk-g6cee8a04c58d`. It
uses release7's config (byte-identical), DTB, initramfs and cmdline. No G5P warnings; the desk-next check and the
audits are green.

**Run (orchestrator):** `PERF60_CLOCK_PKG=build/gpu/perf60clk-6cee8a04c5-pkg scripts/gpu/perf60-clock-device.sh hop 100
bell both mmu15 fread3 pms2`, then `hypr` with quickshell (Hyprland start reproduces the fault in ~20 s). Then:
- if it holds 10 min: repeat with `pms1`, then without `mmu15`;
- if it faults: `measure 30`. Its `fault.txt` has the read, the edit log and the pmsnap dump; `summary.txt` has the
  `pm-switch how=` counts.

## pms2 vs pms1, and stage 4: a PM record per context (13th commit, 2026-11-03)

**pms2 (save/restore) still failed:** lost seq 4262 (10/9) `3d-silent`, with `e150 = e158 = 0` (a stall, not an MMU
fault). The pmsnap decode (`build/gpu/perf60/pms/dmesg-pms2.txt`, ring jobs 4260/4261 on 8/7 and 4262 on 10/9):
- The PM **control words are global** and move with every job of every context: `C+00`/`C+0c` count up
  (`10a3 → 10a6`). `C+04` stays 8 through 8/7's jobs and went **8 → 0xa during 4262's TA**. That is firmware PM
  state of the one shared pool (`pm_once`), which no per-context copy can follow.
- The restored **aux page 0** held 10/9's own allocation records (`0x010107xx`, entries stepping by 1). After 4262's
  TA it holds exactly 8/7's records (`0x010102xx`); S after the TA equals 8/7's too (`S+00 = 0x1a`,
  `S+70/78 = 0x2c000`). The records index pool blocks, so restoring them against a pool and control that the other
  context advanced in the meantime gives a PM context inconsistent with its free list.
- `S+bc` is `S[8] + 4·S[0]` per context (0x75 for 8/7, 0x1d for 10/9). It is cleared by the fresh TA and is not the
  cause.

So save/restore can't be right while PM ID 0, control, list/F and the pool are shared.

**pms1 (fresh S + zeroed aux on every switch) held:** two Hyprland starts (44 and 64 switches) and a 240-job window
(fin median 7 ms), with 0 faults and 0 silents. **Judgement: it is a correct interim** for how we submit:
- every TYPED_V3 job is one TA (tag6 bootstrap, the fresh path that loads the PM context from aux and clears S+bc)
  plus one 3D that restores bank 1 from the S **this job's** TA saved;
- there are no partial renders (no tag5 growth, no OOM resume), and nothing is carried from one job into the next.

A context's job after a switch is therefore exactly the "first job after a pool reset" state that attach builds.
Nothing a later job needs is thrown away. The cost per switch is S rebuilt plus 5 aux pages zeroed and cleaned, tens
of µs.

Caveat: with `pm_once` the pool's control/free list stays global and continuous. The safest interim is pms1 with
`pm_once` off (layout `slots`), where the host resets the pool every job anyway.

**Stage 4, the iOS model (13th commit `909f87a0b0`):**
- **`boot_pm_sets N`** (≤ 8, latched at map): reserves N sets {control + S, list, F} in the firmware GiB right after
  `render_meta` (`0xe1c0268000…`, mapped like the shared pages). The device-wide firmware window adds them.
- **`render_user_pm_ctx`** (latched at the epoch's first attach):
  - **1:** every context bound after the epoch's first gets its own set, its own pool pages (the device's block
    count, 12.25 MiB at 98 blocks) and its own 5 aux pages. Before its bind, its VM maps `G5P_RU_PRIVATE_VA` to those
    aux pages. Its jobs carry its control/S meta address in W, the start/finish packets and tag6. The retire
    predicate's `pm80`/`pm_serial`, the receipts and pmsnap read its own PM. A new epoch or a grown device pool
    rebuilds the set; without `pm_once` its pool is rebuilt per job. Release frees the set and its pages, after the
    unhook has cleared the aux PTEs.
  - **2:** as 1, and set s carries **PM ID s + 1**: TA W+0x10 (`Dcb0`), TA start word 8, 3D start word 12, and the
    tag6 PMid. With PM ID 0 the job bytes are unchanged.
- The epoch's first context keeps the device PM.
- `g5p_rv3_fw_touch()` covers the set pages too (they are firmware pages, attr 0x14).

Tests:
- `test_job_slots` 1316/0, including the PM ID placement: exactly those 3 TA words and 1 3D word change;
- `test_pmset` 650/0: layout inside the shared window's 2 MiB directory, clear of image/root/PIO; distinct pages;
  IDs 1..8; round-robin pick;
- `test_mmu_inval` and `test_fault_decode` unchanged;
- audits pass (the pure `g5p_pmset_*` helpers added to the allow lists).

**Package (DEVICE-READY):**
- `perf60clk-909f87a0b0` (13 commits): payload `build/boot/m1n1-linux-perf60clk-909f87a0b0.bin`, sha256
  `935d09d028ef…`, release `7.3.0-rc1-perf60clk-g909f87a0b0f5`;
- `PERF60_CLOCK_PKG=build/gpu/perf60clk-909f87a0b0-pkg`;
- release7's config (byte-identical), DTB, initramfs and cmdline; no G5P warnings; desk-next check green.

**Run plan (orchestrator), each 10 min of Hyprland + quickshell:**
1. `hop 100 bell slots psets8 pmctx1 fread3`: per-context PM records, PM ID 0, `pm_once` off. `measure`'s
   summary shows the `RENDER-V3 pm-ctx … how=new set= blocks= meta=` lines and the layout line `pm_ctx=1 pm_sets=8`.
2. If 1 holds: `hop 100 bell slots psets8 pmctx2 fread3` (PM IDs 1..8), then `both` instead of `slots` (`pm_once`
   on).
3. If 1 faults: `fault.txt` names the context's own set in the pmsnaps (meta = its set's control).

**PASS** = 0 faults or silents in 10 min, ta/td ≈ 2/4 ms. **Risk:** low. The new boot step maps 24 more firmware
pages before release, exactly like the shared/`render_meta` regions; a boot failure there is a warm rollback.

**Result (909f87a0b0, `slots psets8 pmctx1 fread3`):** labwc's own 3D faulted at the second 8/7 job after the
second context's set was built.
- Order: seq 6/7 (10/9, set 0 new) ok, seq 8 (8/7, device PM) ok, seq 9 (10/9, a 256×256 target) ok, seq 10 (8/7)
  fault.
- The fault: `e150 = 80503759` = read, page invalid, level 1, requester 29/IPF_BLACKPEARL1, **context 5 (VCE1)**,
  VA 0x80.
- The pmsnaps (netconsole) show the records separate: set 0 has its own control `c026c000`, F `c0270000`,
  `S+b8 = c026c040`, its own aux records and its own pool counters.
- **But lane 1 (`S+10`, a PM catalogue page) is `0x8_5ea7b001` both in set 0's S after its job and in the device
  PM's S after job 8.** Two PM records with separate pools ended up with one catalogue page while both ran as
  **PM ID 0**: the PM's lane state follows the PM ID (or the hardware), not the record.

That is also why pms1 holds: zeroing the S lanes on every switch makes each TA allocate its catalogue pages from the
current pool. **`pmctx2` (a separate PM ID per set) is the direct test, and it needs no build** (909f87a0b0 has it).
Whether it alone is enough depends on whether the lane carry is keyed by PM ID (firmware) or held by the hardware
regardless of ID. The 14th commit adds the instrument that answers that, plus the complete iOS shape.

**14th commit `0f4ca0af00`:**
- **`pmctx3`:** as 2 (PM IDs 1..8), and the context that brought the epoch up moves to its own set after its attach
  job. It keeps the device aux its VM already maps, so no PTE changes. No user job runs on the device PM or on PM ID 0
  after the attach job.
- **`pms1` also applies to a context with a set:** its own S fresh and its own aux zeroed on a switch.
- **`RENDER-V3 pm-lanes`** after each TA (with `fread`): the owner of each lane page in S (device pool/aux, a set
  page, a context's pool or aux, or unknown).

**pms1 under real activity (6cee8a04c5, `slots mmu15 fread3 pms1`):** it faults too, after 71 fresh switches:
seq 4449 (10/9) 3D, `e150 = 00000014:80406749` = read, page invalid, **level 0, IPF_BLACKPEARL1, context 4 (TE1)**,
VA 0x1480. Its pmsnaps answer the two questions:
- **The TA→3D handoff is intact.** 4449's S at TA done equals its S at the end; the 3D restored bank 1 from exactly
  what its own TA saved, in its own record. The PM requester contexts 1..6 translate through the PM's lane catalogue
  pages (physical page tables the PM builds in pool pages), not through the user VM. So "is the pool VA mapped in the
  context's VM" does not apply; the failure is the content of the catalogue page a lane names.
- **The lane pages:** after a fresh S (all zero) and zeroed aux, 4449's own TA saved `S+10 = 0x8_15a53001` and
  `S+30 = 0x8_12bc6001`, exactly the previous job's (4447, the other context) lanes 1/2; lane 3 (`S+90`) was newly
  allocated. In this pms1 run one pool is rebuilt identically per job, so that alone is consistent with a
  deterministic allocation as well as with retention. **The stage-4 run is the real evidence:** `0x8_5ea7b001`
  appeared in both set 0's S and the device PM's S with disjoint pools, so a lane page crossed pools.

So the PM's lane-1/2 catalogue pages are carried in hardware across jobs (a power cycle, i.e. the park, would clear
them). Under `pm_once=0` the host rebuilds F every job, and that is the step that puts a catalogue page the hardware
still holds back into the free list, where a later TA hands it out as parameter data. This fits the IPF level-0/1
faults through contexts 4/5 (and the earlier ALIST null).

**iOS never touches the free list after building the PM.** In the pms2 dump (`pm_once=1`) all three lanes stayed
constant across nine snapshots of both contexts; under `pm_once=0` they churn. **Every stage-4 and pms1 run so far
used `slots` (`pm_once` off).** The Apple-shaped tuple, per-context records plus a PM-owned free list, is stage 4 +
`both`, and it has never flown. **Commit 14 does not add a fix for the lane carry. The candidate fix is that tuple.**

Run order (orchestrator), each with Hyprland + quickshell for 10 min:
1. No build, can fly now: `PERF60_CLOCK_PKG=build/gpu/perf60clk-909f87a0b0-pkg … hop 100 bell both psets8 pmctx2
   fread3`. `pmctx2` with `slots` would most likely fault for the `pm_once=0` reason and teach nothing about PM IDs.
2. `PERF60_CLOCK_PKG=build/gpu/perf60clk-0f4ca0af00-pkg … hop 100 bell both psets8 pmctx3 fread3`. Package
   (DEVICE-READY): payload `build/boot/m1n1-linux-perf60clk-0f4ca0af00.bin`, sha256
   `09cbe2ef4cbb…`, release `7.3.0-rc1-perf60clk-g0f4ca0af000f`.
   It uses release7's config (byte-identical), DTB, initramfs and cmdline; no G5P warnings; the desk-next check is
   green (`perf60-clock-check16.log`). **PASS** = 0
   faults, with the `pm-lanes` lines showing each context's lanes in its own pool, or stable cross-pool pages that
   nobody recycles.
3. **Fallback, not built:** if `both` + stage 4 still faults and `pm-lanes` shows a lane page inside a pool the PM
   itself freed, exclude hardware-held lane pages from every free list. A released context's pool must then leak any
   page a lane still names, or the GPU writes into memory the kernel has reused.

**Results with `both` (`pm_once` on):**
- 909f87a0b0 `pmctx2` ran **6.2 min**, and 0f4ca0af00 `pmctx3` ran **8.4 min**, both clean;
- gears windowed under Hyprland ran at **32–34 FPS** (release7: 8.4), with DISPLAY PASS (60 Hz vblank, every flip
  completed);
- `pm-lanes` shows every context's lane pages in its own pool, so the recycling of catalogue pages is gone.

Both runs then ended with the same TA fault: a PM write (requester 6, level 2, page invalid) through **context 10** at
**a set's +0x8000**. That is set 4 in run 1 (`0xe1c02a0000`) and set 6 in run 2 (`0xe1c02b8000`), i.e. that set's
**F page**. The set mappings are complete (all 8 sets × 3 pages are mapped at boot and are in the window), and the
address is the set's own F base, so this is not a record-stride mismatch.

In both runs **the 10/9 context owning that set had closed just before**: `unbind why=close … first=10 last=9`, then
`close … plan=unbind`, then the fault on 8/7's next TA (46 ms later in run 2). The PM writes the previous PM context
back (its F, through the previous job's TA slot) when the next TA switches PM contexts. With the GPU never parked,
that is the next job, which then walks an unbound slot (no catalogue: level 2). A close that came after another
context's job (run 2, 533.59 s, set 5) did not fault.

This hazard is not specific to stage 4: the device PM has the same deferred write-back through a closed slot. It
likely explains some of the earlier faults that "varied by context".

**15th commit `d32c3acc87`: `render_user_close_defer`** (live, default 0). A closed context whose job was the last the
executor ran keeps its slots bound and its PM record and pages alive (the close item's references are kept) until
another context's job has run; then its close runs as before. The reboot quiesce still unbinds every held slot. RAM
only. Lines: `RENDER-V3 close-defer` and `RENDER-V3 close-deferred`.

iOS: I have not RE'd its ParamBuffer release. Its slots stay resident until eviction or destruction, and its GPU parks
between bursts, so the write-back completes before a release. The deferral reproduces the order that iOS's power
cycle gave us for free.

Package (DEVICE-READY): payload `build/boot/m1n1-linux-perf60clk-d32c3acc87.bin`, sha256
`7358cb4168ac…`, release `7.3.0-rc1-perf60clk-gd32c3acc8742`. It uses
release7's config (byte-identical), DTB, initramfs and cmdline; no G5P warnings; the desk-next check is green
(`perf60-clock-check18.log`).

Run (orchestrator): `PERF60_CLOCK_PKG=build/gpu/perf60clk-d32c3acc87-pkg … hop 100 bell both psets8 pmctx3 cdefer
fread3`, with Hyprland + quickshell + gears runs (each gears run opens and closes a context). **PASS** = 10 min+ with
0 faults; the summary's `close_defer=`/`close_deferred_run=` counts show the deferral working.

**Display proof (the bell/never-park presentation stall), my side:** I found nothing in the GPU path that holds
presentation back.
- The job fence is signalled synchronously when `g5p_rv3_execute()` returns, behind only the BO cache maintenance;
  fin median 7 ms in pms1b.
- Logging is about 20 lines per job, about 70 lines/s at 3.5 jobs/s: no printk storm.
- The only IRQs-off sections added by the bell path are the wake/kick settle loops under `event_lock` (≤ 2 ms bound,
  `settle=0` on hardware).

Hyprland's ~3 jobs/s with 0 flips is a compositor/KMS-side wait, not a late GPU fence.

## Pin 200: the guarded drain read (`a9/release8@4ae9dea154`, 2026-11-03)

**Where it stalls.** On d32c3acc87, `hop 200 bell both psets8 pmctx3 cdefer` stalls in the **boot control
command**: `DC timeout consumer=0 producer=1 target=1`, logged by `g5p_control_wait` in `lifecycle.inc`. That is
before any job, with the firmware alive; ALIVE submitted 7 s earlier. The line `GPUPERF dc-timeout … pol34=1` means
the firmware stopped before its pstate setter, inside the clock-change drain `0x1001cec8 → 0x1001b638`.

**RE facts for the clock-change drain RE** (the dedicated RE agent owns that section):
- The drain is `11f00 = 1`; `688 = 7`, poll `(688 & 7) == 0` (`0x100018c8`, abort check `0x1000d138`);
  `1720 = [GbP+68] | 0x1f`, poll `1728` bit 0; SLC all-context `e230 = c03`, poll `e238` bit 0; `100179cc(1)`;
  `e138 = 0x804`, poll.
- It is gated by `0x100111fc` (`[GbP+60] != 0` skips it).
- The firmware's own boot runs the same routine (`0x1000515c`) and gets through it.
- The same `11f00`/`688`/`1720`→`1728` sequence, written **by the host** in the r17c compute
  CDM-invalidation preamble (`dsx-nx12-r48-mining.md`), acknowledged on hardware. So 688 can complete on Linux;
  what differs at the pin-200 request is the state the GPU is in at that point.

**The probe: `boot_gpu_perf_probe 1`** (default 0). At that control timeout it makes one guarded pass:
- under the event lock, the power proof (`powered`, `fender_ready`, `released`, not stopped or failed);
- Apple's wake (`R1+0x14 = 7`, read back), then `R1+0x1000` until `g5p_gpc_ok()` (≤ 2 ms). A pstate request still
  in flight (bit 4) means skip and log;
- then reads only: R0 `11f00`, `688`, `1720`, `1728`, `e230`, `e238`, `e138`, the clock control `0x0/0x4` and status
  `0x8/0xc`, and the PMGR GPU gate (`0x80340`, regmap).

Line:
```
GPUPERF dc-probe did=read|skip-* gate= fence= gpc= settle= 11f00= 688= 1720= 1728= e230= e238= e138= clk=hi:lo clkstat=hi:lo
```
The flush with a bit still pending (688 & 7, 1728 bit 0 clear, e238 bit 0 set, e138 & 0x807) is the one that never
acknowledges.

**Package (DEVICE-READY):**
- `release8-4ae9dea154`, release `7.3.0-rc1-release8-g4ae9dea15412`;
- payload `build/boot/m1n1-linux-release8-4ae9dea154.bin`, sha256
  `bcca031c5cf1…`;
- package dir `build/release/release8-pin200` (the owner's `build/release/release8` is untouched);
- release8 + the probe; release7's config, DTBs, initramfs and cmdline; `verify: PASS`; the check is clean.

**Run (orchestrator):**
*(Device/host command block omitted; it targets the private workspace.)*
That is the release tuple plus those two lines. The stall shows as `ADBE-DEVICE RESULT FAIL` and the run rolls back to
desk-next by itself. Then grep the run's dmesg for `GPUPERF dc-(timeout|probe)`.

**Risk: low–moderate.** Pin 200 stalled warm-recoverably on d32c3acc87 (no freeze). The probe adds one wake write,
which the bell path already does, and register reads only, before any job and behind the settled-pstate guard. If
the GPC is mid-transition the guard skips.

## 2. The step: `a9/perf60-clock` (one commit on release7)

`a9/perf60-clock@9d732490c2` = `a9/release7@802a3d4fc4` + one commit (`drivers/gpu/{,drm/}apple-g5p` only, +71/−16 and
a new `perf-envelope.h`; W=1 0 warnings on both GPU objects; checkpatch 0 errors).

- **`gpc_any_pstate`** (0600, default 0, read at every check): the 16 `== 1` guards go through `g5p_gpc_ok()`. With 1:
  any settled nonzero pstate (bit 4 clear, nibble 1..15) licenses R0, as on iOS; a parked GPC (nibble 0) never does.
  With 0 every check is the old `== 1`. The host's own power-up polls (it writes `0x11` and waits for 1) are unchanged.
- **`boot_gpu_perf`** (0600, default 0, latched at map; 100/200/300/400): before release, iOS's pstate table
  (`meta+0x710/0x714 = 4/5`, MHz `{0, 340, 474, 550, 723}`), limits `ctrl+0x1028/0x1030 = 3348/400`, floor
  `ctrl+0x102c = pin`, request `policy+0x6f0 = +0x6f4 (override) = pin`, ceiling `policy+0x688 = +0x68c (override) =
  400`. So `x = pin`, state 0, `q = pin / 100`: 1 = 340, 2 = 474, 3 = 550, 4 = 723 MHz. Sampler off (`policy+4 = 0`).
  Above 100 it refuses the map unless `gpc_any_pstate=1` (`GPUPERF refused …`).
- **Read-back:** `GPUPERF boot pin=… table=… limits=… policy688=…/… policy6f0=…/… q=… mhz=…` at map; with
  `lat123_log=1`, one `GPUPERF seq=… pol8=<state>/<sub> q=… x=… req=6f0/6f4 ceil=688/68c pol34=… ps=…` per job, next to
  the existing `RENDER-L123 … pol34=… pmgr=…/… ps=…` (`pol34` = the firmware's mirror of the Fender pstate,
  `ps` = `R1+0x1000` sampled once per job at a busy rise when `pstate_probe=3`, `pmgr` = the PMGR gfx word).

Package (after `perf60-clock-build.sh package`): `build/gpu/perf60-clock/` in release7's layout; payload
`build/boot/m1n1-linux-perf60clk-9d732490c2.bin`; release7's DTBs (stock OPPs), initramfs and cmdline byte for byte
(entry renamed), so a plain warm hop from release7 and back.

**Package (DEVICE-READY):** payload `build/boot/m1n1-linux-perf60clk-9d732490c2.bin`, sha256
`296a75ae5551…`, entry `perf60clk-9d732490c2`, release
`7.3.0-rc1-perf60clk-g9d732490c25f`; config byte-identical to release7's; `package` checked initramfs, DTB and
cmdline against release7's entry. `build/gpu/perf60-clock/{entry,release,payload.sha256,entry.sha256,cmdline,
cmdline-sd,labwc}`. The worktree has been `make clean`ed (rebuild ~1 h at -j2).

## 3. Device plan (orchestrator)

Prereq: the owner's release7 session up; `scripts/boot/netconsole.sh listen build/omarchy/logs/netconsole-perf60-clock.log`.

1. `scripts/gpu/perf60-clock-device.sh hop 200`: quiesce, warm hop, release7's tuple + `gpc_any_pstate 1
   boot_gpu_perf 200 lat123_log 1 pstate_probe 3`, labwc-a9-adbe and adbe-device.sh's proofs.
2. `scripts/gpu/perf60-clock-device.sh hypr` (Hyprland back on this kernel), run the load (es2gears as in perf60.md).
3. `scripts/gpu/perf60-clock-device.sh measure 30` → `build/gpu/perf60-clock/measure-<UTC>/summary.txt`:
   the `pol34/ps` histogram, the writer words, `ta_ms` / `td_ms` medians, `bad_lines`.
4. For the FPS number, turn the per-job log off first (perf60: log spam costs ~15 %):
   `echo 0 | sudo tee /sys/module/a9_gpu_drm/parameters/lat123_log`.
5. If 200 passed: `hop 400` (it quiesces this session and hops again), then `hypr`, `measure`, FPS. 300 only if 400
   fails after 200 passed.

**PASS:** `GPUPERF boot pin=200 … q=2 mhz=474`; per job `pol8=0/… q=2 x=200`, **`pol34=2 ps=00000002`** (400:
`pol34=4 ps=00000004`); `bad_lines=0`; `td_ms` median below the pin-1 baseline (perf60: full-panel 3D 30–65 ms); the
desktop and the client keep rendering.

Reading the outcomes:

| what `summary.txt` / dmesg shows | meaning | next |
|---|---|---|
| `GPUPERF refused …` | the tuple's order or values; nothing ran | fix the tuple (warm-safe) |
| `pol8=2/… x=0` | the overrides didn't hold (rung F's question, negative); pstate stays 1, the desktop is unaffected | stay; RE per `nopatch.md` §"Rung E result" |
| `pol8=0 q=2 x=200` but `pol34=1 ps=00000001` | the firmware wants 2 and never moves: no transition without the sampler | stay; RE the governor's transition call (`0x10009db4 → 0x1001c9b8`) |
| `pol34=2 ps=00000002`, `bad_lines=0` | **PASS**: the GPU runs 474 MHz | `hop 400` |
| `ps=0000001x` repeatedly, `RENDER-V3 terminal`/timeouts | a pstate request that Fender never completes; the firmware is stuck in its setter poll | rollback; DFU if SSH is gone |
| `ps=00000000`, bells refused | the GPC parked (should not happen with the sampler off) | rollback |
| SSH and netconsole silent | SoC freeze (e.g. clock without voltage) | DFU |

**Rollback:** `scripts/gpu/perf60-clock-device.sh rollback` = `release7-device.sh desk 1`, a warm hop back to release7
with its own tuple. A first hop back that fails with `alive ret=-110/-112` gets a second hop (`nopatch.md` §"first hop
back"); release7 already has the settle.

**Risk: DFU-risk for pin 200 and above.** Pin 100 is low-risk (RAM words only, pstate unchanged; it answers B2 alone)
but not proven warm-safe; skip it unless 200 is ambiguous. Every failure that keeps SSH has been warm-recoverable on
this path so far (the quiesce power-cycles the GPU on kexec); a voltage-related SoC freeze would not be.

## 4. Proven vs inferred

- Proven: B1 and B3 (decode, source, iOS memory, rung logs); the min() polarity; iOS runs P4 under load with
  `+0x6f0 = 500`, `+0x688 = 400`, `ctrl+0x102c = 400`; the kernel change compiles W=1-clean and checkpatch-clean.
- Inferred: that the overrides hold the request (rung F logic, unflown); that the governor's state-0 arm issues the
  transition with the sampler off; that Fender + hardware DVFS complete pstate 2–4 on Linux; that the clock alone
  speeds full-panel 3D (perf60's fill floor may not scale with clock; the fill lane will tell).
- Not attempted: load-driven DVFS (needs the sampler, B5, and Apple's zero-nibble power arm).

## Coordination

Build slot: this lane's build is done (`build rc=0`) and the worktree is cleaned; the slot is free. The fill lane's kernel (`a9/perf60-fill`) and this one
are both single commits on release7 in different files except the shared `drivers/gpu/apple-g5p/` tree; they should
merge cleanly, but nobody has checked yet.

## Clock-change drain RE (2026-11-03)

This is a research lane: no device run, no build, no commit. Sources:
- `build/gpu/firmware-re/10000000.minim.dis`;
- the j71t kernelcache in the shared Ghidra;
- the release8 driver (`/src/wt/release8` in `linux-a9-src`);
- the pin-200 run `build/gpu/exp12-…-20261103T092742Z-dmesg.txt`;
- the iOS power capture `build/gpu/ios-capture-bundle/20261101T154856Z/device/power/*-series.csv`.

Labels: [P] proven by a device or capture value, [V] verified decode, [I] inferred.

### 0. Bottom line

1. **The drain is not on the clock-change path.** `0x1001cec8` is the firmware's try-to-park routine. It is not "the
   clock change" [V] (agrees with `mmio-access.md` §8). Its sequence:
   - the drain `0x1001b638`;
   - `R1+0x1004 = policy+0x28` (the wake target);
   - `R1+0x0 |= 0x20000000` (bit 29, the "GPU going down" flag; `ORT` is the top half);
   - then either:
     - **park**: clear bit 30 if `priv+0x188 == 0`, then `0x1001c88c(0, mode 0)` (GPC → 0), then the self-branch
       `0x1001d074`;
     - **abort**: only when `arg2 == 0 && 0x1000176c() != 0` (a ring has work). It calls `0x1001cd8c(0)`.

   The pin-200 probe agrees: every flush bit reads clear [P].
2. **In policy state 0 the firmware never changes pstate while powered** [V]. The state-0 arm of the governor
   (`0x1000c770..c7d8`, `cf54`) does three things:
   - writes `+8 = 0` and `+0x28 = +0x2c = q`;
   - calls `0x10009db4`, which returns without a setter call when `+8 == 0` (`0x10009e2c → 9f28`);
   - branches to the idle tail `0x10009bd8`.

   The setter (`0x1001c9b8 → 0x1001c88c`) is reached only from:
   - the firmware's boot sampler `0x1000aa80` (`0x10000b54`, before ALIVE at `0x10000b80`), when
     `policy+0x28 ≠ Fender & 0xf`;
   - the state-1 (fractional pin) dither arms (`0x1000c9e4`, `0x10009fc8`);
   - `0x100094c0` (no static caller).
3. **iOS does exactly this** [P capture + V]. Under load, `policy+0x34` makes only 4→0 / 0→4 transitions (146 each in
   1501 samples), with `policy+0x28 = 4` and `+8 = 0` throughout. At idle the transitions are 1↔0 with `+0x28 = 1`.
   There is never a 1→4 change while powered. So iOS changes the clock only across park → wake: the parked firmware
   halts, the host power-cycles and reboots it, the host requests GPC 1, and the boot sampler applies `+0x28`. The
   kext writes GPC 1 at boot and 0 at power-down, nothing else (`ds-gpu-dvfs.md` §1.3).
   `AGXMetaFirmware_submitDeviceControl` (`6ca05d4`) tests `(R1+0 >> 29) & 1`, the park flag set by `0x1001cec8`
   [V]. iOS's P1 residency of 0.97 % fits the short window between a wake at GPC 1 and the sampler's raise.
4. **Why the pin doesn't take on Linux** [V source + P log]:
   - `boot-layout.h:221` seeds `policy+0x28/+0x2c = 1/1`.
   - At the firmware's boot sampler, target 1 = Fender 1, so there is no transition.
   - After ALIVE (37.694 s), the governor computes `q = 2`, but in state 0 it never applies it.
   - Never-park removes the only other route (park → reboot).

   So `Fender = 0x01` and `pol34 = 1` are the expected end state [P probe]. Pin 200 cannot reach 474 MHz on this path
   regardless of the cmd8 stall.
5. **The cmd8 stall's exact location is still [I].** The only q-dependent hardware action left in the state-0 main
   loop is the try-park kick: `R1+0x1004 = q` plus `R1+0` bit 29, with `q ≠` the current GPC state.
   - Both ways out of `0x1001cec8` end in polls that log once on timeout and then spin forever (`0x10007a94`, [V]).
   - The abort arm polls `R1+0 == 0x40000000` (whole word), then writes `R1+0x1004 = 0`, then W1C-polls `R1+0x8` to 0.
   - At pin 100 the kick carries `q` equal to the current state.

   One read decides whether this is the stall (§4).

### 1. Your first questions

| # | answer | label |
|---|---|---|
| 1 | **`R0+0x688`** is a 3-bit flush/invalidate request with self-clearing status (poll `(688 & 7) == 0`). Values: 7 at boot and park (`0x1001b638`), 4 in compute finish33 (`80008cdc`, so bit 2 is tied to CDM). The host's r17c write cleared it [P], and it reads 0 at the pin-200 stall [P]. **`R0+0x1720`** is the request and **`0x1728`** bit 0 the busy flag (write `0x1720`, poll `0x1728`; the brief's "`0x1728 = [GbP+68]`" is a mis-transcription). The helper `0x10019610` builds `global44 \| 3 \| {4, 8, 0x10}`: bits 1:0 are the operation and bits 4:2 select the unit (0x13 = compute). `0x11f00 = 1` goes through a firmware command list instead when `[GbP+0x3c] ≠ 0` (`0x100125b4`, record `reg<<12 \| 0x204`). None of `0x688`/`0x1720`/`0x11f00` is in the public Rogue maps: these are Apple G5P registers. `e138 = 0x804` is `MMU_CTRL_INVAL` ALL_CONTEXTS\|PC; `e230`/`e238` are Apple SLC3 maintenance in the `e200..e260` SLC3 block. Nothing on the host must be powered or acked for these to clear: the GPC is on and the flush is internal. | [V] decode; [P] values; names [I] |
| 2 | **`[GbP+0x44]`** (decimal 68) has no store in either image ((instruction omitted): none). The data image word at `0x10013a04` is 0, so the request is `0x1720 = 0x1f`. It is firmware-private, and our boot cannot leave it wrong. | [V] negative; value [I] (offset mapping) |
| 3 | **`0x1000d138`** returns 1 iff `*(root+0x74)[0] == 2`, the companion state. Its only writer is the firmware's `0x1000d164` (engine accounting). With no jobs the companion is 0, so the abort never fires on an idle boot. The poll engine `0x100018c8` has no timeout. | [V]; idle value [I] |
| 4 | Boot runs `0x1001b638` inside `0x1000515c` (hardware init) and gets through it. Pin 200 never needs it for a clock change, because the clock change doesn't use the drain (§0.1). The probe shows no flush pending [P]. | [V]/[P] |
| 5 | iOS's kext writes GPC 1 at power-up, GPC 0 at power-down, `R1+0x14 = 7` per DC, and reads bit 29 at DC submit. It writes no SLC/PMGR word around pstate changes, because iOS never changes pstate while powered (§0.3). Our host init matches on the Fender side (`R1+0x10000`, `R1+0 = 0x40000000`, `R1+0x1000 = 0x11`, `R1+0x20000`). The one functional difference for the clock is `policy+0x28` at firmware boot. | [V] kext; [P] capture |

**Clock words and PMGR from the probe** [P/V]:
- `R0+0x0/0x4/0x8/0xc` = `0a2a2a0a`/`a02a8200`/`00000200`/`0`. These are byte-identical to this boot's own
  pre-release `G2 snapshot before-arm` (35.46 s).
- Rogue `CLK_CTRL` layout: every present unit is AUTO; TE/GPP/UVS/FB* are OFF. `CLK_STATUS` has only bit 9 set, so
  the GPU is idle, not mid-flush.
- PMGR `0x3ff` decodes as target f, actual f, plus the sticky `was_pwrgated` (bit 8) and `was_clkgated` (bit 9). The
  same boot logs `POWER before-arm … 000003ff … was_clkgated=1 was_pwrgated=1` [P]. Bit 9 is history, not a pending ack.

### 2. Your revised questions

1. **Between q=2 and a clock change there is nothing in state 0** [V]. The firmware's only route is a firmware
   (re)boot with `policy+0x28 = q` (the boot sampler), or state 1. There is no idle, host-ack or timer wait in that
   path that we fail to satisfy; the path just isn't taken.
2. **`0x1001cce0(x)`** writes `R1+0x1004 = x` and reads it back, with no wait [V]. The waits are elsewhere:
   - in the setter: pre-poll bit 4, write, post-poll `(R1+0x1000 & 0x1f) == q`;
   - in `0x1001c9b8`'s boot branch (`[[GbP+0x7c]+0x28] == 0`, which is always true; the word has no writer):
     - a PIO unit-6 write and read (`+0x2c = 0x1804`, base 0, iOS identical per `dsx-r75`);
     - the META `0x04000180` pulse;
     - an `R0+0x160` delay of `(Δ<<8)/MHz > 4`;
   - in `0x1001cd8c`: `R1+0 == 0x40000000`, then `R1+8 → 0`.

   Every one of these timed polls logs once and then spins forever.
3. **No designed deadlock in the setter path.** The boot-sampler transition runs before ALIVE, so the DC ring can't
   be involved. In the main loop the DC consumer (`0x10001cf4`) advances only after its handler returns, and any T0
   spin blocks it. The candidate spin is the try-park kick with `q ≠` the current state (§0.5).
   - `0x1000176c` = "any of the four root rings (`root+0/8/0x10/0x18`, DC = `+0x18`) has producer ≠ consumer" [V].
   - The idle tail returns early if it is set (`0x10009c4c`).
   - So `0x1001cec8` runs only on empty rings and aborts only if work arrives inside the window.
   - On Linux, cmd8 is rung about 1.9 ms after ALIVE (37.6959 s), inside the first governor passes [P].

### 3. Fix spec for the clock lane (Apple-faithful, RAM only, before release)

**`boot_gpu_perf_seed` (0600, default 0; needs `boot_gpu_perf = 100·q`, q ∈ 2..4).** When it is set, `g5p_make_init`
(`boot-layout.h:221`) seeds the policy record with the firmware's own steady-state output for the pin:
- `policy+0x28 = policy+0x2c = q`, written as `put64((u64)q << 32 | q)`;
- `policy+0x30 = 0` and `policy+8 = 0` (already the case).

Effect [V decode]:
- The boot sampler (`0x1000ada4..ae70`: `+8 ≠ 2`, target `= +0x28 + 4·(+0x30)`, `≠ Fender & 0xf`) calls
  `0x1001c9b8(q)`.
- That runs `0x1001c88c(q, 2, 250)`: `pol34 = q`, `priv+0x2c4 = table[q]` (the TXTIMER reload follows), and
  `R1+0x1000 = q | 0x10`, polled for `q`. All of this happens before ALIVE, which is iOS's wake sequence.
- Afterwards the governor's state-0 output equals the current state, so every try-park kick carries
  `R1+0x1004 = q =` current, as at pin 100.
- Voltage follows in hardware (psinfo MATCH [P]). Nothing else changes: same `meta+0x6c8`, LDR, guards
  (`gpc_any_pstate=1` accepts state q).

Host conditions to keep:
- The R74E power poll (`boot.inc` `g5p_r74e_power_poll(…, 1, …)`) may stay at 1. It completes 52 µs after the
  `0x11` write, about 2.5 ms before the firmware's sampler [P timing].
- **No host write of `R1+0x1000 = 0x11` after release** (`g5p_r74f` reactivation `boot-r74f.inc:237`, `recover.inc`
  wake) unless it is followed by a firmware reboot. Otherwise it drops the GPC to 1 under a firmware that believes q.
  If one of them is in the tuple, it must write `q | 0x10`, or the run must use the firmware-reboot path.

PASS lines:
- `R74E ALIVE submit … state=0000000q after=0000000q`;
- cmd8 consumed;
- job lines `pol8=0/… q=q pol34=q`, bells `gpc=0000000q`;
- `td_ms` lower than at pin 100.

FAIL modes:
- **No ALIVE** (the firmware spins inside `0x1001c9b8`): hop rollback. Read the §4 words at the ALIVE timeout instead.
- **Freeze**: DFU. The risk is low [I]: the transition is the same Fender request iOS makes about 25×/s.

**Run (orchestrator), once built:**
*(Device/host command block omitted; it targets the private workspace.)*

### 4. The decisive read if seed 200 fails, or to name the unseeded stall

Extend `boot_gpu_perf_probe` (same guard: before any job, firmware alive, GPC settled). Take the reads **before** its
`R1+0x14 = 7` write:
- R1 `+0x0`, `+0x8`, `+0x14`, `+0x1004`, `+0x20000`;
- R0 `+0x160`/`+0x164` twice, 1 ms apart;
- through the slave port (`g5p_sample` style): T0/T1 `TXENABLE`/`TXSTATUS` (`0x04800000/10`, `0x04801000/10`);
- through the slave port, second tier, **T0 PC**: write RQ `0x0480fff8 = 0x10005`, poll bit 31, read
  `0x0480fff0`; ×8 samples, 100 µs apart.

The second tier shares the core-register port with the firmware's `0x10021d48`. That path is live only once T1 has
started, which happens after the first work.

| reading | meaning |
|---|---|
| `R1+0x1004 = q`, `R1+0 ≠ 0x40000000` (bit 29 set) | stuck in `0x1001cd8c`'s whole-word poll after a q≠current kick (the unseeded pin-200 stall) |
| `R1+0x1004 = 0`, `R1+8 ≠ 0` | stuck in the `R1+8` W1C poll (`0x1001cd1c`) |
| `R1+0x1000 = 0x1q` or `0x01` with PC in `0x10007b3c..0x10007c4c` called from `0x1001c97c` | seed case: Fender didn't take `q` (setter post-poll) |
| PC in `0x1001b908..0x1001bb08` / `0x10027280`, `R0+0x160` frozen | seed case: the `0x1001c9b8` timer delay (timer not counting) |
| PC at `0x10007a44`/`0x10007a6c` with caller `0x1001b92c..0x1001b944` | seed case: the PIO unit-6 access hangs on Linux |
| PC in the main loop `0x8000a0f0..0x8000a3a0`, all R1 words at baseline | firmware idle and cmd8 not seen (lost doorbell); re-ring once |

### 5. Plan B (`meta+0x6c8 = 0`, host-set clock)

1. **What `6c8` really gates** [V, every reader of `priv+0x22c`, the cached `meta+0x6c8`]:
   - **the power policy and DVFS** (with `priv+0x228`):
     - the main-loop veneer into the governor (`0x10001ae0`);
     - the governor's early return (`0x1000c100`);
     - the sampler's early return (`0x1000aacc`);
     - the park handshake `0x1001cd8c` (`0x1001cdb0`);
     - the divisor choice in `0x1001c9b8` (`0x1001cb24`, `0x1001ba2c`);
   - **the host notification route**: `0x1001fa74`/`0x1001fb9c` raise the host interrupt through PIO unit 2
     (AIC SWINT, `priv+0x260/0x264`) when it is 1, and through the META trigger `0x04820010 = 0x10` (poll bit 4)
     when it is 0;
   - **the firmware time base**:
     - `0x1001fef0` (boot), `0x100220d4`, `0x1002215c`: AIC timer when 1, META timer × `priv+0x270` when 0;
     - the TXTIMER reload at `0x8000a190`: current MHz `priv+0x2c4` when 1, fixed `priv+0x270` when 0.

   So 6c8 is not a DVFS-only switch: it also moves the IRQ route and the time base. The `meta6c8 = 1` requirements in
   the r73b/r74/r74f/r74g/r87b latches are our construction. 6c8=0 controls exist (r73b case 2, r73e case 2, r74
   case 2 / r73f case 4), but the TYPED_V3 first-ALIVE/event plumbing was built and proven only on the 6c8=1 route.
   That dependency on the notification route and time base is real [V route; I that TYPED_V3 breaks].
2. **With 6c8=0:**
   - TA/3D/PM ran in the past: r43–r52 TA consumed with an inline bell, r68/r70 3D consumed
     (`sonnet55-start23-hardware-contract.md`) [P]. `pol34` stays 0 [P corpus].
   - No static path writes `R1+0x1000` then: the setter's callers are all behind the sampler or governor [V static;
     I for indirect calls].
   - So a host `R1+0x1000 = q | 0x10` write would not race a firmware writer. The "R1 power write hang class" in
     `nopatch.md` ~198 is the 6c8=1 race with the firmware's park and setter.
   - It is still a GPC transition on our boot path. Do it with no job in flight and poll bit 4, then `== q`
     (Henrik's protocol).
   - Firmware timeouts would then run on the fixed `priv+0x270` base, not the real clock [I].
3. **A DVFS-only gate with 6c8=1 already exists: integer pin = state 0.** In state 0 the firmware never changes
   pstate while powered (§0.2). With the §3 seed, the firmware sets the pin once at boot, and its kicks then match.
   No `P+0x93c/0x944` equivalent is needed.
   - `priv+0x228` (`meta+0x6c0`) gates the same set as 6c8, including the notification route. There is no narrower
     word [V for the readers found].
   - A host-written pstate under 6c8=1 would need `policy+0x28` kept equal to it, or the try-park kick re-requests
     the old target.
4. **Verdict:** Plan B is a realistic fallback but expensive. It means re-proving the TYPED_V3 transport on the
   META-trigger IRQ route: first-ALIVE, the event decoder, the bells and never-park, which comes for free with no
   policy.
   - Smallest test: the existing 6c8=0 control tuple (r74 case 2) to the first consumed cmd8, then one guarded host
     `R1+0x1000 = 0x12` (poll bit 4 clear, then `== 2`, 100 ms), read back, then one compute DC.
   - Fly §3 first: it is one RAM word pair and needs no transport change.

### 6. iOS reads (the iPad is in iOS now; optional)

The existing capture already settles the iOS mechanism (§0.3), so nothing is required. If the owner wants a load
series with the policy words:
*(Device/host command block omitted; it targets the private workspace.)*
It is read-only: IOReport plus shared-RAM policy/meta/ctrl, no MMIO. It decides one thing: do `policy+0x28`
(target) and the `+0x34` 0→q transitions still match §0.3 at other loads (expected: every `+0x34` change passes
through 0)? No Fender or PMGR MMIO reads on iOS: they panic it.

### 7. Side note: overclock above 723 MHz

This needs four things:
- PSINFO record 5 at `0x20e070050` (PLL from the LLB table: 800/804/850/900 MHz exist; core and buck8 rail codes; the
  buck8 derivation is still open, `ds-gpu-dvfs.md` §4.3);
- `meta+0x710/0x714 = 5/6` with MHz entry 5;
- `ctrl+0x1030`, `ctrl+0x1038` and `policy+0x688/0x68c = 500`;
- the §3 seed with q = 5.

The firmware path is the same.

### 8. Ghidra

There are no firmware renames, because the META LDR is not in the shared project. Comment added on
`AGXMetaFirmware_submitDeviceControl` (`fffffff006ca05d4`): bit 29 = the firmware park flag, and the park → reboot →
boot-sampler clock mechanism. `scripts/ghidra-mcp.sh save` was deferred (server busy); it needs one more save.
