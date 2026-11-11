# R34: the TA end path (macrotile base, TE_PSG soft completion, off-map region headers)

2026-10-24. Kernel `a9/gpu` **`e63e41673b`** on r33 `151170a3cf`. The identity,
payload and commands are in `34-device-tests.md` (not published). Input:
ds-r34-a. Offline only: no device run is claimed.

## Where r33 left it

- **Case 01 `clip-probe` returned `clip-ignored`.** The 0x500-byte
  region-header image after finish24's store does not change when the PPP
  terminate clips to tile (0,0). The image is built from the TE/PPP
  registers (`0xc18`, `0xc98`), so it says nothing about whether a
  terminate arrived.
- **The warm jump into case 02 died in PCIe/NVMe link training.** This is a
  boot-infrastructure failure (round8e-link-fail-tri33).
  Round 8f addresses it, and tri34 carries 8f. Cases 02–06 never ran.

## The ds-r34-a reading, checked here

ds-r34-a says the TA raises TA_FINISHED only after the TE executes the
tile-list terminate:
- one region-header entry per macrotile into `TE_PSGREGION_ADDR`;
- every tile list terminated;
- the tail-pointer cache (TPC) invalidated.

Our job asks for exactly that (`TE_PSG` = `0x00020000`, completeonterminate
= 1). It never writes a byte of it, nothing faults and nothing stays busy.
The RT-dataset scalars match Mesa for 64×64, so only the bases are suspect.

**The firmware emulator confirms how start23 loads the three words** (`tools/gpu-fw-emu/replay.py`,
outputs in `build/gpu/round34/fw-emu/`):

| W word | R0 register | how |
|---|---|---|
| `W+0x38/0x3c` | `0xc00` | **64-bit, verbatim**: 0x1_01040001 → `0xc00 = 0x101040001`; 0x3_00000000 → `0x300000000` |
| `W+0x3c0` | `0xc28` (TE_PSG) | 32-bit: 0 → `0xc28 = 0` |
| `W+0x28/0x2c` | `0xc38` (region headers) | 64-bit: 0x1_01080000 → `0xc38 = 0x101080000` |

So r31-01 (`W+0x38 = 0x3_00000000`) really did write `0xc00` as a 64-bit
value, and `0xc04:0xc00` still read `0:0` at every stage. Either the
register is not readable, or a cleared bit 0 (a valid bit) drops the write.
E2's value sets bit 0 on purpose.

## The r34 factors (root-only `0600`, default 0, latched at prepare)

At most one per epoch. None of them combines with an earlier factor:
prime, the second job, code base, clock, reset, core table, the r30
factors, or start. The re-arm for a second job rebuilds W, and code base
bit 0 owns `W+0x38`. Before editing, each factor checks that the fixture
word it replaces still has its decoded value (`W+0x28` = RT, `W+0x38` = 0,
`W+0x3c0` = 0x20000).

| Parameter | ds-r34-a | Effect | Streams / wait / stage |
|---|---|---|---|
| `render_r34_mtile=1` | E2 | Maps a new zeroed 16 KiB page at **0x1_01040000** (ci 4 / di 8 / ti 16, the RT leaf table) and sets `W+0x38` = **0x1_01040001**. The page exists only on an mtile epoch, so every other catalogue equals r33's and E3's off-map claim holds. | empty (1), E1 (4), triangle-stride0 (7); real 0x801 wait; TA-only, or the **pair on stream 4** (a real frame against the r22 oracle) |
| `render_r34_mtile=2` | E2 granularity | The same page, `W+0x38` = **0x1_01040010** (128-bit but not 512-bit aligned, no bit 0) | as above |
| `render_r34_te_psg=1` | E1 | `W+0x3c0` = **0**, so `R0+0xc28` = TE_PSG with completeonterminate = 0: "force an Interrupt" at the terminate, with no header or TPC work | empty only; the real wait or the r31 TA_TERMINATE wait (`render_event_variant=1`, the ladder case); TA-only |
| `render_r34_rgn=1` | E3 | `W+0x28` = **0x1_01080000**: 512-bit aligned, ti 32, absent from the render catalogue. A TE header write faults. | empty only; real wait (finish24 never runs and cannot write headers); TA-only |
| `render_r34_observe` bit0 | observation | At every render checkpoint, reads `R0+0xc00/0xc04/0xc28/0xc38` and **`0x130`/`0xb20`**. Each was read mid-job on this device before (r24, r31). | any |
| `render_r34_observe` bit1 | observation | The macrotile page at every checkpoint: FNV, nonzero count, up to 32 nonzero 32-byte rows | mtile epochs |

The 3D W is unchanged. The E2 pair keeps the fixture's 3D side
(`td+0x20` = RT). No 3D macrotile field is known.

`render_status` reports `revision=34` and adds:

```
r34 mtile te_psg rgn r34_observe mtile_mapped r34_reads c00=<c04>:<c00> mtile_nonzero
```

## Analyzer (`scripts/gpu/analyze-render-r34.py`)

- It runs the r33 → r28 chain with `revision=34`.
- r33's `summarize` is now chainable.
- r31's `W+0x38` integrity check admits the r34 macrotile value.
- The r34 layer first checks integrity. The inputs record must exist and
  carry the selected after-values (`W+28`, `W+38`, `W+3c0`, `mapped`). With
  observe bit0, a post-kick read-back must exist. With bit1 on an mtile
  epoch, the page record must exist. Any miss gives `stop-inspect`.
- Integrity stops (`capture-error`, or `stop-inspect` from any layer)
  are never relabelled. Two cases still reach the r34 layer:
  - **Analytic verdicts**, whatever their reason text says. On an E1
    positive, r31 relabels the retirement `terminate-retired` with the reason
    "…only TA_FINISHED (bit 5) is missing…". That word must not end the
    chain.
  - **r33's relabel of a non-integrity r28 stop**, for example an incomplete
    retirement predicate, kept in `r28_stop`. The r34 reading rests on
    events, faults and the read-back.
- The event bits come from three sources:
  - every checkpoint's `0x130`;
  - every checkpoint's `0xb20 >> 6`;
  - the 20 ms flight v2 accumulators.
- The verdicts are listed in `34-device-tests.md` (not published).

## Limits

- **The only hard positive for E2 is a natural retirement**:
  `mtile-finished`, then the pair. The read-back and page verdicts are
  weaker readings:
  - `0xc00` may be write-only, as r31-01 suggests.
  - The SLC can hide a content write. PM PTEs carry no cache-bypass
    attribute.
  - The empty stream may not write the macrotile array at all. The full
    stream on a warm boot needs the stale-index fix (`tri-stride0-clean` →
    `mtile-tri`).
- **The `0xc00` role is an inference.** The candidates are `PM_MTILE_ARRAY`,
  `TA_RTC_ADDR`, `TA_CONTEXT_STATE_BASE` and `PM_VHEAP_TABLE`. No header in
  the workspace names `0xc00`.
- **E1 is defined against r31-06**: the same empty stream, the same
  TA_TERMINATE wait, `terminate-not-raised`. Only `W+0x3c0` differs. cr.xml
  does not say which event bit "force an Interrupt" lands in, so bits 5 and
  6 are both read.
- **E3 trusts the BIF fault latch.** A positive needs the fault VA inside
  0x1_01080000..+0x4000. No fault plus a stall is a negative that only
  confirms E1's negative.
- **E3 adds no fault acknowledge, as in every round.** The latched fault
  stays until the next kexec's GFX power cycle, the same as every vertex
  fault since r27.
- **Leftover r33 cases.** Kept: prime-empty (H-hist), tri-stride0 (warm
  index) and gfx-off (knob A, last because it is a new PMGR operation).
  Dropped: repeat-auto and flight-empty. Every r34 case already records the
  no-factor observation, and repeat-auto depends on a mask-0 second job
  that prime already exercises.
