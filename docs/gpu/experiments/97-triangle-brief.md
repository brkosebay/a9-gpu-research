# r97 brief: the app draw g0 (a red triangle over r96's blue clear) and the 20 s TA budget (pre-registration)

2026-10-30. Claude Sonnet 5.5, r97 implementation sub-agent. Host only until the owner flies it. Labels: **[V]** read or run this session; **[D]** derived, argument stated; **[UNKNOWN]**.

**The TA that r96 flew was geometry-free by construction, so "the exact working TA, now with a triangle" cannot literally hold.** [V `r97-spec.py --check`, audit section] The VDM page the kernel has flown since r88 (df-m176 plus the r94 PDS contract) executes only **g1**, the driver's end-of-command-stream strip (PRE = round16 `vdm[0x224:0x268]`, Q7 = the g1 list). The application draw **g0** (round16 `vdm[0x1b8:0x224]`, the 3-index list that is the triangle) is not on the executed walk. r96's 64x64 frame (4096 blue, 0 untouched, 0 other, sealed, exported, displayed on the iPad) is therefore the geometry-independent 3D background clear (W3D+0xc0 clear DMA + EOT): the fragment / PBE / EOT path is proven, and nothing about primitives, the TPC or PM consumption was exercised. r97 flies the first TA that contains a real draw.

## 1. What r97 changes (two things, nothing else)

`boot_r97_cfg` (24th module parameter on top of the 23 keys of the r96 stage-1 tuple; needs `boot_r96_cfg=1`; `r97-spec.py`): `0` exactly r96; `1`:

1. **Three dwords of the TA VDM page.** The control page already carries g0 verbatim at `+0x400..0x474` (start-present variant, count 3), behind a LINK nothing references. The edit: `VDM+4` `0x40500 -> 0x40400` (the head LINK now reaches g0) and one `LINK(0x80000001, 0x40500)` over the first two dwords of the dead copy of g1's state at `+0x474` (back to the unchanged r88 page). Executed order: LINK -> g0 -> LINK -> P -> Q -> flood -> T, i.e. Apple's own g0, g1 order with the r88 flood kept exactly as r94 / r95 / r96 flew it. Walk pins 381 / 5 / 191 / 1 / 4 / 179 / 1 / 0x1100, page sha256 `a2f6388b...`, execution digest `e5375681...`. PPP, code, state, static, W, PM and mappings are unchanged. Every pointer g0 dereferences resolves inside a mapped fixture BO that equals round16 (PPP `0x8c0e0 / e8 / 100 / 10c`, the viewport block at scratch+0x63e8, the vertex DMA at state+0x2c0 -> vertices (-.75,-.75), (.75,-.75), (0,.75), code+0x2680).
2. **`render_wait_ms = 20000`** (the kernel range 3000..30000, so 30 s is the hard cap). [V `r97-spec.py --budget`, recomputed from the raw netconsoles] r96's two "TA timeouts" were a genuine type-1 completion event at **publish + 12.006 s**, 3 ms after the old 12.000 s cap; r95b took 11.02 s, r96's success 0.11 s; the latency is spent inside the firmware's `start23` before it returns (the host cannot shorten it). 20 s is 1.67x the slowest completion seen. All 18 old `render_wait_ms == 12000` admissions moved deliberately to `g5p_r97_wait_expect()` (20000 iff `boot_r97_cfg`, else 12000). One final RAM-only pass after the budget catches a completion that raced the deadline. On **every** no-completion exit of the wait (budget timeout, failed drain, ring protocol error) the kernel latches `quiet` (the export end bank and the two IRQ banks then read no register) and the host runner **skips** the `r73b-export` command (`r73b-export-skipped=no-ta-complete`): after a timeout there is no R0 / export / MMIO, and the netconsole is the evidence. (r96's two timeouts froze the SoC in exactly that export.)

## 2. The oracle and the result classes

Oracle = round16 `expected-linear.bgra` (also the fixture oracle at offset 1510944): **1152 red + 2944 blue** pixels (analytic area (1.5 x 1.5 / 2) / 4 of the 64x64 viewport = 1152). Eight witness pixels (four inside, four outside) are pinned in the spec and the kernel header. The **authoritative** capture is the raw 16 KiB `R96 target-end` page dump compared with the oracle (`r97-outcome.py`, `target_capture`); the kernel prints its own counts and class (`R97 target when=ta-complete|end`, `R97 wit`) which the reader compares, and the legacy `render_status` pixel counters (`R97 legacy ...`) are recorded separately and are **not** the verdict.

| class | rule |
|---|---|
| `untouched` | every pixel still the `0xa5a5a5a5` prefill |
| `clear-only` | all 4096 pixels blue: the background clear, no geometry (r96's result; g0 contributed nothing) |
| `triangle-exact` | every pixel equals the oracle |
| `triangle-approx` | >= 1000 red inside the oracle triangle, <= 64 red outside, no untouched / other pixel |
| `partial` | anything else |

Beside the class: the TA timeline (`late_vs_r96_cap` = a completion after 12 s, `watchdog_like`, IRQ / event deltas, stamp), the `ta-timeout` class (20 s + final pass without a completion; quiet, no export) and the older r96 classes (`ta-not-complete`, `freeze-*`, `3d-*`).

## 3. What stays unproven (the datum)

A natural TA with **real primitives**: whether the TPC / PM free-stack consumption a draw implies completes in the same firmware latency class, and whether the 3D consumes what the TA produced. A `clear-only` result would say the draw was executed but produced no pixels, or was not consumed (a new datum, not a failure of the clear path); a timeout or freeze are new data. n = 1: classify, do not retry. A second arm (the same g0 + g1 with the flood off) is deliberately **not** built.

## 4. Gates (all host)

`r97-spec.py --check` (page, pins, g0 / oracle audit, 24-key tuple, budget proof), `test-r97-kernel.py` (the real `g5p_r97_*` functions and `g5p_r74b_wait_ram` in virtual time: completions at 0.11 / 11.02 / 12.006 / 19.99 s and on the final pass at 20.000 s complete, 20.001 s times out, silent firmware ends at 20 s with quiet latched and no end capture, `boot_r97_cfg=0` is exactly the r96 loop), `test-r97-mutants.py` (every mutant must fail the kernel gate), `test-r97-preserve.py` (only five files differ from a9/tri96, the only removed lines are the 18 pinned admissions, the loop condition and the inverted r96 parameter text), `r97-budget-check.py`, `r97-parent-evidence.py` (the sealed r96 flights), checkpatch 0/0/0, W=1 clean.
