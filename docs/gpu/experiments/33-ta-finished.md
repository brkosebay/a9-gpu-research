# R33: TA_FINISHED on any epoch (prime, clip probe, flight v2) and the warm-index track

2026-10-24. Kernel `a9/gpu` **`151170a3cf`** on r32 `e070aee4f0`. The identity,
payload and commands are in `33-device-tests.md` (not published). Inputs:
r32 results,
ds-r33-a (which warm vertex faulted),
ds-r33-b (what a cold power-up clears),
ds-r33-c (what TA_FINISHED is missing).
Offline only: no device run is claimed.

## The two problems, settled from the captures we already had

There are two separate defects. **(2) is the priority**, because it also
blocks the clean cold boot.

1. **Warm boots fault on a stale vertex index.** Cold boots never fault.
2. **No TA ever raises TA_FINISHED, on any epoch.** The cold r32-01 run
   (`…212022Z`) did not fault: `TA_submitted=1 consumed=1 terminal=1`, but
   `TA_complete=0` and `PM_saved=0`.

### The cold baseline (problem 2), ds-r33-c §1-§3

- **Deterministic.** Six cold captures (r27-01, r28-01, r30-01, r31-01/02,
  r32-01) have the same end state. The three with a flight recorder show the
  same ~10 µs burst, about 422 µs after the doorbell:
  - JONES_IDLE goes `3d7f → 3d3e → 3d35 → 3d34 → 3d7c → 3d7f`, so the VDM,
    PM and TILING units are busy briefly.
  - `0x430` (`VDM_CONTEXT_STORE_STATUS`) goes `1 → 0x12 → 0x02 → 0x11`.
  - After that, nothing happens for 12 s.
- **The VDM consumes its whole stream.**
  - Late `0x410` = `0x1_000404e0`, one word past `STREAM_TERMINATE`.
  - `0x420` counts the INDEX_LISTs (2 for full streams, 0 for empty ones).
  - `0x430` ends at `COMPLETE=1, NEED_RESUME=0`.
- **The PPP terminate state is present and correct.** It is
  `{0x02000000, 0x00040001, 0}` (pres_terminate, clip 0..1 × 0..1 for
  64×64, RT 0), followed by `0xc0000000`. Removing it (r24-r26 `probe&1`)
  also stalls.
- **The one PB word that changes (`pb3000 = 0x297b8001`) is a PM page-table
  entry, not geometry.** The 70 PB words are the PM's TA-start
  pre-allocation (PC → 2 PD → 2 PT, 37 frames). Its root is `R0+0xe008`.
- **No event of any kind latches.** `EVENT_STATUS` stays 0 and `b20` stays
  `0x0d`, so neither TA_FINISHED (bit 5) nor TA_TERMINATE (bit 6) fires.
- **The cold epoch is irrelevant to TA_FINISHED.** r28-01 ran the **empty**
  render (STREAM=1, no draw) on a DFU-first boot and stalled exactly like
  every warm run. A cold boot only removes the vertex fault. The minimal
  failing case is therefore the empty render, and it is valid on **any**
  epoch.
- **Zero RT does not prove the TE ignored the terminate.** Region headers
  have only ever appeared after a firmware store: finish24 after a mask-0
  wait, or the fault abort.
- **iOS job2.** The TA microsequence matches ours structurally. The first
  job of a fresh iOS context has our shape. The iOS W, S and VDM stream
  were never dumped, so no W/S/stream diff is claimed. The dumps to take are
  listed in ds-r33-c §4.5.

### (a) Which warm vertex faulted at `0xF_FF18_6B80` (ds-r33-a)

- **The packet is the same as E2's.** It is requester 8 (`MCU_TEXAS0`, the
  vertex DMA), context 8, a read, level 2 (no PC entry for VA[39:30]).
- **Excluded:**
  - an instance index: both vertex PDS programs read only `t0`, and E2 showed
    `t0` equals start_index;
  - another unit: every other PDS program is halt, doutW-only or a shift.
- **The quad did carry start_present with start_index 0.** The captured tail
  matches, and `0x410` shows the VDM read past TERMINATE.
- **Arithmetic and search.** The implied index is `0xEFF17E98..9B` against
  the triangle or `0xEFF0FEB8..BB` against the quad. No base/stride in our
  state gives a small index. The owned-RAM search found 0 hits (it found 6
  for E2, so it works).
- **Still open:** a later triangle vertex (v1/v2), or a quad vertex whose
  start_index was ignored.
- **Discriminator:** E1 with stride 0 on the triangle only (r33 case 04).

### (b) What a cold power-up resets that the warm kexec cycle does not (ds-r33-b)

- **The warm cycle is a real reset.** Every resettable R0 word the previous
  job changed comes back at its cold value. That includes a latched,
  never-acknowledged MMU fault word and the Fender wrapper registers, before
  any write.
- **The only survivor is `R0+0x418/0x41c`.** It holds the previous boot's
  exact `0x1_00080000`. On cold boots it shows a power-up pattern that
  varies by a few bits (`0xFE_0Bxxxxxx`), so it is a register with no reset.
- **No sampled register carries the stale index.** All 149 late-window words
  are identical cold vs warm.
- **The variable is the off-time.** The cycle holds `ps_gfx` off for about
  10 µs; a cold boot has it off for seconds to minutes.
- **No fuller Apple reset path is skipped.**
  - Every SOFT_RESET bit in the G5P mask is pulsed on every boot.
  - Apple's three host-only extras all faulted in r27.
  - iOS power-off has no minimum off time.
  - SOFT_RESET2 bits 3-8 and 10-11 are never pulsed by anyone. They are a
    low-prior knob B, not built this round.
- **Proposed fix (knob A): hold the gate off long enough.**
- **The case-04 kexec hang** has no GPU indication. The kexec hang rate is
  2 in about 58 warm runs, and the other hang followed a boot with no fault.

## The r33 factors (root-only `0600`, default 0, latched at prepare)

| Parameter | Kind | Effect |
|---|---|---|
| `render_r33_prime=1/2/3` | factor (ds-r33-c E1, H-hist) | Requires STREAM=1 (empty) and the r30 mask-0 wait, and admits no other factor. Job 1 is retired by finish24 under the mask-0 wait, which runs the end-of-TA PM save and the `0xc50` store (r30-05). The **witness** then records the PM-aux words, the RT region headers, `0xc50`, `0xe008` and the stamps, before the r32 re-arm zeroes PB/RT/aux. Job 2 runs in the same boot with the **real 0x801 wait**. 1: the empty render again. 2: the E1 triangle, TA-only. 3: the E1 triangle **pair** (TA + 3D, r22 oracle; the 3D channel is used for the first time), pair stage only. |
| `render_stream_variant=6` | factor (ds-r33-c E2, H-deliver) | Clip0: LINK → VDM+0x400 → a private PPP state at VDM+0x410 `{0x02000000, 0, 0}` (pres_terminate, clip (0,0)-(0,0)) → TERMINATE. The shared terminate block at `0x1_0008c174` is untouched. Run with the mask-0 wait, so finish24 writes the region headers. TA-only. |
| `render_stream_variant=7` | factor (ds-r33-a) | E1 (start_index 0 on both draws) with **stride 0 on the triangle only** (`state+0x2d8 = 0`; the quad keeps `0x10`). The triangle can no longer fault, so any vertex fault is the quad. TA-only. |
| `boot_gfx_off_ms` (≤ 2000) | factor (ds-r33-b knob A) | At the first Fender wake, before any GPU MMIO and before any GPU IRQ is requested, the GPU driver holds PMGR `ps_gfx` (`0x80340`) off: target 0, poll actual 0, sleep, then target `0xf` and poll actual `0xf`. It refuses unless the gate is fully on with min, reset and auto clear (pmgr-pwrstate's own rules). Every exit requests the gate on again. Logged as `POWER gfx-off ms= held_us= before= end= after= off_ret= on_ret=` in dmesg. The witness is `0x418/0x41c` at `attached-no-launch`. |
| `render_r33_observe` bit0 | observation | **Flight recorder v2** after every TA doorbell, re-armed for job 2 (prime and the r32 second job). It records the r31 registers plus `0x410`, `0x420`, `0xc30`, `0xc50`, `0xe008`, `0xe028`, `0xe048`, `0x290` and `0xcb8`. It watches the PM PT entry (old pb3000), the first frame of PM region A (`physical[7]+0x3000`) and region B (`physical[3]+0`), and the region-header flag bytes of tiles 0/1/4/5 (`rt+0/4/0x14/0x18`). CLK_STATUS is accumulated but not logged, so the burst is never dropped. It replaces the r31 flight (r31 observe bit0 must be off). Every line carries `job=N`. |
| `render_r33_observe` bit1 | observation | The r32 R0 windows (`0x400..0x4b4`, `0xc00..0xd20`, `0xf000..0xf074`), read once at `attached-no-launch`, giving a pre-kick baseline for the late read. |
| `render_r33_observe` bit2 | observation | RT page 0 region headers (0x500 bytes, nonzero 32-byte rows), the five PM-aux words, `0xc50` and `0xe008`, at TA-only, PM-saved, 3 s, pixels and failure, and in the witness. |

`render_status` is `revision=33` and adds `r33 prime r33_observe prime_witness
prekick flight2_job flight2_iterations flight2_events flight2_dropped
flight2_skipped`. The witness bits are 1 aux, 2 rt, 4 pm_saved, 8 retired.

## Analyzer (`scripts/gpu/analyze-render-r33.py`)

- It runs the r32 → r28 chain with `revision=33`.
- r28 rebuilds the expected VDM head/tail and VS data for streams 6 and 7.
- The r28 integrity stop is kept (`r28_stop`), because r29 (queue/IRQ) and
  r30 (mask-0) relabel `stop-inspect`. That masking was a latent inherited
  bug, and it would have hidden a wrong tail on every WAIT=1 run.
- Flight v2 is split per job.
- The region-header image is rebuilt from the rt-rows and compared with the
  full-screen baseline: `0x20` at {0,1,4}, `0xb0` at 5, 24 × `0x70`,
  228 × `0x60`, flag byte at 5·i. This baseline matches the r32-01/03 warm
  captures byte for byte.
- Verdicts are listed in `33-device-tests.md` (not published).

## Limits

- **Prime tests hardware/firmware history only.** The re-arm rebuilds W/SKU
  and the PM pool and zeroes RT/aux/PB. If prime 1 is negative, the
  follow-up keeps job 1's aux and S.
- **"First TA after a firmware boot" cannot be literally impossible,**
  because iOS's own first TA must complete. Read a positive prime as "the
  finish24 store path primes some hardware/firmware state", which is the
  thing to then find.
- **The clip probe reads the header image after finish24's store.** "Image
  unchanged" is ambiguous: the store may build headers from TE registers
  (`0xc18`). Only "image changed" is decisive.
- **gfx-off runs ~26 s after boot, from the GPU driver, with genpd still
  "on".** It is the same PMGR operation as the kexec cycle, only longer. A
  positive result means `0x418/0x41c` lost its value **and** there is no
  fault. Completion is not part of it, because the cold job also ends with
  `TA_complete=0`.
- **Register names** for `0x410`, `0x420`, `0xc30`, `0xc50` and `0xe0xx` are
  inferences. The S7 TA/TE/PM register block is not in the KM header.
- **First mid-job reads.** The flight v2 is the first to read `0x410`,
  `0x420` and `0xc30` while a TA runs. Before r33 they were read only after
  a terminal stage (the r32 late window), and start23 does not touch them.
  Their neighbours `0xc28`, `0xc38` (r24 `TA-post-notify`) and `0x430`
  (~10k reads per job since r31) were read mid-job with no effect.
- **Integration.** tri33 carries the round-8e boot code (a9/boot
  `bfe22c60a0`) and its initramfs, for the unattended warm ladder. See
  `33-device-tests.md` (not published).
