# r83: what is missing between start23 and the first TA output (root-cause synthesis, build-ready r83 brief)

*(Passage removed: boot-chain or iOS-side tooling detail, out of scope for this repository.)*

## 0. Owner summary (plain language)

**There is no missing kick.** Every launch action start23 performs is accepted by the hardware, and the hardware then finishes a short start-up of its own and goes completely idle with the TA still "open" and nothing produced. In the microsecond flights the tiling engine (TE) lights up when `0xc68` is written, the vertex master (VDM) starts when `0x400` is written and runs its cursor to the end of the stream in 1-8 µs, the parameter manager (PM) is busy for about 4 µs, and about 6 µs after the TE lit up everything reads idle. At +102 ms after the kick in a natural stall the idle register `JONES_IDLE (0x8328)` reads `0x3d7f` = every unit idle, the stream cursor `0x410` sits at the terminate word, `TA_FINISHED` is not set, and no tile pointer, region header or PM page has been written. r82 showed the same with the event path taken out of the picture.

**Strongest missing thing (ranked, not proven):** the tiler/vertex-collector side never receives the geometry or the terminate. The best-supported reading is that the TE and the PM finish their ~5 µs arm handshake without the TE0/ALIST0 PM clients ever being set up (the TE and ALIST lanes `0xe028/0xe048` stay undescribed in every Linux boot, the PM did no allocation, Apple's PM always describes them). The retained evidence cannot separate that from a break one step earlier (vertex collector to PPP). **No single register value, strobe or kick is identified.**

**Confidence:** no missing/rejected strobe or kick: about 95%. The break is upstream of TE data acceptance (nothing ever enters PPP/TE/PM allocation): about 75%. The specific PM client/context setup as the cause: about 35% (ranking in section 5). A one-line fix: none exists in the retained evidence, so there is no case A.

**Exact next run:** r83a, one device boot (up to two attempts if the first never releases), no firmware change, no bypass: the proven r80 stage-7 construction (`ctrl0 0x9`, marker 3, IRQ-owned bank at least 100 ms after release) with the bank widened from 28 to 41 registers by one 8-line kernel patch (section 7). In parallel and independent of the Linux device, the orchestrator should schedule the Apple positive-control reads from section 7.6 (`0x5020/0x5028/0x5110/0x5120`, `0x420`) because they decide whether the PPP/TE signature registers mean anything at all.

## 1. start23, exact hardware order (CODE, with the hardware's answer)

`start23 = 0x8000672c`. Order from `sonnet55-start23-byte-decode.md` section 2.2 and the executed replay `build/gpu/ds/ta-start-events.json` (67 MMIO accesses; fixture values, real runs read the same landing values: S7 bank column). Block = which hardware unit consumes it. **Acceptance witness** separates "the store executed" from "the hardware did something because of it".

| # | firmware PC | access (R0 offset = value) | block | acceptance witness (hardware's answer) | grade |
|---|---|---|---|---|---|
| 1 | `0x10017d84/9c/b4` | `0xf078`, `0x136c`, `0x136d` = `0x08` (byte) | requester context map (TA slot) | readback `0x08` | OBSERVED (PRIOR boundary map 2.5) |
| 2 | `0x80006758` -> `0x800022c0(1, id)` | none when stored identity == id (Linux id 0 = iOS context A id 0); else `0x210 0x218 0x220 0x230 0x390 0x398`, `0x2b0`, `0x2a0` | PM identity bind | n/a (path skipped in the replay) | CODE; iOS context A is also (slot 8, PM id 0) `ds-r35-a` |
| 3 | `0x80007678 ...0x80007d50` (63 stores) | `c78=0x88 c88=2 c98=0x3f003f c18=0x1001 c08=c10=0x10100c c20=0x10 d20=0 ce0=1 c28=0x20000 c90=0x1e3ce508(x2) c38=0x1_01020000 c40=0x1_01030000 c00=0 c80=0x88 428=0x1_00086240 cc0=0x1_00086040 438..460 (store/resume tasks) cb0=0 470=len 420=0 418=0x1_00080000 408=0x1_0004_0000 f058..f070 f038 f040`, then 6x (`0x11ff8=i`, `0x11030=0`), `f000..f018=0` | TE/PPP/VDM/TA-context register file | landing registers read back at +102 ms: `c18 0x1001, c28 0x20000, c38 0x01020000, c78 0x88, c80 0x88, c88 2, c90 0x1e3ce508, cc0 0x86040, 428 0x86240, 438 0x24001002, 43c 0x00030005, 470 0x370, 408 0x40000` | OBSERVED (S7 bank). `c00 c08 c10 c20 cb0 d20 ce0 418 440-460 f0xx 11030` not in any post-kick read (UNKNOWN landing; c08/c10/c20/ce0/d20 equal their reset values so they cannot discriminate) |
| 4 | `0x80006784` -> `0x1001e930` | none (CDM mask `rec+0x34` = 0) | CDM | n/a | CODE |
| 5 | `0x800067b4` -> `0x10005f30` | `0x3d0 = 0x1_00000100` (64-bit), `0x240=0x1_01000000`, `0x248=0x1_01010080`, `0x2d8=0x1_01000080`, then `0x290=1`, `0x198=1`, `0x258=1`, each write-1 / poll bit 0 | PM (bank select, aux windows, three load pokes) | `3d0 0x100`, `240/248/2d8` read back; pokes read 0 immediately (self-clearing: 0 = accepted or never latched) | landing OBSERVED; **poke acceptance is only inferred** (PM+VDM clock-request bits and a BIF blip appear ~6 µs before `c68` in the flights, INFER) |
| 6 | `0x800067bc` -> `0x80009138` | `0xcb8 = 1` poll bit 0, then `0xc68 = 1` (`0x80009178`, no readback) | TE (context command port, then the TE arm) | **`c68`**: reads 1 for exactly one 2.2 µs flight sample, TE `JONES` busy bit sets in the same sample (r47-04 405.292 µs), `c68=0` next sample. `cb8` was never seen set in 1440/1440 reads, so its acceptance is unknown | `c68` OBSERVED (6c8=0 flights); `cb8` UNKNOWN |
| 7 | `0x800067d0..f4` | RAM only: `G+0x728=1`, `G+0x724=0`, `G+0x730=ctx` | firmware | host sees `G+0x728=1` (this is "release") | OBSERVED |
| 8 | `0x80006808` -> `0x80009120` | **`0x400 = 1`** (the only store after step 7 besides the trace post) | VDM | `0x410` goes `0 -> 0x40000` (base) one sample after `c68=0`, then to the terminate address within 2-7 µs; VDM `JONES` bit clears for 1.3-7.8 µs; S7 natural stall `0x410 = 0x4036c`, exactly the host's `R71 construct ... walk_end=36c cursor_expected=010004036c lists=1` | OBSERVED, both constructions |
| 9 | `0x80006874` | trace id 0 (ctrl0 bit 0) | ring 4 | drained | OBSERVED |

`0x410` has **no firmware writer**: a scan of all four images for stores at offset `+#1040` finds none (only (instruction omitted) = `0x408` at `0x80007a70` and (instruction omitted) = `0x400` at `0x8000912c`). It is zero before the kick (r79/r80 plateau and mid-upload fingerprints, r82 post-retire), so it is hardware-written progress.

## 2. The `0x400` vs `0xc68` "alias" is resolved: two different units, both accepted

Source: `build/gpu/r47-04-flight-empty-ta-20261025T085113Z-diagnostic_blob.txt` (`RENDER r39 flight-event`, 6c8=0 inline bell, 2.1 µs sample cadence, time = ns after the bell):

| ns | event |
|---:|---|
| 398 864 | `CLK_STATUS` PM and VDM request bits set (`0x100333`), `JONES = 0x3d7e` (BIF busy) |
| 405 292 | **`c68 = 1`**, `JONES = 0x3d3e`: **TILING (bit 6) busy** for the first time |
| 407 463 | `c68 = 0` (strobe consumed, about 2.2 µs), **`0x410 = 0x00040000`**, `JONES = 0x3d34`: **VDM (1), PM (3), TILING (6), BIF (0) all busy** |
| 409 508 | `0x410 = 0x00040288` (cursor at the terminate), `JONES = 0x3d37` (PM and TILING still busy, VDM idle) |
| 413 265 | `JONES = 0x3d7f`: **everything idle**, and it stays idle |

Over all 43 fast-sampler flights (r39..r47, every stream shape: empty, triangle, quad) the same order holds: TE busy starts first in 43/43 (VDM start 1.25-6.1 µs later, median 2.25 µs), the PM starts with the VDM (0-1.4 µs later), the TE busy span is 4.3-6.5 µs (median 5.4 µs), the PM busy span about 3.8 µs, and **TE and PM go idle at the same sample in 41/43**. 104 flights in total show TE+PM+VDM busy together (the later ones have coarser sampling). The TE/PM episode length does not scale with the stream content (TE busy median 5.3 µs with draws, 6.0 µs for empty streams), so I read it as a fixed arm / PM start-up handshake, not as processing of geometry (INFER). The VDM busy span does scale (median 1.3 µs for an empty stream, 6.4 µs with draws), so draws really do reach the VDM draw stage. **Sharpest form:** in 17 of the 27 draw-stream flights the VDM is still busy 2.5-3.9 µs *after* the TE and PM have gone idle (the other 10 end on the same sample), and in no flight does the TE light up again; for the 16 empty-stream flights the TE ends 1.2-4.1 µs after the VDM. The TE went quiet while the VDM was still consuming the draw, so nothing the VDM issued afterwards reached the TE, and the TE never reacted to the terminate either.

Conclusion on the alias: **`c68` is the TE arm (TE-side busy is its response); `0x400` is the VDM start (cursor and VDM busy are its response).** Neither is a duplicate of the other, neither was lost, and the order (`c68` first, `0x400` about 2 µs later) is the firmware's order. Earlier reports' "the real kick is `0x400`" and "`c68` is the kick" are both partly right and both irrelevant to the stall.

## 3. What the hardware does after the kick, and the three new readings of old data

1. **`JONES_IDLE` (`0x8328`) is the discriminator the TA reports left as a footnote.** `dsx-nx38` section 2 / row 13 already recorded "TE engaged-then-idle (not stuck)" from the kick blips; what is new here is applying it to the +100 ms natural stall and the post-retire bank, and using it to demote the "TE stuck waiting on PM" reading of nx24 (ii) and nx89 rank 1. Bit map (header lines 4834-4876): 0 BIF, 1 VDM, 2 CDM, 3 PM, 4 USCS, 5 IPP, 6 TILING, 7 SOCIF, 8 HOSTIF, 9 GARTEN, 10 TLA, 11 MMU, 12 FB_CDC, 13 FB_CDC_TLA, 14 TDM; steady state `0x3d7f` (bits 7, 9, 13, 14 always 0 on this core, 769 samples, PRIOR nx38 section 2). **Polarity: set = idle**, pinned by Apple's own readers: `waitForSLCAndBIFIdle` spins until bit 3 (PM) is *set* and `waitForMetaIdle` exits on (instruction omitted) (bit 9 set) (nx38 section 2, kext `0xfffffff006ca4f74` / `0xfffffff006ca4334`); a clear bit = busy. **S7 natural stall, +101.6 ms after the release was seen (`R80 bank-reg i=13`): `0x3d7f`**, i.e. VDM, PM, TILING, IPP, USCS, CDM all idle. **r82 post-retire bank: `0x3d7f`.** So after the first ~13 µs no VDM, PM, TILING, IPP, USCS or CDM bit is busy in the 20 ms flights (sporadic BIF blips from firmware memory traffic aside) and none is busy at +100 ms or after the retire: the hardware is **idle-and-waiting, not busy-and-stuck**. "TE started and is stuck on PM" is therefore not what the data shows (PRIOR nx89 rank 1 and nx24 reading (ii) assumed it could).
2. **The TA phase is open for the whole stall and closed only by finish24.** S7: `0x6020 = 0x02155184` = 34 951 556 cycles = 102.8 ms at 340 MHz, versus 101.6-104.1 ms between the kick and the bank read (kick is at most one 2.5 ms poll gap before the release was seen); r82 (0.59 s after the finish24 retire): `0x6020 = 0` while `c18/c28/0x430/0x8328` read live non-zero values in the same bank, so the register file is not gated and the zero is a real reset. So the counter starts at the kick and is reset by the retire (n = 1 each, INFER; nx38 called it free-running, which cannot be right for a value 4 orders of magnitude below 340 MHz x uptime). Consistent with `0x130 = 0` and `0xb20 = 0x0d`: the hardware itself does not consider the TA finished.
3. **The r82 region image is evidence about the TE, not about the stall.** `finish24` writes `c50 = 0x40000000` and polls its ack; the TE acknowledges and the constant empty 1280-byte region image appears (PRIOR nx10, `82-bypass-output-coherence.md` section 4). So the TE and its memory path answer a commanded flush normally; only the *natural* terminate-driven completion never occurs. (Whether the image bytes come from the TE or from firmware stays open, nx10 section 13; either way it is stream-independent.)

What the hardware definitely did, in one line: **VDM ran the whole stream (cursor at the terminate), the TE/PM completed a ~5 µs handshake, then everything idle with no output, no PM allocation, no event.**

## 4. Delta table: Linux vs Apple vs mainline/Mesa/DDK, start23-to-launch contract only

Apple column = the captured working iOS `W`/records (`ds-r36-a`: 295 of 344 `W` dwords byte-identical, all 49 differing dwords job/context dependent, "not one constant Apple sets and we set differently"; `ds-r35-a` for the `0x23` record; `dsx-nx24` 2.3 for the live c-block). Mesa/DDK column: Mesa `pvr_arch_job_render.c:719-788` (geometry KMD stream: `VDM_CTRL_STREAM_BASE`, `TPU_BORDER_COLOUR_TABLE_VDM`, `PPP_CTRL`, `TE_PSG`, `VDMCTRL_PDS_STATE0`, view index) and the DDK `RGXFWIF_TAREGISTERS` (`build/gpu/refs/mediatek/rgx_fwif_client.h:188-223`).

| field (reg) | Linux (device) | Apple | Mesa / DDK | delta? |
|---|---|---|---|---|
| stream base `0x408` | `0x1_00040000` | `0x1_00040000` (min) | `VDM_CTRL_STREAM_BASE` | none |
| stream end/len `0x470` | `0x370` (r80+ stream) | one past `STREAM_TERMINATE` of its stream | DDK `VDM_CTRL_STREAM_TERMINATE` | none (consistent with `0x410` landing at the terminate) |
| VDM progress `0x410/0x420` | hardware-written (see section 2) | same by design | n/a | none observable |
| `TE_PSG 0xc28` | `0x20000` (`completeonterminate`, `region_stride` 0) | `0x20000` kext constant | Mesa: `completeonterminate = geometry_terminate`, `region_stride = rgn_stride/unit` (non-zero) | **form differs from Mesa, equals Apple**; Apple's choice, not a Linux delta |
| `PPP_CTRL 0xc88` | `2` | `2` | Mesa: `wclampen=1, fixed_point_format=1` (`0x200` family) | equals Apple; the `0x202` variant was flown (r35) and stalled the same |
| `PPP_WCLAMP 0xc90` | `0x1e3ce508` x2 | same | DDK `PPP_WCLAMP` | none |
| `TE_PSGREGION_ADDR 0xc38`, `TE_TPC_ADDR 0xc40` | `0x1_01020000`, `0x1_01030000` | placement only | DDK `TE_PSGREGION_ADDR` | none |
| `PM_MTILE_ARRAY 0xc00` | `0` | `0` in every iOS job (`ds-r36-a`) | DDK `PM_MTILE_ARRAY` | none |
| TPU border/YUV/CEM regs | not in the start23 upload | not in Apple's upload | DDK `TAREGISTERS` has them | none Apple-vs-Linux (our shaders never sample) |
| per-core table `0x11030` x6 (`W+0xd0..0xf8`) | all 0 | **all 0 on iOS** (`ds-r36-a` section 7) | n/a | none. `dsx-nx89` 6.3 ("Apple's value is unobserved") is superseded by the captured iOS `W` |
| PM prepare `0x3d0/0x240/0x248/0x2d8` | `0x1_00000100`, `0x1_01000000`, `0x1_01010080`, `0x1_01000080` | relocation only, same formula, **`N` = 36 records on iOS vs 1** | n/a | record count only; no firmware instruction consumes `N` (PRIOR nx85); hardware consumption UNKNOWN |
| PM identity `rec+0x1c` | id 0 | context A id 0 (B id 2) | n/a | none for A |
| stream | stream 7 (`R71 construct case=2`: 11 blocks, **1 INDEX_LIST** `0x6f440900` count 4, `walk_end 0x36c`, publish `0x370`) | run18c clear-only: same PPP/PDS/VDM-state/INDEX_LIST/terminate shape; only `start_present` differed and its ablation (r71) stalled the same | n/a | none (r59, r65-r67, r71) |
| TA doorbell `R0+0xb00=0x10` | **never rung in the 6c8=1 construction** (33/33 receipts `cancelled`) | rung after every submit | mainline `wmb(); MTS_SCHEDULE; mb()` | **real, but it only governs dispatch (the 0.4-12 s plateau, r81), not what the hardware does after `0x400`** |
| PM client descriptors in `S` | `VCE0`, `VCE1` only; `E028/E048/E0B8/E0D8 = 0` | `VCE0 TE0 ALIST0 VCE1 TE1` always described | DDK HWRTData carries VCE/TE/ALIST cat bases | **the one persistent state delta**; it is a PM product (written by PM hardware or the install copier), not a host register (PRIOR nx83, nx84, nx89 6.2) |
| per-context cat table (object 0x89) | ctx 0, 7, 8 only; ctx 1-6 = 0 in 176/176 boots | **UNKNOWN** (never captured) | n/a | UNKNOWN; do not copy a slot without an Apple value |
| `init+0x6cc -> private+0x238` | 0 | boot-arg derived | n/a | **no reader**: two `SETD`, zero `GETD` of `private+0x238` in the 0x1000/0x8000 images (3D-template field, not the TA path) |

The reconciled statement is `working-driver-ta-stall-gap-audit-r2.md` section 0 plus two new facts: the hardware answers every start23 action, and the hardware is idle afterwards.

## 5. Ranking of the remaining causes (r82 plus the idle data)

Event-only explanations (TA_FINISHED raised but lost, ISR mask, wait handler) are **eliminated**: r82 removed the wait and still no output exists anywhere, the natural stalls had 12 s, `0x130 = 0` in the S7/r82 banks, `0x6020` shows the phase open, and the injected-event route (r68/r70) works. The plateau (0.4-12 s before `start23`) is a separate upstream matter owned by r81 and is out of scope here.

| rank | candidate | evidence for | evidence against | confidence (INFER) |
|---|---|---|---|---|
| 1 | **PM client / context service for the tiler never established** (TE0/ALIST0 descriptors, per-context cat bases 1-6) so the armed TE has nothing to serve | TE busy episode ends together with the PM episode and nothing follows; no PM pop (`pm-free` identical +1 ms to end, `phys changed=3 delta=70` always); `E028/E048` zero in 31 000 samples per word; PM progress counter 0 vs Apple 3..1568 (nx11/nx89); Apple always describes TE0/ALIST0 | it is a PM *product*: lanes may be zero only because the TE never asked (cause vs symptom not separable); lane/record seeding (r60-r62) was inert; the 3D-side ctx-4 catalogue copies (r52g-09, r53a) addressed the 3D fault chain, not the TA stall, so they are no evidence either way | 35% |
| 2 | **vertex collector (VCE/UVB) to PPP handoff or terminate never delivered** | VDM draw stage runs (busy span scales with draws, `0x410` at terminate); USC export moves `0x5118` (r58); but no PM-pool page beyond the 3 catalogue pages ever changes (so no vertex block reached the VCE0 pages the PM mapped), PPP/TE signatures 0 in 53 captures x every stage, bbox-enable probe inert (R55-03), TPC/region never written; TE episode independent of the stream | no positive control for the signature registers exists (section 7.6); r58's export proof is one build | 30% |
| 3 | hidden global/init state neither host nor firmware writes differently from Apple's *visible* inputs (pipe/cluster enables, UVS/TPU partitioning, firmware init tunables) | every host/firmware-authored input is at parity, so whatever differs must be outside them | pure exclusion argument; no candidate register named | 20% |
| 4 | reset/power runtime state | `SOFT_RESET = 0` 1105/1105 pre-kick; TE obeys `c50`; clocks up | SOFT_RESET only sampled pre-kick (nx38 residual 10a) | 5% |
| 5 | coherency of a PM/aux/RT page the hardware (not firmware) reads | PM-pool pages are `dmam_alloc_coherent`, `dcache_clean_poc` done | `dma-coherent=0` Normal-NC; hardware read-side unverified | 4% |
| 6 | kick/strobe not accepted, or alias | `c68` and `0x400` each demonstrably accepted (section 2); `cb8` and the three PM pokes only inferred | the three PM pokes and `cb8` acceptance are unproven (reads of 0 are uninformative) | 3% |
| 7 | event delivery only | see above | eliminated | 1% |
| - | `0x400` vs `0xc68` alias | resolved (section 2) | | 0% |

Ranks 1 and 2 overlap (the VCE also needs PM-served pages); I keep them separate because they predict different values for the signature registers and `0x420` in the extended bank (section 7.4).

## 6. Observed hardware action vs firmware-attempted (the exact split)

| class | items | basis |
|---|---|---|
| **hardware accepted the store** (landing readback) | `c88 c78 c80 c18 c28 c38 428 cc0 438/43c 470 408 240 248 2d8 3d0` | S7 bank at +102 ms |
| **hardware reacted to a strobe** | `c68` (TE busy, c68 pulse), `0x400` (cursor `0x410`, VDM busy/clock) | r39..r47 flights, S7 |
| strobe read of 0 = **uninformative** | `0x290 0x198 0x258 0xcb8` (self-clear; poll passes on 0), `0x400` itself (self-clears faster than a sample) | PRIOR contract 2.3 |
| PM accepted one client | `E008` becomes valid at +1 ms (PM hardware writes it) | nx83 |
| USC ran | `0x5118` moves with a one-byte change of the exported W | r58 (PRIOR) |
| **no acceptance ever observed** | PPP/TE data (`0x5020 0x5028 0x5110 0x5120` all 0, bbox untouched, TPC/region/PM-pool untouched), any PM allocation, `TA_FINISHED` | 53 captures x stages (nx89), S7, r82 |
| **firmware attempted only** (no post-kick hardware witness) | `0xc00 0xc08 0xc10 0xc20 0xcb0 0xd20 0xce0`, `0x418 0x440-0x460`, `0xf038-0xf070`, `0x11030` x6, `0xf000-0xf018` | not read after the kick, or equal to reset values |

The break lies between the last two rows of the first block and the "no acceptance" row. `JONES_IDLE` says the hardware went quiet at the break instead of hanging at it.

## 7. r83 design (build-ready brief; nothing implemented, nothing built)

### 7.1 Decision
r83 is **observation-only**. There is **no case A**: no one-line or one-value candidate survives the retained evidence (section 4 closes every host-authored field; section 5 ranks only structural causes). Firmware strobe receipts are **not** recommended: section 2 shows each strobe's hardware response already, start23 takes at most a few ms, and a cave in a poll or in start23 would perturb the instrument more than it informs (sites exist in `sonnet55-start23-byte-decode.md` section 10: caves B `0x800067bc`, C `0x800067c4`, region `0x800092d8..0x800093b7`, ids `0x381/0x382`; keep them as a fallback if r83 shows an unexpected timing).

### 7.2 Configuration (module parameters, entry on the existing r82 payload line)
`r80-spec.py STAGES` has no `marker=3, bank=1` row (stage 7 is `{ctrl0 0x9, marker 0, ladder 0, bank 1}`); `g5p_r80_cfg_valid(7, 0x9, 3, 0, 1)` accepts it (`r80-trace.h:72-81`: marker needs `ctrl0 & 8`; `ctrl0 0x9` has it), but the stage engine and the `test-r80-*` suite key off the table, so **`r83-spec.py` adds the stage row `{ctrl0 0x9, marker 3, ladder 0, bank 1}` and defines `BANK_REGS` as the 41-tuple**; `test-r80-source.py:152` (kernel table == `SPEC.BANK_REGS`) then enforces kernel/spec equality unchanged. Parameters: `ctrl0 0x9`, `boot_r80_marker=3`, `boot_r80_ladder=0`, `boot_r80_bank=1`, `boot_r82_bypass=0`, `boot_r82_endbank=0`, route `campaign-warm`, unpatched case-0 firmware, `wait_ms 12000`. Marker 3 plus ctrl0 `0x9` gives, in the same boot, id 0 (start23 returned) and M3 (absent expected), as proposed in `80b-marker2-marker3-gap.md` 9.1 test A, which was never flown. `g5p_r80_cfg_valid` accepts the combination (r80b report 0.4, test A). The bank is the existing IRQ-owned one: one read set at least 100 ms after `first_g728` (release), gate `R1+0x1000 & 0x1f == 1`, fallback consume + 11.5 s (precedent: `round80/runs/void-attempt-20261029T162531Z-stage07-1`, `bank done=1 mode=publish`). One boot; a second attempt only if the first never releases (`pub_ns` for the bank = 0, the r82 control and `161026Z-stage07-1` showed this happens).

### 7.3 Patch: widen the bank by 13 registers (all with retained read precedent)
Kernel patch `0141` on top of `a9/tri82` (`2494782cde`): edit only `boot-r80.inc` (a 2-hunk change) and the spec/test tables.
* `boot-r80.inc:25`: `#define G5P_R80_BANK_REGS 28` -> `41`.
* `boot-r80.inc:36-41` (`g5p_r80_bank_offsets[]`): keep the 28 existing entries in order, append
  `0x420, 0x3c8, 0x5020, 0x5028, 0x5110, 0x5118, 0x5120, 0xe008, 0xe028, 0xe048, 0xe098, 0xc30, 0xc34`.
* `scripts/gpu/r80-spec.py:210-212` `BANK_REGS` and a new `scripts/gpu/r83-spec.py` (extends `r80-spec`/`r82-spec`, `ROUND='round83'`, `ENTRY_PREFIX='tri83'`) with the same 41 entries; `analyze-r80.py:612-614` and `test-r80-source.py:152` already derive from `S.BANK_REGS` (no edit). `g5p_r82_endbank()` uses the same array (irrelevant: knob 0).
* Precedent for every new register (host reads on Linux, no incident): `0x420 0x3c8 0xe008 0xe028 0xe048 0xe098 0xc30 0xc34` in the r47-02 reads and 246/261/252/184 blobs; `0x5020..0x5120` the `group=sig` read in 168 blobs (`RENDER r39 regs ... group=sig`). **Excluded for no precedent:** `0x270` (PM progress counter; only the firmware save reads it), `0x3800` (SLC_CTRL_MISC, PSG hazard bit; never read on either OS). They may be added only if the orchestrator accepts an unprecedented read.
* The read is taken >= 100 ms after the hardware's ~13 µs activity, so it is not an active-window read.

### 7.4 Pre-registered branches (read at +100 ms, S7 construction)
Expected "same as always": `0x8328 = 0x3d7f`, `0x130 = 0`, `0xb20 = 0x0d`, `0x410 = 0x4036c`, `0x430 = 1`, `0x5020 0x5028 0x5110 0x5120 = 0`, `0x5118 != 0`, `E028 E048 = 0`, `E008 != 0`, `E098 = 0xc000`, `0xc30 = 0xc0000000`, `0xc34 = 0`, `0x420 = 1` (stream 7 has `lists=1`, `R71 construct`).

| observation | meaning | next |
|---|---|---|
| all as expected (most likely, about 70%) | localisation confirmed incl. `0x420` (draw reached the VDM) and `0x5118` (USC exported) in *this* construction; PPP/TE idle and never fed | Apple positive control (7.6); then rank-1 vs rank-2 work is blocked on Apple data |
| `0x420 = 0` | VDM reached the terminate without executing the INDEX_LIST (stream/LINK interpretation) | stream-shape RE, rank 2 weakens |
| any of `0x5020/0x5028/0x5110/0x5120 != 0` or `0xc34 != 0` | PPP/TE did receive data; stall is inside TE/PM | rank 1 up; flight with the signature channels (6c8=0) |
| `E028` or `E048 != 0` | PM did describe TE0/ALIST0 (contradicts 31 000 zero samples) | recheck bank timing |
| `0x8328 != 0x3d7f` (bit 6, 3 or 1 clear) | a block is busy at +100 ms: stuck-busy, the opposite of the flights | new TE/PM stuck-busy investigation |
| `0x5118 = 0` (all others as expected) | no vertex export latched in this construction, or the last-transaction register was cleared (nx86 / boundary map: it returned to 0 on a later stage in r52-04b) | compare r58's staged reads; does **not** by itself move rank 1 vs rank 2 |
| `0x130 bit 5` set | event raised but uncollected | r68-type route question |
| void: bank refused (`R1+0x1000 & 0x1f != 1`), `bank_done=0`, `lost>0`, drain gap > 20 ms, `0x301`-class marker absent in a stage that needs it | non-evidence for the bank only | repeat |

### 7.5 What r83a cannot tell
It does not separate rank 1 from rank 2 by itself: all-zero PPP/TE signatures are only meaningful if the same registers move on a working Apple job (7.6).

## 8. Contradictions with earlier reports (not smoothed over)

| earlier statement | here |
|---|---|
| `dsx-nx89` 6.3 / `ds-r28-c`: Apple's `W+0xd0..0xf8` unobserved, `0x11030` table "only unmodelled input" | `ds-r36-a` section 7 captured Apple's `W`: all six zero on iOS. Closed (my section 4) |
| `sonnet55-start23-hardware-contract.md` 2.1/2.3: "`0x400` vs `0xc68` alias uncertain" | resolved by the r47-04 flight (section 2): `c68` starts the TE-busy episode, `0x400` starts the VDM cursor |
| `dsx-nx38` finding 7: `PERF_TA_CYCLE` "free-runs, clock witness only" | S7 value equals 340 MHz x time-since-kick, r82 reads 0 after the retire: it is reset at the TA start and stopped by the retire (n = 1 each) |
| `dsx-nx24` 8 / `dsx-nx89` 6.1 rank 1: "TE received the terminate and stalled on PM-served state" | `JONES_IDLE = 0x3d7f` at +100 ms and the fixed 4.3-6.5 µs TE episode say the TE is idle, not stuck, and its episode does not track the stream; rank 1 is now "PM client never established", not "TE stuck waiting" |
| `82-bypass-output-coherence.md` section 0 last para: the bypass cannot separate delivery defect from truthful absence | the natural stalls (12 s) plus `JONES_IDLE`, `0x130`, `0x6020` and the PM-pool census do; event-only explanations are eliminated |
| contract 0.4/0.5: the doorbell is the "top difference" | true for dispatch only; it cannot change what happens after `0x400` (the 6c8=0 inline-bell flights stall identically) |

## 9. UNKNOWN / limits

* Every microsecond datum is 6c8=0 (inline bell, r39-r47 builds); for the 6c8=1 construction only the +100 ms bank and the host ring exist. I assume identical post-kick hardware behaviour because the stall end state is identical.
* The signature registers (`0x5020 0x5028 0x5110 0x5120`) have no positive control on this core (nx38 2.3). Their zeros are not proof of "never fed" until section 7.6.
* `cb8` and the PM pokes: acceptance unproven.
* Apple's per-context cat table and live PM catalogue bases are unmeasured.
* `JONES_IDLE` polarity (set = idle) rests on the kext's two wait loops (nx38 section 2) plus the steady `0x3d7f` and the `0x3d34` kick blips; there is no vendor prose for the register.
* n = 1 each for the `0x6020` readings.

## 10. Reproduce (read-only)

```text
# flight timeline (section 2): RENDER r39 flight-event / flight-bit lines
grep -E 'flight-event.*ch=(jones8328|vdm0410|te0c68)' build/gpu/r47-04-flight-empty-ta-20261025T085113Z-diagnostic_blob.txt
# 43 fast-sampler flights: first_ns/last_ns of jones8328 bits 1/3/6 over build/gpu/*diagnostic_blob.txt
# S7 natural stall bank and r82 end bank (section 3)
grep -h 'R80 bank-reg' build/gpu/round80/runs/void-attempt-20261029T162531Z-stage07-1/*diagnostic_blob.txt
grep -h 'R80 bank-reg' build/gpu/round82/raw/20261029T174557Z/stage02-attempt1/*diagnostic_blob.txt
# no firmware writer of 0x410
grep -nE '#(1040)\]' build/gpu/firmware-re/80000000.minim.dis    # no hit; 0x408 at 0x80007a70, 0x400 at 0x8000912c
# JONES_IDLE bits
sed -n 4829,4876p build/gpu/refs/linux/pvr_rogue_cr_defs.h
```
