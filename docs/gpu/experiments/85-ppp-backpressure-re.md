# 85 (RE): the r85 stage-2 park at the VDM-to-PPP boundary: what gates it, ranked, and the smallest post-r86 experiments

2026-10-30. Claude Sonnet 5.5, PPP-front-end gate RE lead. **Offline only: no iPad command, no build, no kernel/script edit, no commit.** Written here: this file. Ghidra (shared server): one EOL comment extended at `0xfffffff006c972d8` (section 7).
Labels: **OBSERVED** = a retained capture or a byte/instruction read this session (path given). **INFERRED** = arithmetic or decoding over OBSERVED data, derivation stated. **UNKNOWN** = neither. **PRIOR** = taken from an earlier report, not re-verified. Percentages are my judgement, not evidence.
Companions (not repeated): `r85-brief.md`, `85-build-report.md`, `84-upstream-primitive-admission-re.md` ("84u"), `dsx-nx36/37/38/96/97/98`, `dsx-agx-boundary-register-map-annotated.md` ("map"), `dsx-r74-pm-catalogue-mlist.md`, `dsx-nx25-lane-open-semantics.md`, `dsx-r71-kext-te-input-edge.md`.

---

## 0. Answer in plain language

1. **What r85 B-s2 is, by the brief's own rules.** Stage 2 (`N = 896`) is a clean **(1a) `ppp-input-not-draining`**, provisional twice: n = 1, and its campaign has no same-campaign control (section 2.3). The cursor (`0x410 = 0x40e2c`) sits 8 bytes into pair 142 (K_cursor = 142); the list counter `0x420 = 0x8e = 142` agrees exactly. The 143rd PPP-state block was consumed and the VDM stopped entering the 143rd count-0 `INDEX_LIST`. Not park-at-link (segment 0 ends at `0x1344`), not vdm-idle-midstream (`0x430 = 0x12` and JONES bit 1 clear).
2. **The park is the first host-visible A/B witness on the PPP side.** In r82c S3 / r83a / r84b S3 every PPP/TE register read zero or constant and the VDM always "completed". Now one register set (`0x410`, `0x420`, `0x5118`, `0x8328`) moves with a host-authored stream edit. It proves **finite buffering with zero drain between the VDM output and the first PPP/TE-originated effect** (zero drain observed from consume + 4.0 s to + 12.2 s; nothing earlier was read). It also reinterprets every earlier "VDM walked to the terminate" result: with at most 13 lists in the stream, the walk would finish even if nothing downstream ever consumed a token.
3. **It does not say which consumer is dead.** "PPP never starts" and "PPP buffers, the TE/PSG side never takes" both fill a FIFO. The three ranked causes below are two downstream consumers or gates that are not draining (C1, C2) and one fetch-side hold (C3); the park alone cannot separate them (section 3).
4. **Ranked (judgement):** C1 the PPP-to-TE/PSG stage is a closed door because the TE0/ALIST0 requester context is never opened (about 40 %). C2 a hidden global/boot state outside the launch contract, in the SLC/BIF-tiling/GARTEN words nobody has ever read (about 25 %). C3 a memory-side hold in the VDM's own BIF traffic, so the depth is fetch/response buffering and not PPP credit (about 20 %). Other 15 %.
5. **One-word/register initialization Apple performs that Linux omits: none survives.** The one open lead from the map (`meta+0x6cc`) is closed today: Apple's value is 0 on this iPad (same as Linux), and the field has no literal reader in the firmware (section 5). The remaining Apple-vs-Linux deltas (TE0/ALIST0 lane records, populated PPP context page) are **hardware-written state**, not host-authored words (PRIOR, nx25 section 0.3; r60/r61/r62 host seeding did not install).
6. **No r86 document exists** (`grep -ril r86 docs scripts .planning` finds nothing). I assume r86 is the brief section 7 first item (shift the segment bases to separate count from address, plus the fresh-epoch K reproduction). Section 6 orders the follow-ups on top of that; each is "one Apple-only state or one read on the N = 896 construction, read K".

---

## 1. Artifacts read and search boundaries

- r85 raw: `build/gpu/round85/raw/20261029T230658Z/stage02-attempt1/header.json` (B-s2, the park), `build/gpu/round85/raw/20261029T223352Z/stage0{1,2,3}-attempt1/` (A-s1 `N=0`, A-s3 `N=12`, A-s2 void), `campaign-start/end.json`, `stages.jsonl`. Python over `header.json` `r85.bank_regs` (3 slots x 41 registers) for every table below.
- Docs: the list in the header, plus `docs/gpu/experiments/dsx-r74-linux-reset-gap.md`, `dsx-r74-apple-ta-reset.md`, `dsx-r71-init6c0-runtime.md`, `dsx-nx5-pm-bind.md`.
- Code: kernelcache in the shared Ghidra server (`AGXMetaFirmware_initializeSharedRootsAndControl`, `0xfffffff006c96be8`); flat disassembly `build/gpu/agx.dis` for the `0x7b3f402` recompute (Ghidra has no function at `0x6c93a9c`); firmware listings `build/gpu/firmware-re/{10000000,80000000,20000000,c0000000}.minim.dis` (literal-offset greps); live ADT dump the private live ADT dump (not published); pinned headers `build/gpu/ds/pvr_rogue_cr_defs.h`.
- **Search boundaries.** Firmware reader searches are literal-offset (`[reg+#568]`, absolute `0xa238`); a computed-address reader is not excluded. The kext register-write census is nx7's immediate/write-primitive scan (PRIOR). No iOS MMIO value exists (run16 is memory-only), so every "Apple value" for a register is a kext/firmware constant, never a sample. I did not decode the `a764/a744/a834` post-`c50` helpers, `vtable+0x768()` (still UNKNOWN), or any hardware internals beyond what headers and captures show. Not run: anything on the device.

---

## 2. OBSERVED

### 2.1 r85 bank, N = 0 / 12 / 896 (all three slots identical per case except the free-running counters)

Source: `header.json` `r85.bank_regs` of A-s1, A-s3, B-s2. Only registers that differ or matter are listed; all other 28 bank registers are equal in the three cases (`0x130 = 0`, `0xb20 = 0xd`, `0x428 = 0x86240`, `0x438 = 0x24001002`, `0x470 = 0x370`, `0xc18/c28/c38/c78/c80/c88/c90/cc0`, `0x240/248/2d8`, `0x3d0`, `0x414 = 1`, `0x5020/5028/5110/5120/5030 = 0`, `0xe028/e048 = 0`, `0xc30 = 0xc0000000`, `0xc34 = 0`).

| register | A-s1 `N=0` | A-s3 `N=12` | B-s2 `N=896` |
|---|---|---|---|
| `0x410` (VDM cursor, low word) | `0x4036c` | `0x4036c` | **`0x40e2c`** |
| `0x420` (INDEX_LISTs consumed) | 1 | 13 | **142 (`0x8e`)** |
| `0x430` (`VDM_CONTEXT_STORE_STATUS`) | `0x01` | `0x01` | **`0x12`** |
| `0x8328` (`JONES_IDLE`) | `0x3d7f` | `0x3d7f` | **`0x3d7c`** |
| `0x5118` (`USC_UVB_CHECKSUM`, last-transaction) | `0x0800033c` | `0x0800033c` | **0** |
| `0xe008` (VCE0 lane) | valid | valid | valid (`0x1cbd7001`) |
| read times after consume (slot 0 / 1 / end) | 3.63 s / 4.64 s / 13.22 s | 3.49 s / 4.50 s / 13.25 s | **4.02 s / 5.03 s / 12.23 s** |
| `R74H` objects at end (`rt0`, `region-image`, `tpc`, `aux0`; `pm-control` `nz=18 delta=2`) | `nz=0` (pm-control as right) | same | `nz=0`, `pm-control` identical (no memory effect of the flood) |

B-s2 values are identical at slot 0 (+100 ms after `first_g728`), slot 1 (+1 s) and the end bank. The `R82C fault` bank is clean (`e150 = e154 = e158 = e15c = 0`, B-s2 blob), so the TPC-leaf-absent canary is silent. `refused: true` appears in all three headers (the 3D side is never submitted); it is not specific to the flood.

### 2.2 Decode (INFERRED, arithmetic only)

`(0xe2c - 0x544) = 0x8e8 = 2280 = 142 x 16 + 8`. Pair 142, dword 2 (the `INDEX_LIST` dword `68040600`): pairs 0..141 are complete (142 lists, matches `0x420`), the pair-142 PPP-state block (`00000201`, `0x0008c5f0`) is consumed, the list is not. Totals at the park: 587 stream dwords from the entry `0x500`; 147 PPP-state blocks (4 in the preamble + 143); 142 lists; 1 PDS + 2 VDM-state (preamble); 1,176 payload bytes of PPP state if each state is fetched at decode. `JONES_IDLE = 0x3d7c`: bit 0 (BIF) and bit 1 (VDM) busy; bit 2 CDM, bit 3 PM, bit 4 USCS, bit 5 IPP, bit 6 TILING idle (decode: `dsx-nx38` section 2). `0x430 = 0x12` is `COMPLETE = 0, NEED_RESUME = 1, LAST_PIPE = 1`: the same value the control shows during its 4.4 us walk (r71-02, `r76-ppp-token-flood-brief.md` section 6); here it is simply held because the VDM never reaches the terminate. Report, not interpreted further.

### 2.3 Verdict, provenance, and the honest caveats

- **Clean (1a).** Cursor not at the walk end; `0x410/0x414/0x420` identical on both plateau reads; cursor maps into a pair region; `K_list = 142 > 13`; `0x5118 = 0`; busy signal present; no fault (`R82C fault` bank clean, canary silent, `e150..e15c = 0`); `short-walks` on the same entry (A-s3). The quad (`0x5118`) is past the last LINK and was never reached, as expected.
- **Provisional twice.** (a) n = 1; the brief requires a fresh-epoch reproduction within +-4. (b) Pairing: the brief's void list includes "paired control missing". B was a one-stage campaign (`planned_stages: [2]`, new source boot `ca813b77`, 23:07); its control and calibrator (A-s1, A-s3) are the same entry and payload (`tri85-30f63ab243`, sha `c2a959ae...`) from a different campaign (22:34 / 22:36, source boots `5acd2216`, `9ad1e61f`). Same payload, different epoch: I treat that as partial pairing and flag it for the owner.
- **A-s2 is `void-infrastructure`, not a freeze caused by the flood.** `20261029T223352Z/stage02-attempt1` stopped at `R74 milestone seq=6 step=attach-reactivated ret=-110` (`attach-reactivation-failed`, 66.47 s, before publication); the campaign ended `unreachable`. The hardware never saw the flood in that boot.
- **First read is consume + 4.0 s, not + 100 ms.** Slot 0 is armed 100 ms after the release `first_g728_ns`, which is 3.9 s after `consume_ns` in B-s2. The control walks 11 blocks in about 4.4 us, so an unimpeded `N = 896` walk would end in under 1 ms. Zero drain is observed from 4.0 s to 12.2 s; whether the VDM crept for the first 4 s is UNKNOWN.
- **Unit of the depth is not decided.** 142 lists, 147 states, 289 blocks, 578 PPP-side dwords, 587 stream dwords and 1,176 payload bytes are all candidates. I do not convert it to a FIFO size; section 6 gives the separating experiment.

---

## 3. What the park proves and does not prove (INFERRED)

| claim | verdict |
|---|---|
| Count-0 lists are not dropped at the VDM boundary | **Yes, for count-0 lists.** They are held until a depth then back-pressure; this retires the drop-without-draw false negative of brief section 8.1 for this token class. |
| The VDM-to-PPP "infinite sink" form of U1 | **Dead** (as the brief predicted for (1a)). |
| The sink is the TE | **Not shown.** TILING (bit 6) and PM (bit 3) are idle for 8 s while the VDM is stuck, so nobody downstream has work in flight. A TE stuck on the PM would be expected to look busy (INFERRED, not calibrated), which points at a closed input (PPP front-end or the stage in front of the TE), but the JONES TILING bit has no calibrated "busy while waiting" case. |
| The PPP has a clock/power/reset gate | **No such gate exists in the register map** (nx38 sections 0.1-0.3, PRIOR; `CLK_CTRL` 26 fields, `SOFT_RESET` 59 bits, none names the PPP; `0xc88` retains). The park does not reopen this; it only says that if the PPP is gated, the gate is not a documented bit. |
| Earlier "VDM completed" results | **Non-informative about drain.** With at most 13 lists / about 23-44 blocks the stream fits in the elastic region. Every claim of the form "tokens were delivered to the PPP" in nx96 section 2.3 / nx97 section 2.3 is a fetch-side statement. |
| Back-pressure is positive evidence of a dead sink, not of a slow one | Zero movement over 8 s. A slow sink at below one token per 8 s is possible but not distinguishable. |

The BIF busy bit (JONES bit 0) is the only asymmetry besides the VDM bit. It is consistent with (a) a response buffer that cannot be delivered because the consumer is full (a consequence of C1/C2), and (b) a genuinely outstanding VDM read (C3). It is not evidence for either alone.

---

## 4. Ranked causes (at most three)

For each: mechanism, OBSERVED/PRIOR for and against, exact writers/readers, boot/submit ordering, and the smallest post-r86 experiment. "Apple-only state" means state Apple has and Linux lacks, per the retired-axes table of 84u section 7.

### C1 (about 40 %): the stage in front of the TE (PPP-to-TE/PSG) never opens because the TE0 / ALIST0 requester context is never bound by the PM

*Mechanism (INFERRED).* The TE accepts PPP output only once the PM has bound its parameter-memory requester contexts: PM context ids TE0 = 1 and ALIST0 = 3 (`CONTEXT_MAPPING2 = 0xf088 = 0x030102`, firmware boot constant, `0x100187a0`-`10018828`); on Apple the lane records for TE0 and ALIST0 are `ADDR|VALID` in 21/21 captured jobs (`S+0x30`, `S+0x90`, nx25 / r74-ml section 0.5), on Linux in 0 of 115,037 samples; Linux binds VCE0 only (`E008`, 45,377/48,957). With the door shut, whatever sits between the VDM output and that stage (VDM output FIFO, PPP input queue) fills to K and stays.

*For.* (OBSERVED, B-s2) TILING, PM and IPP idle with the VDM stuck: a closed input rather than a busy consumer. (OBSERVED) `0xe028 = 0xe048 = 0` and every PPP/TE signature zero in this boot too; `0x130 = 0`, so no `PM_OUT_OF_MEMORY` (bit 7) event: the PM never refused anything. (PRIOR) the TE arm `cb8`/`c68` is answered and TE/PM go idle together about 5 us later in 41/43 flights, "TE asked and the PM stopped" (84u 6 U3, weak); in bypass the TE writes the same empty region image for an empty and a quad stream (r84b N2): the quad primitive never changed TE output even when the TE was commanded to flush.

*Against.* (PRIOR) The TE writes region headers with `e028 = 0` (r49-05a, r30-05): the lanes are a demand fingerprint, not a gate for command-driven work (nx25 0.4; r74-ml D1-D4 favour "the TE never asked"). So C1 only survives as "a precondition for accepting *in-band* tokens", which nothing shows directly (84u U3 Against). No requester-6 (PM) fault has ever been decoded. No host-authorable writer: the lanes are hardware-written (nx25 0.3; nx5 0.3), host seeding did not install (r60/r61/r62), a host write to `0x1270` is not retained (`r53a-06`).

*Writers/readers (PRIOR, exact).* Lanes `0xe008 + 0x48*DM + 0x90*pipe + 0x20*req`; written by the PM hardware (or by the firmware copier `10018e5c` after `[G+0x72c] == 3`, never observed to run: `0x2b8 = 0` in 79,122 samples). Read only by the harvester `1001886c` on completion/stop paths. Nothing in the kext references `0xe0xx` except four MMU registers. After `0x400 = 1` (`0x8000912c`) the firmware executes no PPP/TE/PM access (84u 3.1).

*Smallest post-r86 experiment.* **No host-authorable Apple-only word exists for C1, so the smallest experiment is an observation on the same N = 896 construction, not a fix:**
- Plain reads at the existing three slots (no new MMIO class; flag exists, `render_r46_observe` bit 0, patch 0068): the lane companions `0xe010 0xe014 0xe030 0xe034 0xe0a0 0xe0a4 0xe0c0 0xe0c4` (map 8.1 O2). "Described but empty" versus "absent" splits whether the PM ever got a TE request.
- Fenced (owner decision; one write, restored): the never-taken clock-forced read of `BIF_PM_CAT_BASE_TE0 = 0x1250`, `ALIST0 = 0x1260`, `TE1 = 0x1270`, with `BIF_CAT_BASE` ctx-8/7/0 as positive controls (r71-ke section 0.3; map 7). Caution: r74-ml 7.3 says the public block reads 0 even when `E008` is valid. A zero with valid positive controls is therefore consistent with C1 but cannot prove it; a **non-zero TE0 base kills the lane half of C1**.
- Predictions: lane companions non-zero while `e028 = 0` -> the PM described TE0 (then C1 becomes "TE asked, PM refused to bind"); all zero -> unchanged.
- A fix-shaped alternative exists only as a prior licence: r74-ml section 10 (`S+0x70 = S+0x78 = 0xc000` on the r74 construction, watch `E0B8`). It needs copier dispatch, which has never been observed, and the park cannot affect that. I do not re-rank it.
- **Not recommended:** a commanded `c50` or any forced `finish24` poke at the park. It would answer "does a TE flush release the VDM", but it is the retired forced-finish class (brief section 7) and breaks the read-only rule.

### C2 (about 25 %): hidden global/boot state outside the launch contract, in the unread SLC / BIF-tiling / GARTEN words

*Mechanism (INFERRED).* The PSG/TE path writes through the SLC and BIF tiling apertures. A global hold or an unprogrammed aperture there would let the PPP take a few tokens and then stall, while the commanded `c50` path (which only needs one write) still works. The candidates are exactly the words nobody has read on any boot of either OS:

| word | what it is | written by | Apple vs Linux | read ever? |
|---|---|---|---|---|
| `0x3800` `SLC_CTRL_MISC` | bit 1 `ENABLE_PSG_HAZARD_CHECK`, bit 8 `MISC_PAUSE`, bit 3 `RESP_PRIORITY`, bit 0 `BYPASS_BURST_COMBINER` | nobody found | UNKNOWN | **no** (nx38 5.3) |
| `0x12d8 .. 0x1310` `BIF_TILING_CFG0..7` | 8 tiling apertures | boot list (`0x12E0 0x12F0 0x1300 0x1310` are in the 49-word boot set, nx37 7.3) | UNKNOWN | **no** (just past the fleet's read window, nx38 5.4) |
| `0xbb8` `GARTEN_SLC`, `R1+0x10` | boot value; kext write set includes `0xbb8` | kext + our boot stream (same order/value, nx7) | equal as written, **never read back** | no (84u 6 U2) |
| `0x11f00 .. 0x13070` GARTEN window | boot words `0x11F00 0x11F40 0x12000 0x12008 0x13000 0x13070` | firmware boot init | UNKNOWN | 25 of 49 boot words never read (nx37 7.3) |
| `e240`, `e250` SLC3 base | one init-record-gated store; skipped on Linux | firmware `10019b70` | **structural** (no SLC3 region registered), not host-reachable (r71-ke 0.5) | no |

*For.* Satisfies "everything authorable is identical, so the remainder is un-authored state" (84u U2 For). The busy BIF bit at the park fits a fabric-side gate.
*Against.* PRIOR: the kext writes nine RGX registers, all in our stream with the same values (nx7, nx37 section 3); `SLC_CTRL_BYPASS` bit 32 `REQ_TA_PPP` reads 0 in 733 samples, i.e. matched to Apple's `0x3828 = 0` (nx38 5.2); TE, PSG, region/TPC page tables and the BIF requester work under command (84u 3.3). Prior per word is small.

*Smallest post-r86 experiment.* **Read-only, one boot, same construction:** add `0x3800`, `0x12d8 .. 0x1310`, `0xbb8`, `R1+0x10` to the existing bank (the brief's rider flag `boot_r85_riders` already covers `0xbb8` and `R1+0x10` as plain reads; `0x3800` and the tiling apertures are new and SLC-side, so they need the same fenced clock-force window as C1; combine the two fenced reads in one step). Predictions: `0x3800` bit 8 set, or a tiling aperture reading 0 while its boot write was non-zero, is a one-word candidate with a directly testable "write Apple's value" follow-up; all matching the written values retires the bucket. No write to `R1+0x1000` (never-write list).

### C3 (about 20 %): memory-side hold in the VDM's own BIF traffic, so the measured depth is fetch/response buffering and not PPP credit

*Mechanism (INFERRED).* The VDM fetches the stream and each PPP state payload (`VDMM` requester; r39-04/05 fault reads) through the BIF. If a VDM read never returns, the cursor stops where the fetch pipeline runs dry and BIF stays busy, with no fault because the transaction is pending, not failed. The depth would then follow address/line geometry (stream bytes `0x92c`, PPP BO copy `+0x5f0`, 16 bytes short of `+0x600`), not a token count.
*For.* BIF (bit 0) is the only block besides the VDM that is not idle; no fault anywhere; the park is exactly where a response-buffer/outstanding-read limit would show.
*Against.* The first 142 fetches from the same two pages worked; the cursor is not at a cache-line boundary (`0xe2c` is dword 3 of the `0xe20` 16-byte group; an unreturned line fetch would stop at a line start) and fetch and execution agree to the dword (`0x410` and `0x420` both say 142), which is what output-side resistance looks like, not a fetch stall (INFERRED). Prior flights also show `BIF_JONES_OUTSTANDING_READ` non-zero in some boots (below), so a busy BIF is not abnormal by itself.

*Smallest post-r86 experiment.* **Plain reads only:** `BIF_JONES_OUTSTANDING_READ 0xf098`, `BLACKPEARL 0xf0a0`, `DUST 0xf0a8` at the three slots (flown precedent: patch 0064 `g5p_r39_ios[] = { 0xe228, 0xf098, 0xf0a0, 0xf0a8 }`, flag `render_r39_observe` bit 2; earlier blobs read `f098 = 0 / 1 / 2 / 4` in 1,091 / 188 / 77 / 8 samples). Predictions: `0xf098 = 0` stable -> the BIF-busy bit is not a counted outstanding read (C3 falls, C1/C2 rise); `0xf098 > 0` stable across the three slots -> a stuck VDM read is counted (C3 rises); then the shift-bases data below decides address versus count. This is the cheapest of the three and can share a boot with the r86 bases shift.

---

## 5. One-word/register initialization candidates Apple performs that Linux omits: audit

**Result: none survives.** Closest, and why each is not it:

| candidate | Apple | Linux | verdict |
|---|---|---|---|
| **`meta+0x6cc`** (kext `6c972d8`, (instruction omitted), `w9 = (accel+0x402 >> 4) & 1`, gives firmware `private+0x238` via the copy at `0x1000116c` / `0x10003d18`) | **0 on this iPad** (below) | 0 | **Closed today.** The bit is `(model-slow == 1)`; the property is absent from the live ADT, so Apple writes 0 as well. No literal firmware reader of `private+0x238` exists (only the two (instruction omitted) copies). Computed-address readers are not excluded [UNKNOWN]. |
| `meta+0x6c0` (`(accel+0x402 >> 1) & 1`) | 1 (`no-gpc` absent; r71-init6c0 0.2) | 1 (patch 0006) | equal; consumers are the firmware register-access layer, none on VDM/PPP/TE/PSG/ISP (r71-init6c0 0.4). |
| `meta+0x6c8` = `vtable+0x768()` | UNKNOWN (slot unresolved) | not transcribed | open; gates the policy/readiness path and the PIO table, not a TA path (r71-ke 0.7); not a PPP candidate. |
| `e240` SLC3 base | programmed if the init record carries it | skipped | structural, not host-reachable (r71-ke 0.5). |
| `0xe248 = 0x1ffe` | kext in `waitForSLCAndBIFIdle` | not written | excluded causally (three region-header boots never wrote it; nx7 5.1). |
| `0xc78/0xc80 = 0x88` (an apparent coincidence with a depth near 136) | sample-grid nibbles `(x=8,y=8)` (nx36 section 3.1) | equal | not a credit/limit; retired. |
| TE0/ALIST0 lane records, populated `cc0` page | present | absent | hardware-written, not host-authored (nx25 0.3; nx98 section 2 cites `TA_CONTEXT_STATE_BASE` as the PPP store sink, so its content is a consequence, F5). |

**How `meta+0x6cc` was closed.** Ghidra disassembly of `AGXMetaFirmware_initializeSharedRootsAndControl` shows `x20+0x402` read as a byte; bit 1 goes to `meta+0x6c0`, bit 4 to `meta+0x6cc`. The byte is the global `0x7b3f402`. Its full recompute is in the unnamed function at `0x6c93a9c` (flat disassembly `build/gpu/agx.dis`, lines around `fffffff006c93dbc` to `fffffff006c93e4c`): (instruction omitted) with `w10 = (byte[0x7b3f3fa] == 1)`, and `0x7b3f3fa` is written at `6c93c50` from the `model-slow` OSNumber (`1` = present and non-zero, `0` = present and zero, `2` = absent; r71-init6c0 section 1.2). `grep -i 'model-slow\|no-gpc\|has-kf' the private live ADT dump (not published) returns nothing, so the byte is 2 and bit 4 is 0.

**Honest limit of this section.** It says the *host-authored word space* is exhausted to the depth of nx7/nx37 plus today's check. It does not say Apple does nothing the park cares about: the open items are state the hardware writes (C1), words nobody has read (C2) and the BIF counters (C3).

---

## 6. What to fly after r86, in order (each one factor or one read on the N = 896 construction)

Assumed r86 (not found on disk): brief section 7 item 1, "shift segment bases (separate FIFO depth from position)", with the fresh-epoch reproduction of K (+-4). What it separates:

| r86 reading | meaning |
|---|---|
| `K_list` stays 142 when the preamble/segments shift by +-16/32/64 bytes | a count limit (a credit or entry FIFO): C1 or C2 |
| the cursor *address* (`0x40e2c`) or the stream byte count (`0x92c` from the entry) stays fixed | a stream-side byte or line limit: C3 |
| K follows the PPP BO copy address (`+0x5f0`) | the state-fetch line: C3 (and a PPP BO geometry question) |
| K moves with neither | the limit is in the PPP-facing token stream shape; do the split below |

Then, cheapest first, none of them forced-finish24:

1. **Reads on the r86 boot (no extra boot):** `0xf098/0xf0a0/0xf0a8` (C3) and the lane companions (C1). Both are plain reads with flown precedent.
2. **Token-class split (one stream edit, not an Apple-only word):** two floods of the same `N` in stream bytes, state-only (PPP-state blocks, no lists) and list-only (count-0 lists, no state). If lists park at `K_list` and states never park (or park at a different count), the dead sink is the draw/primitive path (VCE/PPP); if the states park, it is the state path. This localizes the consumer without any hardware write and is the strongest separator of "PPP front-end" from "after the PPP".
3. **One fenced read-only window (owner decision):** clock-forced `0x1250/0x1260/0x1270` with `BIF_CAT_BASE` ctx-8/7/0 positive controls, plus `0x3800` and `BIF_TILING_CFG0..7` (C1 and C2 share it).
4. Only if (3) finds a non-zero or mismatching word: the matching "write Apple's value" follow-up for exactly that word, flown on the N = 896 construction so the park is the witness and no completion is injected.

Pre-registered reading of the park as a witness for later fixes: any Apple-only change that moves `K_list` or releases the park (cursor reaches `0x4036c`, `0x420 = 897`, `0x5118 = 0x0800033c`) is the first PPP-side positive since the project began; a change that leaves `K_list`, `0x410`, `0x8328` untouched is a clean negative on that axis for the first time.

---

## 7. UNKNOWN, and Ghidra annotation

UNKNOWN: which consumer is dead (C1/C2/C3 not separated); the unit of the depth; whether the VDM crept during the first 4 s; whether `0x430 = 0x12` held has any meaning beyond "the terminate was not reached"; whether `private+0x238` has a computed-address reader; `vtable+0x768()`; whether a stuck BIF read exists (needs `0xf098`).

Ghidra (shared project): extended the existing EOL comment at `0xfffffff006c972d8` with the closure above (existing comment preserved, resolution appended). No renames; the existing names (`AGXMetaFirmware_initializeSharedRootsAndControl`) were reused. `scripts/ghidra-mcp.sh save` reported `SAVED ok` after the first attempt was deferred (server busy).

## 8. Reproduce (read-only)

*(Listing omitted under the no-Apple-code rule; the surrounding text describes the behaviour.)*
