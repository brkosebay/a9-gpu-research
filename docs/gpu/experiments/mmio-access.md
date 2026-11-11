# MMIO access: why GPU register reads hang the A9, how iOS reads them, and one safe accessor

2026-11-03. Research sub-agent (Opus 5.5), host only. No device access, no kernel edit, no commit.
Sources: shared Ghidra project (iOS 16.7.10 j71t kernelcache, `kernelcache.release.iPad6,11_12`), a capstone scan of
the AGX range of that file (`__PLK_TEXT_EXEC` `fffffff006c00000..6cbe000`), the firmware listings
`build/gpu/firmware-re/10000000.minim.dis`, the release8 driver at `a9/release8@4ae9dea154` (extracted read-only from the
`linux-a9-src` volume), the iOS power capture `build/gpu/ios-capture-bundle/20261101T154856Z/` (already on disk), and the
prior studies listed in the brief (consumed, not redone).

Labels: **[P]** proven (device data or code that runs), **[V]** verified decode (disassembly/decompile read here),
**[I]** inferred (the argument is stated). Addresses: `fffffff006cXXXXX` kext, `0x1001XXXX` firmware.
`R0` = `0x201000000` (Rogue registers), `R1` = `0x201e00000` (Fender). "GPC" = the Fender power/performance state,
`R1+0x1000`: low nibble = pstate (0 = off, 1..4 = 340/474/550/723 MHz), bit 4 = transition in flight.

---

## 0. Answers

1. **Why a read hangs.** The R0 bus has no response while the Fender has the GPC at, or on its way to, pstate 0. The
   firmware drops the GPC to 0 on its own when it goes idle: its governor parks, and its power-down path drops it too.
   A host R0 read that lands there stalls the CPU forever. It is bus-level, not a read side effect. Every documented hang
   is an R0 access made on a GPC check that had gone stale, at the moment the firmware had just gone idle (§1) [I, high].
   R1 reads are safe whenever the PMGR `gfx` domain is on (Apple reads R1 in every state, including mid-transition)
   [V]. PMGR is always-on [P]. One second-hand datum contradicts the R1 claim; the first proof rung settles it (§1.3).
2. **How iOS reads safely.** Every runtime R0 read in the kext sits behind one predicate, fw vt+0x290 at
   `fffffff006ca10ec`, now named `AGXMetaFirmware_isGPURegisterAccessible` [V]. It passes when all three hold:
   - the Fender "powered" software flag is set (PMGR on);
   - `1 ≤ (R1+0x1000 & 0xf) ≤ maxPstate`;
   - **`R1+0` bit 29 is clear.** The firmware sets bit 29 in its power-down path before it drops the GPC (§2.3).

   That is the handshake we never implemented. The check involves no wait, no wake and no kick write. When it fails,
   **iOS skips the read**; it never wakes the GPU in order to read it. Perf counters come from the firmware (device-control
   command 6), not from MMIO. Pstate and residency come from RAM mirrors and the PMGR side (§2).
3. **Our gaps (§3).**
   - We never check `R1+0` bit 29.
   - We never bound the nibble by `maxPstate`.
   - Our check-to-read gap was unbounded: printk and many reads after one check.
   - Several sites read R0 outside any licence (perf60c, r74, r95 banks).
   - Recovery clears `fender_ready` only after the PMGR cycle.
   - No firmware word or doorbell exists that *prevents* a park during an access. iOS has none either: its window is
     closed by being short. Our production never-park pin (RAM `ctrl+0x1040`) is the only "hold" we have, and it is a
     firmware policy, not a lock.
4. **Accessor (§4).** `g5p_mmio_hold()` / `g5p_mmio_release()`:
   - RAM preconditions are checked under a new leaf `mmio_lock`, with IRQs off;
   - then Apple's three-term licence, plus our stricter bit-4-clear term;
   - then at most 8 R0 accesses with nothing in between;
   - then a post-check re-read that marks a sample stale.

   It is legal in IRQ context (no poll) and refuses rather than waits. It does **not** write `R1+0x14`: Apple's reads
   never kick.
5. **Proof plan (§6).** Five rungs. Rungs 1–2 are safe even if the accessor is wrong, because they add no R0 read or
   only add reads where we already read today. Rungs 4–5 are the race cases and carry DFU risk.

---

## 1. Hang cause, per register class

### 1.1 The hang record

| incident | what the firmware was doing | host access at the stop | gate used | source |
|---|---|---|---|---|
| exp 01 (2026-10-22) | not started; Fender never initialised (GPC 0) | `R0+0x18`, PMGR gfx ACTIVE | none | `02-fender-meta.md` [P] |
| r74 case 01 | `meta+0x6c8=1` policy mode; firmware wrote `R1+0x1000 = 0x10` (→ pstate 0) 1.97 ms after the host saw 1; ALIVE storm every 3.3 ms | first of 8 raw R0 clock reads (`R0+0x0…`), ~85 µs and 5 MMIO reads + a printk after one `R1+0x1000` gate | `(x & 0x1f) == 1`, stale | `dsx-r74b-mmio-read-safety.md` §1 [P log, I which read] |
| r95 post-TA | TA just completed (firmware idle) | `g5p_r82_endbank`: gate read `R1+0x1000`, then ~47 R0 reads | one gate, stale | `96-natural-3d-brief.md` §2 [P log, I which read] |
| perf60c (2026-11-02) | release7 park mode (state 2); 3D just completed: firmware idle → governor park | point 2: `readl(R1+0x1000)` unguarded, then `R0+0x160` + `0x6008/6010/6020/6028/6038` if `g5p_gpc_ok` | time-of-check, after retirement | `perf60-fillrate.md` §9.7 [P log, I which read] |
| "page-table edit after a job" (2 kernels) | after a job | "the first access was one `readl(R1+0x1000)`; in the second kernel it was the only register access" | none | `hendrik/a9-reply-20261102.md` §1.2, **second-hand, primary log not located** |

What succeeded:

- the pin-200 probe: a wake, a settled pstate, then 7 R0 reads while the firmware was alive, stuck in its own `0x688`
  poll and not idle [P, brief];
- `render_user_fault_read`: 4 R0 reads at a fault event, when the firmware was halted on the fault [P];
- the r74 `MMU alive` snapshot, 1.1 s into the ALIVE storm [P];
- the production bell path: `R1+0x14`/`R1+0x1000` read before every TA bell, i.e. after the previous job retired, for
  16 min with 0 faults [P, STATUS].

### 1.2 R0 (Rogue registers): bus-level, while the GPC is at or going to pstate 0 [I, high]

- **Why bus-level, not a side effect.**
  - The offsets that hung (`0x0`, `0x18`, the clock/perf block) were read without trouble in the same boots at other
    moments [P, r74 same-boot reads; dsx-r74b §2 table].
  - None of them is a read-to-clear register.
  - What differs between a good read and a fatal one is the GPC state at that instant, not the offset.
  - The CPU stalls on a Device-nGnRnE load that never completes; with 2 cores the other one wedges on the first IPI or
    RCU wait. That is "the whole SoC frozen" [I].
- **Why "going to 0" counts.** r74's sample read `0x10`: target 0, transition in flight. The firmware's setter
  (`0x1001c88c`) writes `q | 0x10` after waiting for bit 4 to clear, and in mode 0 it does not wait for completion [V].
  So between the host's check and its read, the Fender can be partway through powering the core down. Nothing in the
  wrapper blocks a slave access in that state. Apple never issues one: its licence refuses nibble 0 (§2.1).
- **Why after a retirement.** That is when the firmware goes idle, and an idle firmware parks:
  - its governor calls the setter with `q = 0` (state 2 on Linux, the "park");
  - or it runs its power-down path `0x1001cec8`, §2.3.

  iOS shows the same thing from the other side: the firmware mirror of the pstate (`policy+0x34`) sits at **0 for
  96.6 % of idle samples** and at 4 under load [P iOS capture, `r0-160-counter-re.md`]. A read at a fault, or while a
  phase is in flight, finds a firmware that will not park [I].
*(Passage removed: boot-chain or iOS-side tooling detail, out of scope for this repository.)*
- **Clock gating within a powered GPC.** Apple forces the BIF/MMU clock on (`CLK_CTRL[17:16] = 01`) before the indirect
  `e140 → e148` read, then sets it back to auto (`10`) [V `ca5cd4`]. An auto-gated module can return stale indirect data;
  nothing suggests a hang [I]. The accessor copies Apple for that one indirect pair.

### 1.3 R1 (Fender): safe while PMGR `gfx` is on [V Apple behaviour, P production]

- Apple reads `R1+0`, `+8`, `+0x10`, `+0x14`, `+0x1000`, `+0x1004` and `+0x20000` in the power-down checks
  (`isQuiescent` polls `+0x1000` bit 4 for up to 30 s), at every submit, and in the licence, i.e. at pstate 0 and during
  transitions [V `ca66e4`, `ca05d4`, `ca10ec`].
- Its one guard is software: `fender+0xc`, set by `setPlatformPower` (PMGR on) and cleared before PMGR off. At PMGR off,
  `vt+0x18` returns 0 **without** touching R1 [V `ca4d68`].
- No R1 read has a side effect the firmware sees. The firmware touches Fender only at `+0`, `+8`, `+0x1000`, `+0x1004`
  (all four writer and reader sites, unit 0, §2.3) [V]; `+8` is cleared by a write, not by the read.
- Our driver holds `ps_gfx` through runtime PM from first power to `remove` (`core.inc:173`, `:727`) [V]. The
  exceptions are the kexec quiesce and the in-boot recovery cycle (`g5p_kq_cycle`), and during those R1 reads would hang
  too.
- **R1 read in the worst state, direct evidence [P].** Both retained logs read `R1+0x1000` during a firmware
  transition, and the read returned both times: r74 read `0x10` (going to pstate 0) and r73f read `0x11`
  (`dsx-r74b-mmio-read-safety.md` §1.3, §3.2). The state-2 bell runs also read R1 at nibble 0 (`skip-gpc` lines) without
  harm.
- **Open contradiction.** The Henrik reply says one kernel hung with `readl(R1+0x1000)` as its only register access.
  The primary log was not found, and the state at that read is unrecorded. Against it:
  - two logged R1 reads at the worst state, which returned;
  - the production bell path, which reads `R1+0x1000` after every retirement, thousands of times per session, without
    a hang [P].

  Rungs 1 and 1b (§6) are the discriminating tests, and they cost nothing in R0 exposure.

### 1.4 PMGR side (`0x20e080340` gfx gate, PSINFO `0x20e070000`, sequencer `0xa0000`): always-on, safe [P]

Read in every state, including inside the r74 hang snapshot (`actual=f`), and by `perf60-psinfo.py` at runtime.
PMGR state is **not** a licence for R0 (r74 hung with `gfx` on) [P].

---

## 2. The iOS protocol (static, kext + firmware)

### 2.1 The licence: `AGXMetaFirmware_isGPURegisterAccessible` (fw vt+0x290, `fffffff006ca10ec`) [V]

```
if (fw->fender) {
    n = fender->vt18();                 // fender+0xc ? (R1+0x1000 & 0xf) : 0      (ca4d68)
    if (n < 1) return 0;                // parked, or PMGR off (no MMIO in that case)
    if (fender->vt18() > meta[0x710])   // > max pstate (fw+0x268 -> +0x710; 4 on j71t)
        return 0;
    return !(fender->vt78() & 1);       // R1+0 bit 29                              (ca6624)
}
return ((flags & 0x12) == 0x10) || acc->d21 == 1;   // no-Fender devices
```

- No bit-4 test: a transition between nonzero pstates passes.
- No wait, no wake, no `R1+0x14` write.
- On refusal the caller **skips** its reads.

### 2.2 Every runtime R0 access in the kext [V, capstone scan + decompiles]

| access | where | guard |
|---|---|---|
| fault banks `e150`/`e158` (64-bit), then `CLK_CTRL` force, `e140 = ctx`, `e148`, `CLK_CTRL` auto | acc vt+0x740 `ca5c14`, from `reportFaultAndRestartChannels` | licence (`c823e4`/`c824b8`) |
| second bank `e178`/`e170` | acc vt+0x748 `ca5d10` | licence |
| `e178` touch | acc vt+0x878 `ca5ef8`, from the event drain `c98b20` | `acc+0x561 &&` licence |
| register-range dump (71 ranges, `0x11ff8` port select + `0x11200..0x112f8` sweep) | acc vt+0x728 `ca518c`, debug `panic_on_gpu_hang` path | licence |
| IRQ ack `W 0xac8` | `ackFirmwareIRQ` | `d21 == 1` (r108 B5) |
| MTS doorbell `W 0xb00` | submit wrappers `ca05d4`, `ca00a0`, `ca0284`, `ca03dc`, `ca0504` | **none** (after `markKick` `R1+0x14 = 7`) |
| META slave port `0xa00..0xa18`, `0xbf8`, `0xac8` | boot, stop, recovery, event-6 handler | host-owned power transitions only |
| `0x18`, `0x20` ID registers; `0x3c8` poll; `waitForSLCAndBIFIdle` (`8328`, `e228`, `f0a0`, `f0a8`, `W e248`); `waitForMetaIdle` (`8328`) | boot / power-down paths | host-owned power transitions |

The sites the `+0x2d8` heuristic also hit (CL `buildFirmwareWork`, `c7a06c`, `c9673c`, the WQ `+0x758` loads) are
fields of other structures, not R0 [V]. **There is no periodic or timer-driven R0 read on iOS**, and nothing reads the
perf counters or `ROGUE_CR_TIMER` [V within the scan's reach: immediate and register-offset forms after a `+0x2d8`
load].

### 2.3 The firmware side of the handshake: `R1+0` bit 29 [V decode]

- **The tick** (`0x1001cd8c` → `0x1001ce28..ce64`) writes `R1+0 = 0x40000000`, (instruction omitted), and polls it back.
  `0x40000000` is the value Linux reads (585 of 585 `raw R1+00000` samples in the round-7x logs) [P]. So **the tick
  keeps bit 29 clear**.
- **The power-down / clock-change routine** (`0x1001cec8`):
  1. the SLC/BIF/MMU drain `0x1001b638`;
  2. the `R1+0x1004` write `0x1001cce0`;
  3. **`R1+0 = D1.6 | 0x20000000`** (`0x1001cf0c ORT D1.6,D1.6,#0x2000`; META `ORT` ORs the top half, exactly as `MOVT
     #0x4000` gives `0x40000000`), with a read-back;
  4. `R1+0 &= 0xbfffffff` (`ANDMT #0xbfff`, bit 30 off), **only when `[GbP+108]+392 == 0`** (`0x1001cf7c`). iOS's
     `isQuiescent` requires bits 30 and 29 together, so on iOS's normal idle path this clear must be skipped [I];
  5. then `0x1001c88c(0, mode 0)`, i.e. GPC → 0;
  6. then the self-branch at `0x1001d074` (halt).

  The only arm that returns instead is `arg2 == 0 && 0x1000176c() != 0` (`0x1001cf48`/`0x1001d078`). The
  `[..+368] & 4` branch (`0x1001cfe8 → 0x1001d1c4`) calls `0x10017688` and rejoins at `0x1001cff0`, so it ends in the
  same steps 5–6 [V].
- **Cross-check.** The kext's `isQuiescent` requires `R1+0 & 0x60000000 == 0x60000000` (`ca66e4`) and `isIdleBit29`
  exists (`ca6624`). This routine is the only firmware writer of either bit. So: bit 29 = "the firmware has drained and is
  dropping the GPC". **The firmware raises it before step 5.** That gives the host's licence a lead time of the
  intervening few calls. This is the handshake.
- **Correction.** `power-words-init-re.md` §3 (line 178, "`Fender+0x0 |= 0x2000` (kick)") and nx20's
  `fw_gpcStateApply1004AndMasterBit13` read `ORT #0x2000` as bit 13. It is bit 29.
- **The governor's park does not raise bit 29.** It calls the setter with `q` from `0x1001c9b8` (sites `ca44`, `cbc0`,
  `ccd0`, mode 2) [V]. Against a park, only the nibble check protects, and its window is the setter's own pre-poll plus
  the Fender's power-down time [I].

### 2.4 Power states iOS actually goes through [P iOS capture `20261101T154856Z`, bytes read here]

| sample | `acc+0xd20/d21` | `acc+0x498` (idle-off timer armed) | `fw+0xcad` (ALIVE) | meaning |
|---|---|---|---|---|
| idle-a, idle-b | 1 / **1** | 1 | 1 | PMGR on, firmware alive, GPC parked (`policy+0x34 = 0`) |
| load-a, load-b | 1 / 1 | 0 | 1 | running, pstate 4 |
| after-a | 1 / 1 | 0 | 1 | |
| after-b | 1 / **2** | 0 | **0** | idle-gated: firmware stopped, PMGR off (`setPlatformPower` refcount `cc8 = −1`) |

- iOS lives in all three states the licence distinguishes: PMGR off, PMGR on with the GPC parked, and running.
- The idle gate needs `isQuiescent`, which includes bit 29 and GPC 0, i.e. the firmware has run its `0x1001cec8`
  power-down (r108 §3.2).
- The next submit reboots the firmware (`ensurePoweredForWork` → `powerUpAndBoot`) [V r108].

### 2.5 Reading without waking

| quantity | iOS source | MMIO? |
|---|---|---|
| current pstate | `R1+0x1000 & 0xf` (R1, any state with PMGR on), or the firmware mirror `policy+0x34` in RAM | R1 only / none |
| perf counters | `AGXPerfCtrSamplerPreG10_submitCommand6` (`cb3164`): **device-control command 6**, empty payload, `waitDeviceControlConsumed`; firmware handler `0x10005f78` | none on the host |
| GPU / Fender residency, DVD, CLTM | IOReport "GPU Stats" / ApplePMGR perf-state reporting | none on the GPU |
| utilisation windows | `policy+0x8f0..0x934`, `meta+0x784/0x788` (firmware-written) | none |
| fault address | fault banks, licence-gated, read only at a fault event | R0, licensed |

**iOS never wakes the GPU to read a register.** Its only wake is the power-up for work (`ensurePoweredForWork`).

---

## 3. Our gaps (release8 `4ae9dea154`)

| # | gap | where | Apple |
|---|---|---|---|
| G1 | `R1+0` bit 29 never checked | `g5p_gpc_ok()` `core.inc:29` | licence term 3 |
| G2 | nibble not bounded by max pstate (`0x5..0xf` pass with `gpc_any_pstate`) | same | `≤ meta+0x710` |
| G3 | check-to-read gap unbounded: printk, other MMIO, many reads per check (r74: 19 R0 reads per gate; r95: ~47) | historical sites; the current probe and fault read are short | ≤ a handful of accesses right after the check |
| G4 | R0 reads with no licence at all | perf60c (retired), r59/r22 observers (off), `g5p_cache_maintain` diagnostics | none exist |
| G5 | the in-boot recovery and kexec quiesce gate PMGR before any shared flag forbids R1/R0 (`recover.inc:47` cycles, `:53` clears `fender_ready`) | recover.inc, teardown | `fender+0xc` cleared inside `setPlatformPower(0)`, before the gate |
| G6 | the read paths write `R1+0x14 = 7` (probe, fault read) | `g5p_gpu_perf_probe`, `g5p_rv3_fault_read` | reads never kick; `markKick` is submit-only and consumed by Fender hardware (firmware never touches `+0x14` [V]) |
| G7 | no firmware-side read path (DC command 6) for counters | — | §2.5 |

- **Is there a handshake that stops the firmware parking during an access? No, on either side** [V for the kext: no
  host write precedes any licensed read; the firmware reads no host-written Fender word except through `+0`/`+8`/
  `+0x1000`].
- `R1+0x10` bit 0 (`setPowerModeRequest(0)`) is set by Apple only on deferred power-down and is read by Fender hardware
  alone. Whether it blocks a park is untested [I]. It is not part of this design.
- The practical hold on Linux is the never-park pin, which is what production runs.

**Is reading `R1+0x1000` itself the hazard? No.**
- Apple reads it in every state [V].
- Production reads it after every retirement [P].
- r74 and r73f read it at `0x10`/`0x11`, mid-transition, and the reads returned [P].

This is subject to rungs 1 and 1b.

---

## 4. The accessor

### 4.1 API

```c
struct g5p_mmio_ticket { u32 r1_0, gpc, flags; u64 t_ns; };
/* 0 = licensed; -EAGAIN = refused now (parked, bit 29, transition, max); -ENODEV = power epoch not readable */
int  g5p_mmio_hold(struct g5p_diag *g, struct g5p_mmio_ticket *t, unsigned int flags);
bool g5p_mmio_release(struct g5p_diag *g, struct g5p_mmio_ticket *t);  /* true = samples valid */
u32  g5p_mmio_r0_read(struct g5p_diag *g, struct g5p_mmio_ticket *t, u32 off);  /* only between hold/release */
#define G5P_MMIO_MAX_OPS 8	/* R0 accesses per ticket */
```

### 4.2 `hold`, in order

1. **Take `g->mmio_lock`** with `spin_lock_irqsave`. It is a new **leaf** lock: nested inside `event_lock` where both are
   held, never the reverse, and no other lock is taken inside.
2. **RAM preconditions; any false → `-ENODEV`, no MMIO:** `g->powered && g->fender_ready && !g->mmio_off &&
   b->released && !b->stopped`.
   - `b->failed` is **not** required clear: the fault read runs after `failed` latches, as Apple's does.
   - `mmio_off` is new. The quiesce, recovery and any PMGR gate set it under `mmio_lock` **before** `g5p_kq_cycle()`
     (fixes G5); `g5p_fender_wake()` clears it after Fender init.
3. **`r1_0 = readl(R1+0x0)`; bit 29 set → `-EAGAIN`** (G1). We also refuse `r1_0 == 0`: Apple's submit arm treats that
   as a dead wrapper (`ca05d4` vt+0x70 branch).
4. **`gpc = readl(R1+0x1000)`.** Require bit 4 clear and `1 ≤ (gpc & 0xf) ≤ g5p_max_pstate`. `g5p_max_pstate` is
   `meta+0x710` as the driver wrote it: 4 with `boot_gpu_perf`, else the boot table's count. Otherwise `-EAGAIN`.
   - Bit 4 clear is stricter than Apple and costs nothing.
   - **No poll in hold.** A caller in process context that wants to wait loops *outside* the lock: `hold` → `-EAGAIN` →
     `usleep_range(20, 40)`, ≤ 2 ms total.
5. Store the ticket, return 0, **still holding the lock with IRQs off.**

### 4.3 Reads and release

- `g5p_mmio_r0_read()` does a bare `readl`/`readq`; it counts ops and returns `U32_MAX` past `G5P_MMIO_MAX_OPS`
  without touching the bus.
- **Nothing else may run between hold and release:** no printk, no other MMIO, no sleep, no allocation. Format the log
  line after release.
- Indirect MMU reads (`e140`/`e148`) bracket themselves with Apple's `CLK_CTRL[17:16]` force (`01`) and auto (`10`)
  `readq`/`writeq` of `R0+0x0`. Those count toward the 8 ops.
- **`release` re-reads `R1+0x1000` and `R1+0`.** If either differs from the ticket (nibble, bit 4 or bit 29 changed),
  it flags the ticket `stale` and returns false. Then it unlocks.
- A stale sample is data loss, not safety: by then the read has already completed. **The post-check is damage
  accounting, not exclusion.** Apple has the same check-then-act shape; its race is closed only by how short the window
  is.

### 4.4 Where it is legal

- Hard IRQ, threaded IRQ, process context, under `event_lock`, under `g->lock`.
- Never under a sleeping lock held across the window: there is no sleep inside, so a sleeping lock held by the caller is
  fine.
- The bell path keeps its own sequence (`R1+0x14 = 7`, settle, `R0+0xb00`). It is a write, Apple's submit order, and
  it is already proven in production. It should take `mmio_lock` for the `R1` reads and the doorbell, and add the bit-29
  term as a skip.

### 4.5 Policy on top of the accessor

- **Callers should prefer moments when the firmware will not park:**
  - at a fault event (the firmware is halted on it);
  - while a phase is in flight (published, consumed, no completion decoded);
  - at a DC timeout with the firmware alive (the pin-200 probe).

  Directly after a retirement is the worst moment, but with the licence it is no longer forbidden.
- **No host reads of perf counters or `ROGUE_CR_TIMER`.** Use DC command 6 (G7, an RE item: the reply format of
  `0x10005f78`) and the RAM mirrors (§2.5).
- **Behaviour when parked:**
  - `-EAGAIN`, logged once per caller per second;
  - **no wake** (Apple has none);
  - the fault read records `skip-parked`, which is what Apple's report does (no `bif%d_fault` entry).

### 4.6 What it replaces

`g5p_gpc_ok()` call sites that license R0 *reads*:

- `g5p_rv3_fault_read`, which also drops its `R1+0x14` write;
- `g5p_gpu_perf_probe`, likewise;
- the boot/lifecycle observers.

`g5p_gpc_ok()` stays for the doorbell/write paths, with bit 29 added.

---

## 5. What iOS does that we deliberately don't copy

- Apple accepts nibble `1..max` with bit 4 set. We stay stricter.
- Apple rings `0xb00` at nibble 0 (after `markKick`). Our bells skip at nibble 0. In state-0 bell mode that just means
  waiting for the firmware, so we keep it.
- Apple powers the platform off on idle (`d21 = 2`) and reboots the firmware per burst. Linux does not, so `fender+0xc`
  has no runtime analogue beyond `mmio_off` for the quiesce and recovery cycles.

---

## 6. Proof plan (orchestrator; nothing is built yet)

The accessor needs one implementation commit on `a9/release8`. Its build adds one runtime knob, `mmio_selftest` (0600,
default 0, in `a9_gpu_drm`, read live), whose bits drive the rungs below. Every rung is a release8 warm hop with the
production tuple. The package dir is `build/release/release8-mmio`, built the way `release8-pin200` was.

Lines: one `GPU-MMIO sample why=… did=read|skip-<why>|stale r1_0= gpc= v=… us=…` per sample, plus a 10 s
`GPU-MMIO stats` summary (`reads`, `skips` by reason, `stale`).

| # | rung | knob | what it adds over production | safe if the accessor is wrong? | risk |
|---|---|---|---|---|---|
| 1 | **R1-only census** | bit 0: a 1 kHz hrtimer reads `R1+0` and `R1+0x1000` (no R0), idle and under load | R1 reads at arbitrary times | **yes** (no R0; production already reads R1 after every retirement) | low; it settles §1.3's contradiction. A hang here means R1 itself, so stop |
| 1b | **R1-only census across real parks** | bit 0 plus `render_user_switch_park_ms 50` (live): 50 ms state-2 windows at context switches, so the census samples R1 at nibble 0 and during transitions | R1 reads during parks and transitions (the Henrik scenario) | yes for R0 (none); the state-2 bell runs already read R1 at nibble 0 | low–moderate. A hang here confirms the contradiction (R1 itself), and recovery is **DFU** |
| 2 | **licensed R0 at the existing points** | `render_user_fault_read 3` + `boot_gpu_perf_probe 1`, routed through the accessor, **without** the `R1+0x14` write | removes the kick from two read paths that work today | yes: same moments, same registers, fewer writes | low |
| 3 | **licensed R0 at random idle times, never-park** | bit 1: every 100 ms from a timer, `hold` → `R0+0x20` (CORE_REVISION), `R0+0x18` → `release`; expect `0x00090f00`/`0x011b0602` | R0 reads with no job in flight | mostly: in never-park the licence always passes; the risk is only that pin 100 also parks, which the census in rung 1 shows | low–moderate |
| 4 | **park windows** | bit 1 plus `render_user_switch_park_ms 50` (live; 50 ms state-2 windows at context switches) | the licence must **refuse**: `skip-parked` / `skip-bit29` counts > 0, `read` never with nibble 0 | no: a wrong licence reads a parked GPC | **DFU-risk** |
| 5 | **post-retirement, park mode** | bit 2: one `hold` + 2 reads at every 3D completion decision (perf60c's point 2), with the licence; on a park-mode tuple (release7-style, no pin) | the perf60c case | no | **DFU-risk** (owner present, DFU ready) |

Commands (after the build; the netconsole listener runs first as usual:
`scripts/boot/netconsole.sh listen build/omarchy/logs/netconsole-mmio.log`):

*(Device/host command block omitted; it targets the private workspace.)*

- **PASS per rung:** the device stays up, `GPU-MMIO stats` grows, `stale = 0` or rare, the values match, `bad_lines=0`.
- **Rung 4 needs `skips > 0`;** a run with no refusals did not test the race.
- **STOP:** any silence (SSH and netconsole) is DFU, and the last `GPU-MMIO` line names the class. Any `read` with
  `gpc & 0xf == 0` or bit 29 set in the same line means the accessor is broken: revert.

Rung 2 also answers G6 directly: if fault reads and the probe work without the kick, the kick leaves the read path for
good.

---

## 7. iOS (the iPad is in iOS now): no new run needed

- The licence is static code (§2.1).
- The capture already on disk shows the three states (§2.4) and the 96.6 % idle park.
*(Passage removed: boot-chain or iOS-side tooling detail, out of scope for this repository.)*
- If the owner wants one more datapoint, the existing RAM-only power capture can be repeated. It reads the acc and fw
  objects (`d21`, `cad`, the idle timer) at idle, load and after; it does no MMIO and no kernel write. Command as in
  `docs/gpu/experiments/ios-capture-bundle.md`, phase `power`:

  *(Device/host command block omitted; it targets the private workspace.)*

  It decides nothing new for this design. It would only re-confirm §2.4 on a second boot.

---

## 8. For the clock-change drain RE agent (`perf60-clock.md`)

Two decode facts from this lane, without interpretation:

- `0x1001cf0c ORT D1.6,D1.6,#0x2000` sets **`Fender+0x0` bit 29**, not bit 13. META `ORT` ORs the top half, the same
  convention as `MOVT #0x4000` → the device-observed `0x40000000`. This supersedes `power-words-init-re.md` §3 l.178 and
  nx20's `…MasterBit13`.
- `0x1001cec8` reaches `0x1001c88c(0, mode 0)` (GPC → 0) and then the self-branch `0x1001d074` on every arm except
  `arg2 == 0 && 0x1000176c() != 0`; the `0x1001d1c4` side branch rejoins the same path. So it is also the firmware's
  power-down-and-halt route, not only a clock change.
- Its bit-30 clear (`0x1001cf8c`) is conditional on `[GbP+108]+392 == 0`.

One more point for that lane: the host must not write `R0+0x688`/`0x1720` while the firmware's drain may be running
(two masters on the same flush bits). The pin-200 probe only reads them, which is fine.

---

## 9. Ghidra changes (shared project), files, reproduce

- **Rename:** `fffffff006ca10ec` `FUN_…` → `AGXMetaFirmware_isGPURegisterAccessible` (+ PRE comment).
- **Comments, `mmio-access:` prefix:**
  - PRE: `ca518c` (licensed register dump, vt+0x728);
  - EOL: `ca5c14` (fault bank + `CLK_CTRL` force), `ca5d10` (`e178`/`e170`), `ca6624` (bit 29, firmware writer),
    `c98b30` (licensed `e178` touch).
- **Saved:** `scripts/ghidra-mcp.sh save` → `SAVED ok` (2026-11-03, after two deferrals while another lane was
  active).
- **Files:** this doc only. Scratch scripts in `/tmp/mmioacc/` (not part of the repo).

*(Device/host command block omitted; it targets the private workspace.)*

## 10. Claims ledger

| claim | label |
|---|---|
| Every runtime R0 read in the kext is licensed by fw vt+0x290; the doorbell write is not | [V] (scan: immediate and register-offset forms after a `+0x2d8` load; indirect bases beyond that not enumerated) |
| The licence = powered flag, `1 ≤ nibble ≤ max`, `R1+0` bit 29 clear | [V] |
| The firmware sets `R1+0` bit 29 before GPC → 0 in `0x1001cec8`; its tick rewrites `0x40000000` | [V decode] |
| The governor park does not set bit 29 | [V] |
| iOS idles both GPC-parked (`d21 = 1`) and PMGR-off (`d21 = 2`) | [P capture] |
| Perf counters come from DC command 6 | [V] (data format unknown) |
| R0 hangs = no bus response at GPC target 0 | [I, high] |
| R1 reads are safe with PMGR on | [V Apple, P production]; one second-hand counter-claim, rung 1 |
| No firmware "don't park" handshake exists | [V kext side], [I firmware side] |
| The accessor makes post-retirement reads safe | **unproven**; rungs 4–5 |
