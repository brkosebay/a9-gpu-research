# r74e: bounded pre-ALIVE power transition and one-shot submit

r74d's corrected render path was never reached on device. The first ALIVE was
observed by the poll path before IRQ174, but only the IRQ path owned the immediate
cmd8 submit. Poll-side snapshots and optional PMGR/MMU reads delayed submission by
about 492 us; R1+0x1000 had already changed from active (1) to 0x10/0 and the
submit returned `-EHOSTDOWN`.

r74e bounds the release-side GPC-off and GPC-on polls to 1.0 ms and 1.8 ms.
Either poll stops once its loop head observes ALIVE. There remains a narrow
check-to-read race, and the successful functional submit intentionally reads R1.
A failed transition suppresses the old optional failure snapshot. On success,
r74e skips post-release diagnostic snapshots and gives poll and IRQ observations
one serialized one-shot submit helper. The functional Fender/active-state
sequence contains no optional diagnostics before the doorbell. If the active
window has closed, r74e voids rather than re-ringing the doorbell during the loop.

The r74d render path is byte-identical: `render_r45_order=0`,
`render_order_variant=0`, exact r71 stream/PM tuple, and only the redundant second
`g5p_r22_mmu()` pass omitted in policy RAM-only mode.

The gated runner also checks that the cold source entry is staged before it
creates `/run/g5p-r74e-source-used`, so the known "pristine dtb unknown" refusal
does not silently burn a clean epoch.

## Device result: direct cold boot

The decisive successful construction was run directly on the cold
`tri74e-bd247eba0f` boot, without warm kexec. GPC1 reached active in 552875 ns,
the first-ALIVE cmd8 was published and consumed, and render preparation returned
zero for the first time. The two DC3 records were then committed coherently and
the control producer advanced from 1 to 3. The immediate pre-kick check found
the policy window inactive and returned `-EHOSTDOWN` before the doorbell, so no
TA was published.

The corrected verdict is `attach-published-not-kicked`. This establishes two
separate facts: warm-kexec GPU cycling was the GPC1 bootstrap confound, while
the next natural-policy blocker is synchronizing DC3 and TA doorbells to the
firmware's active/ALIVE window. The records and producer are immutable while
pending; r74f owns the delayed one-shot kick experiment.

## Build

The final entry, commits and payload hash are written by
`scripts/gpu/write-r74e-ready.py` after all offline gates pass. Exact parents:

- `a9/gpu74d` at `75fc01bdf105acabe1769b4434f7387324cd26e5`
- `a9/tri74d` at `7b4888fa5d9908ac8b6dc1905afc8ec3f4c514bb`

Required gates: strict checkpatch, both G5P object compile gates, full Image and
DTBs, W=1, clean branch, irqfix identity, cmdline/initramfs identity, manifest,
analyzer fixtures and host preflight.

## Device order

One decisive case only, from a fresh DFU/cold GPU-untouched source epoch with
netconsole live. Never chain or retry on the same GPU epoch.

Pre-registered outcomes are `natural-ta-complete`, `ta-consumed-stalled`,
`ta-not-consumed`, `attach-published-not-kicked`,
`attach-kicked-not-consumed`, `hard-freeze`, `void-gpc1-activation-failure`,
`void-power-transition-failure`, `void-active-window-closed`, or another
construction/infrastructure void.
