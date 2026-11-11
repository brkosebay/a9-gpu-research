# r96 brief: the natural 3D after the proven natural TA complete (pre-registration)

2026-10-30. Claude Sonnet 5.5, r96 implementation sub-agent. Host only until the owner flies it. Labels: **[V]** read or run this session (file, command); **[D]** derived, argument stated; **[RELAYED]** from another lane's report (cited); **[UNKNOWN]**.
Control: the flown r95 stage `build/gpu/round95/raw/20261030T152707Z/stage01-attempt1` (`tri95-29134a97b7`, payload `97433f09...b3e807`): the exact r94 PDS contract with every page mapped reached the first **natural TA complete** (stamp 1, PM saved, consumer = producer = 1, G2 completion event 33, `render-fixed-ta result=0`) [V netconsole]. Nothing of the TA outputs survived: the freeze took the blob with it [V].

## 1. What r96 is

`boot_r96_cfg` (23rd module parameter; the 22 of r95 unchanged, `scripts/gpu/r96-spec.py`): `0` exactly r95; `1` publish the natural 3D once right after the natural TA RAM-complete and watch it RAM-only for 12 s, **zero register access from the TA complete until reboot** (default stage); `2` the same plus ONE doorbell `0x11` after r74g's grace if the 3D ring is still pending, owned by the ALIVE decoder through a real 3D bell kind (`G5P_R74F_3D`: ring `0x64`, bell `0x11`, queued count 1; never the DC3 self-drain branch). One stage per cold epoch, one attempt, no analyzer-driven retry. Kernel `a9/tri96` = `a9/tri95` + one commit (patch 0156): `r96-frag.h`, `render-r96.inc` (new), hooks in `boot-r73b.inc`, `boot-r74f.inc`, `boot-r80.inc`, `render-fixed.inc`.

Nothing before the TA complete changes: the r94 PDS pair, the r95 mapped-output setup, stream, W, PPP, PM, attach are byte-identical [V `test-r96-preserve.py`]. No PTE, PM, W, code or stream edit; no new GPU VA (the inherited PM free-stack VA `0xE1_C026_4000` is >= 2^38 as in r88/r94/r95 and is printed in `R96 va`; Henrik's A10 bracket says buffers stall at `0x40_`/`0x80_` but did not isolate the free list [RELAYED]). The freelist-lease patch of `freelist-lifetime-production-fix.md` is **not** integrated: the serial path already prevents TA(n+1)/3D(n) overlap [RELAYED].

## 2. The freeze, and what r96 does about it

[V r95 raw, `r95-post-ta-freeze-analysis.md`] After `result=0` the host read the boot id (answered), then wrote `r73b-export` to `command`; `r73b-export-rc` never came. The first and only register access of that command is `g5p_r82_endbank()` (gate read `R1+0x1000`, then ~47 registers) [D: circumstantial, the bus-hang read is not identified; the IRQ-thread plateau bank slot 1 may overlap].
r96: `g5p_r96_quiet()` (called the moment `r->retired[0]` is set) makes `g5p_r82_endbank`, `g5p_r85_irq_bank` and `g5p_r80_irq_bank` return early, so a completing boot reads no register after the retirement. While the TA does not complete the banks are exactly r95's.
**Tier A (kernel, RAM, before the 3D is published):** 18 object digests (FNV + SHA-256) at four checkpoints (pre-publish, published, consumed, end); the console copy of S (`pm+0x80`, 0xc0 B), the PM control head, the region image, the TPC page and aux0 as non-zero 32-byte rows with a row count and a running FNV (`R96 cap-end`), so a dropped UDP line is visible; blob dumps of region, RT0, TPC (0x4000), PM control, aux0 (0x4000) and the TA W (0x560); the pixel classes of the target page before and after; a 1 Hz `R96 alive` heartbeat in the window and a final one before the command returns.
**Tier B/C (host, `run-control-host-r96-stage.sh`):** RAM-backed sysfs files first, one ssh per file, each saved and marked `.done`; then `r73b-export` (RAM-only now); the blob again, `fw_trace`, `dmesg`; then a 60 s liveness poll of `/proc/uptime` (no MMIO). Never SIGTERM the campaign while it recovers.

## 3. The 3D leg (apple-3d-fragment-contract-exact.md, C1-C7 [RELAYED], what is implemented)

| item | in r96 |
|---|---|
| C1 no MMIO after the retirement | `r96_quiet`; end bank, r85 and r80 IRQ banks skipped; `g5p_r52c_before_3d` is never called |
| C2 refusals before publication | `r94/r88 edited`, canary 0, armed, `W+0x88 = 0x100`, attached, TA retired / consumed / PM saved / stamp 1 / ring c = p, no fault, `!submitted[1]`, ring state, `0x25/0x26/0x40000017`, `W3D+0x7f0/0x7f4 = 0`, stamp words, dependency `{4, TA stamp+4, 1}`, 3D stamps 0, S non-zero, idle `0x724/728/72c = 0`, r52h/r52f/r37 off |
| C3 RAM snapshot before the kick | Tier A above (`S`, region, TPC, aux0, TA W, PM control, F-stack digest, stamps) |
| C4 the W3D words | 17 words checked exactly before publication (`0x30810`, `0x30800`, `0xa8 = 0x14`, `0x2bc0`, `0x402`, `0x28c0/0x2840`, `0x00040004` x2, `0x3c0 = 0x0021000f`); relocation and ISP_RGN are **not** touched |
| C5 publish and doorbell | record `{1, meta(1), base+2, 0, 0}`, `WORK_CTL+0x40 = base+2`, producer last (the order of `g5p_r74f_publish_ta`); cfg 2: real 3D bell kind, ALIVE-owned, fenced, `-EHOSTDOWN` = wait for the next ALIVE; the DC3 self-drain trap is closed in code (`kind == G5P_R74F_DC3`) and the old `g5p_r74f_bell` refuses the 3D kind |
| C6 witnesses | RAM only: ring consumer, `W3D+0x7f0/0x7f4`, 3D stamps, control words, idle words, PM words, the firmware retirement predicate, `G2` events on the console; target page classes and digest |
| C7 if it parks | the RAM snapshot first; the one-factor arms (W3D `0x5e8..`, ISP descriptor, PM F re-address, PM id 3) are not in r96 |

The publish receipt is the TA's own format with engine 1: `RENDER publish engine=1 slot=7 endpoint=2 kick=0 W=c0258400 sequence=1 identity=1` (kick 0: no doorbell in the publish). The userspace lane's `a9c_parse_publish` reads it (engine 1, slot 7), which settles the lane's "INFERRED engine=1 receipt" [V `r96-a9c-crosscheck.py`].

## 4. Other lanes, placed

* **Userspace (tools/mesa-a9) [RELAYED]:** no parallel record contract. `scripts/gpu/r96-a9c-crosscheck.py` runs the lane's real `a9c_ctx_lint`, `a9c_program_shape`, `a9c_early_block_present`, `a9c_cot_consistent` and `a9c_slot_check` on the TA record r94/r95 flies (all pass: layout B, early block 24/24, `TE_PSG = 0x20000`, slots 8/7) and on the sealed r88 record (refused: `-EDOM`, shape `-EINVAL`, block 0/24), so the kernel recipe and the Mesa lint agree.
* **Henrik, A10 reply 2026-10-30 [RELAYED]:** the retained A9 block at `B+0x100` is exactly his iOS shape (a two-dword data block, then an end-and-halt instruction pair at +0x20), which resolves r94's "data vs code" as both; the USC jump at `B+0x40` is followed by `c000` padding to `B+0x80` (verbatim in r94); the fixture code BO has 11 (control) and 12 (factor) `0100 01pp 0000` jumps and **no** padding hazard (`r96-a10-audit.py`). A10 never isolated `0x470` alone: the full context mapping `0x428/0x438-0x460/0xcc0/0xf058-0xf070` is already carried by our record (those words are non-zero in the W the lint accepts); `0x440-0x460` and `0xf058-0xf070` are in no register bank and are not read in r96.
* **Presentation (tools/gpu-present-a9) [RELAYED]:** display is not part of the kernel experiment. `scripts/gpu/r96-frame-export.py` turns the captured target page (64 x 64, dwords already XRGB8888) into the raw tile, a 1536 x 2048 pitch-6144 canvas (the lane refuses a smaller frame), a PPM and the exact `a9present present --src-file ... --mode copy` line (SETCRTC first; PAGE_FLIP, DIRTYFB and G5P dma-buf import are unproven). r96's target BO is not a dma-buf, so the `A9P_CTRL_FD` producer contract belongs to the typed path.

## 5. Pre-registered outcomes (`scripts/gpu/r96-outcome.py FOLDER`, post hoc, never from the runner)

`void` | `ta-not-complete` (r95 not reproduced) | `refused` (names the field) | `freeze-before-publish` | `freeze-in-window` | `3d-fault` | `3d-published-not-consumed` | `3d-consumed-not-complete` | `3d-complete` with the target class `triangle-exact` (4096 = oracle, 1152 red / 2944 blue) / `clear-only` (all blue) / `untouched` (all `0xa5a5a5a5`) / `partial`. Beside every class: the 3D timeline, the bell record, the checkpoint objects whose digest moved, the `G2` events after the publish. n = 1; a hang class is not retired by one run (the A10 USC padding hazard is audited offline, none found).

## 6. Not in r96 (and why)

Clear-only as its own stage: the fixture has one 3D record (the quad) and no captured clear-only 3D record; a blue-only result is classified, not built. PM id 3, `W3D+0x28 = 0x11`, W3D relocation, ISP_RGN `0x50`: the exact-3D report says keep ours [RELAYED]. The freelist lease and TA(n+1)/3D(n) overlap: production hardening after first pixels. A post-completion register bank: a later, separate command only after a sealed folder (`r95-post-ta-freeze-analysis.md` 5.5). A 120 s delayed-work heartbeat after the command returns: the in-window heartbeat and the host liveness poll cover it.
