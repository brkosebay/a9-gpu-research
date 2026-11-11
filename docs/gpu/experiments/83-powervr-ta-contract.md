# r83: PowerVR/Rogue working-driver TA contract vs Linux start23, the hand-off configuration inventory, and the falsifiable test

2026-10-29. Claude Sonnet 5.5 research sub-agent. **Offline, read-only**: no device, no build, no kernel/script/patch edit, no Ghidra write, no commit. One file written: this one. Revised three times after integrating `83-ta-launch-root-cause.md` (RC), `83-apple-ta-launch-exact.md` (AP, incl. its §12), and the owner's priority note (**TA/tiler failure only; no doorbell, generic tracing, compute or broad PM census; compute liveness optional**).

Labels: **SRC** = a line in a vendor, mainline or Mesa source (`file:line`); **OBSERVED** = a retained capture (**ME** = I re-parsed it this session, §9); **STATIC** = decoded firmware; **PRIOR** = cited from an earlier report, not re-verified; **INFER** = my reading; **UNKNOWN**.

| tag | path |
|---|---|
| MESA | `third_party/mesa-g5p/src/imagination/{vulkan/pvr_arch_job_render.c, vulkan/pvr_free_list.c, include/hwdef/rogue_hw_{defs,utils}.h, csbgen/rogue/{cr,vdm,ppp}.xml}` |
| DDK | `build/gpu/refs/mediatek/{rgx_fwif_client.h, rgx_fwif_shared.h, rgxfwutils.c, rgxstartstop.c}` (Rogue DDK, Series6XT tree) |
| MAIN | `build/gpu/refs/linux/{pvr_rogue_fwif.h, pvr_mmu.c, pvr_fw.c, pvr_rogue_cr_defs.h}` |
| HDR | `build/gpu/firmware-re/round10-rgx_cr_defs_km.h` (DDK `rgx_cr_defs_km.h`, 270 addresses) |

---

## 0. Owner summary

1. **No host- or firmware-authored hand-off configuration delta is left.** Every value that configures USC -> UVB -> VCE -> PPP -> TE -> PSG/PM is either byte-identical to Apple's or derived by Mesa's formulas to the same number (§2.2, §4). Run18 field-level diff (Apple stress job vs Linux, `build/gpu/run18-linux-diff-dryrun/run18-linux-diff.txt`): PPP state blocks `ppp_00..04`, PDS code, PDS data and the USC window are **byte-identical**; the stream differs only in group count and `INDEX_LIST` presence bits (`start_present`, flown in r71, same stall). AP: W/record/PM-state words match beyond pointers/context/bookkeeping; Apple's kext authors no per-requester PM lane. So **there is no "exact handoff configuration" to correct**; the stall is a hardware-side or global-state condition.
2. **What the hardware does** (RC + AP + my re-parse): `c68` lights the TE and `0x400` starts the VDM (both accepted; kick is not a candidate, not retested); USC exports exactly the expected vertex data (`0x5118` = host-expected value in 423 of 584 non-zero lines); then **nothing downstream of the UVB latches**: `0x5030` VCE_CHECKSUM, `0x5020/28`, `0x5110/20` are 0 in 1466 reads (but see the liveness caveat), the TE/PM episode lasts ~4-6 µs regardless of stream, in 21 of 29 draw flights the VDM keeps issuing after the TE went idle and the TE never lights again, no PM data page is popped, no TPC/region coverage, no event, `JONES_IDLE = 0x3d7f` (all idle) at +102 ms with `0x6020` showing the TA phase open. The machine is **idle and waiting for input that never arrives**, not busy and stuck.
3. **Ranking (adopting AP's numbers; my own re-derivation agrees after two withdrawals):** **H2 delivery of state/terminate to the TE broken in hardware (about 65 %)**, **H3 hidden global state (about 20 %, the bucket's total, not the governor's own probability)**, **H1 missing PM client setup (about 10 %, a symptom, not authorable)**, other (about 5 %). **Common-mode constraint:** empty streams stall identically and carry no vertex data, so whatever suppresses `TA_FINISHED` sits on the **control path into the TE (VDM -> PPP state/terminate -> TE)**; a UVB -> VCE defect is either downstream of the same cause or a second, separate defect. Withdrawn from my previous version: the "TE start-of-job write" separator (B1; AP §12.1 withdrew the start-of-job reading: Apple's image was read 77 ms after the job) and the H1g/descriptor test (Apple's kext writes no per-requester state; nothing to author).
4. **The falsifiable one-boot test** (§7 T1): on the proven r80 stage-7 construction, **flip the one never-flown Apple-vs-Linux global input that sits on the power/clock side, the governor ceiling** (`policy+0x688 = 400` as recovered from Apple's record, `dsx-r74-power-handshake.md` §0.4, and `ctrl+0x1028/102c/1030 = 3348/400/400`, the existing `dc_variant 9` constants, `sonnet55-apple-ctrl0-policy-audit.md` §7.1; the r73b cases that define the TA epoch reject any `dc_variant != 7` (`boot-r73b.inc:938`, `-EINVAL`), i.e. a zero ceiling), with RAM witnesses `policy+8/+0x38` and the **priority-ordered bank `0x5118, 0x5030, 0x5060, 0x420, E008/E028/E048, 0x8328`**. Falsified if the governor state moves (`policy+8` 2 -> 1) and every TA observable stays byte-identical to the retained S7/r82 baselines. It is the only never-run one-word candidate in the hidden-state bucket; its prior is low (§6). **Risk, stated: enabling the governor path executes `fw_setGPCPerformanceState` for the first time on Linux, whose only non-wrapper write is `unit 6 +0x2c = 0x6040/0x1804` through an aperture entry Linux leaves zero; `dsx-r74b-mmio-read-safety.md:202,540` keeps that zero-aperture write as a fabric-wedge residual that "cannot be excluded". T1 therefore supplies the unit-6 descriptor (`PA 0x2_0080_0000, len 0x1000`, `dsx-r75-apple-pio8-table.md` §0.2) as a safety co-factor, and the session may still be lost; the owner's reboot recovery applies.**
5. **The H2 localiser is Apple data, not a Linux knob** (§7 T2): read `0x5118` (known to move), then `0x5030`, `0x5060`, `0x5020`, `0x5028`, `0x5110`, `0x5120`, `0x420` on a working clear-only job; the first zero after a non-zero names the stage where Linux's chain must end. Include `0x5030/0x5060`, drop nothing else (AP §12.4).
6. **TA output write behavior** (the only untested attribute): PM-accessed memory PTEs. Mesa, mainline and the DDK flag every PM buffer `PM_FW_PROTECT`; Apple's PM-aux pages are `PA|0x4000000000000001` (no CC, no SLC-bypass), Linux maps `PA|0xd` and never sets bit 62 (grep-verified). One-line test T3, ~5 %.
7. **Out of scope per owner**: doorbell (`p1` governs upstream dispatch only), generic tracing, compute (the Linux compute-job signature-liveness control is optional, listed in §7 T4, not scheduled), broad PM census.

---

## 1. Sources and limits

MESA gives the host obligations and every sizing formula; MAIN the fwif structs, kick, PTE bits; DDK the names and order of the registers the firmware loads before a TA kick (`rgx_fwif_client.h:188-249`) and the errata sets (`:255-270`); none gives TA register offsets (HDR is trimmed: no names in `0x180-0x32f`, `0x340-0x3c7`, `0x3d0-0x42f`, `0x468-0x49f`, `0xc00-0xd20`; checked by script). The DDK is Series6XT; A9 is Series7XT Plus; BRN/ERN numbers are not mapped to A9 silicon.

---

## 2. The working-driver contract

### 2.1 Pipeline, PM clients, who provides what

```text
VDM --(PDS/USC vertex tasks)--> UVB --> VCE --> PPP --> TE/TEAC --> PSG --> end of TA (EVENT_STATUS bit 5)
                                        |                  |         |
   PM clients (per raster pipe):      VCE0/1            (PPP)     TE0/1    ALIST0/1   <- BIF_PM_CAT_BASE_{VCE,TE,ALIST}{0,1}
   PM inputs (host buffers):          MTA 128 B, MList, VHEAP 0x600 B, freelist (4-B PFN stack)
```

The stage order and "VCE stores vertex data in PM pages" are INFER from the per-requester cat bases (HDR lines 3434-3470; MAIN `pvr_rogue_fwif.h:2145-2150`), `TA_RTC_ADDR` = "TA Render Target Caches, for the VCE, TEAC and PSG" (`cr.xml:836`) and the PTE text on PM memory (`pvr_mmu.c:615`).

* The **host writes no TA register**: it provides a command with a small register image (`geom_regs`; MESA `pvr_arch_job_render.c:719-788`), the HWRT dataset (MAIN `pvr_rogue_fwif.h:2117-2175`), memory objects, and the MTS doorbell (`wmb(); write; mb()`, MAIN `pvr_fw.c:1071-1081`, DDK `rgxfwutils.c:179-189`).
* **Per-requester PM roots** (`vce/te/alist_cat_base`) are HWRT fields the firmware fills; neither Mesa nor the DDK host code writes them. AP §12.2 (STATIC): **Apple's kext writes no per-requester state either**; the PM builds lanes itself (E008 appears in the same <=2.2 µs flight sample as the TA start, ME §9, 17 of 18 flights). Absent `E028/E048` is therefore a product, not a missing host field.
* First kick: firmware zeroes RTC/TPC (`bTACachesNeedZeroing`, DDK `rgx_fwif_shared.h:247`); Linux's zero pages cannot discriminate.
* Free list: 4-byte PFN stack, BO flags `GPU_UNCACHED|PM_FW_PROTECT` (`pvr_free_list.c:33-35,107`); PM OOM = event bit 7.

### 2.2 Sizing cross-check (every row matches)

| quantity | Mesa formula (SRC) | 64x64 / 1 sample / 32-px tile | Apple = Linux |
|---|---|---|---|
| `mtile_x1/x2/x3` | `ALIGN_POT(ceil(tiles/4),4)`, x2, x3 (`pvr_arch_job_render.c:146-151`) | 4/8/12 | `TE_MTILE1/2 = 4<<18\|8<<9\|12 = 0x0010100c` |
| `TE_SCREEN`, `mtile_stride`, `PPP_SCREEN` | `x_tile_max\|y_tile_max<<12`; `mtile_x1*mtile_y1`; `(h-1)<<16\|(w-1)` | `0x1001`, 16, `0x003f003f` | same |
| TPC size | `next_pow2(4*4)^2 * TAIL_POINTER_SIZE(8)` (`:249-292`, `rogue_hw_defs.h:81`) | `0x800` | `W+0x44c = 0x800` |
| region array | 5 B/entry (`rogue_hw_utils.h:233-245`) x 16 tiles x 16 macrotiles | 1280 B | Apple/Linux image 256 x 5 B |
| `TE_PSG` | `COT = geometry_terminate`, `region_stride = rgn_stride/4096` (`:754-760`) | `0x20000` | `0x20000` |
| `TA_RTC_ADDR` | layers>1 only (`:211-221`) | 0 | `0xcb0 = 0` |
| MTA / VHEAP / MList | `4*4*8`; `0x180 dwords*4`; `cr.xml:254` "64 KBytes" | 128 B / 0x600 / 64 KiB | A9 aux `a8` 128 B, `b0` 0x600, `a0` 64 KiB per RT |
| `PPP_CTRL` | `0x202` (`:745`) | `0x202` | `0x2` on Apple and Linux (r35 `0x202` stalled the same) |

### 2.3 Completion semantics

`COT=1` (`cr.xml:668-671`): region headers, stream termination and TPC invalidation happen **on the terminate reaching the TE/PSG**. The terminate is in-band, die-internal, per raster pipe, behind earlier vertex tasks (`dsx-nx1` §0.6: no MMIO carrier). "VDM consumed the stream" (`0x410` at the last dword) proves fetch only. Both `COT=1` and `COT=0` (r53-03, no `TA_TERMINATE`) produce no response, and a poisoned `TE_PSGREGION_ADDR` produced **no fault** (r34-03): the TE never attempts the write in the natural stall, so the in-band terminate never arrives.

---

## 3. Register map (A9 offsets)

| off | role | basis | class | Linux 6c8=1 |
|---|---|---|---|---|
| `0x130/0x138` | `EVENT_STATUS` (bit 5 TA_FINISHED) / `EVENT_CLEAR` | HDR, MAIN | HW latch / ack | `0` |
| `0x3d0` | bank select `{0x100,1}` TA | STATIC | config | `0x100` after PM prepare |
| `0x240 / 0x2d8 / 0x248` | PM load pointers: `S+0xa8 -> MTA`, `S+0xa0 -> MList`, `S+0xb0 -> VHEAP` | size identity (exact for MTA 128 B, VHEAP 0x600; MList by `cr.xml` text) | firmware-latched | `0x01000000 / 0x01000080 / 0x01010080` |
| `0x290/0x198/0x258` | PM load strobes (write 1, poll bit 0) | STATIC | strobe | reads 0, acceptance inferred only |
| `0x210..0x230, 0x390, 0x398` | PM identity/freelist latch (`0x80009a3c`) | STATIC; r43 6c8=0 tuple `c0264000/000000e1/00000400/000003ff` | latch | in no 6c8=1 list I read |
| `0x408 / 0x470` | `VDM_CTRL_STREAM_BASE` (`cr.xml:261`) / stream end (DDK TERMINATE slot) | SRC | firmware-loaded | `0x40000 / 0x370` (Apple fixed `0x640`: no dependence shown, AP §12.1) |
| `0x410` | VDM cursor, hardware-written, no firmware writer | RC §1 | HW status | `0x4036c` |
| **`0x400`** | **TA/VDM start** | flight r47-04 + `rec[+0x20]` branch | strobe | accepted |
| **`0xc68`** | **TE arm** | flight r47-04 | strobe | accepted (TE busy ~5 µs) |
| `0xcb8` | TE context command port | STATIC | strobe | **acceptance unobserved** |
| `0xc00` | `PM_MTILE_ARRAY` by DDK position; 0 on every Apple job; MTA rides `0x240` | DDK `:190` | unused | `0` |
| `0xc08..0xc98`, `0xcb0`, `0xcc0` | TE/PPP values of §2.2, `TA_RTC`, `TA_CONTEXT_STATE_BASE` (store/resume only, `cr.xml:843`) | SRC | firmware-loaded | landed (RC §1) |
| `0xc30 / 0xc34` | PPP bbox, self-disabled by the stream's `STATE_PPP_CTRL`; the bbox-enable factor on the executed word was flown (r55-03, `no-downstream-witness`) | `dsx-nx97`, `dsx-r63:185` | not a witness | reset values |
| `0xc50` | TE flush strobe (finish24) | BMAP | strobe | the image it yields equals Apple's finished page in 252/256 entries, **without** coverage bits (AP §0.3) |
| `0x8328` | **`JONES_IDLE`**, set = idle; bit 1 VDM, 3 PM, 6 TILING (MAIN `:4829-4876`) | polarity from kext wait loops (RC §3) | HW status | `0x3d7f` |
| `0x5118` | `USC_UVB_CHECKSUM` (moves with exports; = host-expected) | AP §12.3 | only live member | non-zero |
| `0x5030 / 0x5060` | `VCE_CHECKSUM` / `PDS_DOUTM_STM_SIGNATURE` | AP §12.3 | signatures | 0 of 1466 reads; **no liveness control** |
| `0x5020/28`, `0x5110/20`, `0x5000-0x5018`, `0x5100/08` | PPP/TE/UVS signatures | BMAP, AP | signatures | 0 of 1466; uninformative (zero even when the TE provably wrote 256 headers, r49-01; `dsx-r63:180`) |
| `0x6020` | TA cycle counter (starts at kick, reset by retire, RC §3.2) | RC | HW status | running |

Ordering (STATIC): slot map -> PM identity bind (latch only if id != cached) -> 63-store upload -> PM prepare (`3d0`, `240/248/2d8`, strobes) -> TE arm (`cb8`, `c68`) -> publish `G+0x728` -> `0x400` -> ... -> finish24 (`c50`, `0x430`, PM save, SLC3 maintenance). All polls are plain `GETD` loops with no timeout. Reset/power at parity (SOFT_RESET read 0, GPC gate). `BIF_TRUST` only under `SUPPORT_TRUSTED_DEVICE` (`rgxstartstop.c:535,697`). DDK `REG_CFG` per-kick lists (`rgx_fwif_shared.h:466-483`): no A9 counterpart searched.

---

## 4. Hand-off configuration inventory (USC -> UVB -> VCE -> PPP -> TE -> PSG/PM)

For each hop: the configuration that governs it, its parity with Apple/Mesa, and the witness that exists. Nothing in the "config" column is left to author.

| hop | configuration | parity | witness | status |
|---|---|---|---|---|
| VDM fetch/walk | `0x408`, `0x470`, stream words, PPP/PDS blocks | identical (run18 diff; `0x410` at the terminate) | `0x410` | works |
| VDM -> PDS -> USC vertex task | `VDMCTRL_PDS_STATE0-2`, `VDM_STATE0-5` (unified/common/output sizes), PDS code/data, USC code | **byte-identical** to Apple's `g1` (run18 diff); `vend`/`DOUTU.end` present (`dsx-nx99` §0) | `0x5118` | works |
| USC -> UVB export | vertex program, vertex data | `0x5118` = host-expected (423/584 lines) | `0x5118` | works |
| **UVB -> VCE** | `TA_RTC` (0 for 1 layer), PM MTA/MList/VHEAP/freelist (accepted by PM: 3 MList pages scaffolded), VCE0 client (E008 built at TA start) | parity; no host-authored delta | `0x5030`, pool pops | **nothing latched, no pop** |
| VCE -> PPP | PPP state blocks, `PPP_CTRL/SCREEN/WCLAMP`, `OUTPUT_SEL` words in the block | **byte-identical** blocks; values equal | `0x5020`, bbox (blind), `JONES` IPP bit (never clears in 144 flights) | no witness live |
| PPP -> TE | `TE_*` register values (Mesa-equal), `c68` arm | equal; TE busy ~5 µs then idle; **never relights** | `JONES` TILING bit | arm answered, no data |
| TE -> PSG/PM | region/TPC bases (poison -> no fault, r34-03), `COT=1/0` | equal | pops, region coverage | never attempted |
| terminate | VDM `STREAM_TERMINATE`, PPP terminate block (byte-identical) | equal | `0x130` bit 5/6 | not delivered |

Residual UNKNOWNs inside the config column: `0xcb8` command acceptance and the three PM-poke acceptances (reads of 0 are uninformative); `INDEX_LIST` presence-bit layout (r71 flown); PM freelist latch `0x210..0x230` in the 6c8=1 epoch (unobserved).

---

## 5. What the retained data fix (ME re-parse of 144 flights / 143 blobs, 24 536 `jones8328` events; RC §2-§3; AP §12.3)

| datum | value | reads as |
|---|---|---|
| busy bits seen | only 0 BIF, 1 VDM, 3 PM, 6 TILING clear in real flights; bits 2 CDM, 4 USCS, 5 IPP, 8, 10-13 never clear | `JONES` cannot show USC/IPP activity; it cannot show "vertex work did not run" |
| VDM vs TE end | VDM last busy sample after TE last busy: **21/29 draw-named flights** (20 by >=2.5 µs; RC 17/27), 0/22 empty | TE goes idle while the VDM still issues; nothing after reaches the TE |
| PM / TE episode | PM span median 2.3 µs empty, 1.3 µs draw (`r39` flights, 2.2 µs cadence); TE 4.2 vs 3.8 µs; RC ~3.8 µs both | fixed arm / start-up handshake, not stream-scaled |
| VDM span | empty 0, draw 5.2 µs | the draw stage really runs |
| `E008` vs TA start | same sample 17/18 (one 26.6 µs earlier; at 2.2 µs cadence the PM-prepare strobes cannot be told from the kick) | the VCE0 client is registered at TA start, by the PM, from nothing the host authors |
| pool / TPC / region | `changed=3 delta=70` only, TPC zero, no coverage bits; poisoned region base no fault | no primitive or terminate ever reached the tiler |
| `0x8328` / `0x6020` / `0x130` | `0x3d7f` / running / 0 at +102 ms | idle with the TA open |

Three consequences: (i) the break is **after UVB export and before the first primitive/terminate reaches the tiler** (H2 or a global condition on that path); (ii) no host-authored PM or stream field can be the lever (§4); (iii) the PPP/TE/VCE signatures cannot arbitrate until a positive control exists (§7 T2).

---

## 6. Ranking

| rank | candidate | basis | prob. (AP, my review) | test |
|---|---|---|---|---|
| 1 | **H2: state/terminate delivery to the TE broken in hardware** (VDM -> PPP -> TE control path; UVB -> VCE is downstream of the same cause or a second defect) | §4/§5: all inputs at parity, export correct, nothing latches downstream, terminate undelivered; common-mode with empty streams | ~65 % | locate by Apple positive control (T2); no Linux lever identified |
| 2 | **H3: hidden global state** (power/clock/governor; geometry-side gate not visible in R0/R1) | named, never-flown, one-word member: the governor ceiling `policy+0x688 = 0` vs Apple 400 (`dsx-r74-power-handshake` §0.3-0.4, host and Apple values [V]); both Linux constructions (6c8=0 policy off, 6c8=1 ceiling 0) stall identically, Apple has policy on with ceiling 400 | ~20 % is the bucket; the governor is a small fraction of it | **T1** |
| 3 | H1: PM client set (TE0/ALIST0/TE1) | Apple authors none (AP §12.2); lanes are PM products | ~10 % | none authorable |
| 4 | PM-memory PTE attributes (TA output write behavior) | §3 of the earlier version: `PM_FW_PROTECT` everywhere in MESA/DDK/MAIN, Apple aux `PA\|0x4000000000000001`, Linux `PA\|0xd`, never tested | ~5 % | **T3** |
| - | kick, doorbell, event path, host PM descriptors, `PPP_CTRL`, `TE_PSG`, per-cluster table, `W+0x45c`, N sweep | closed or out of scope | ~0 | do not re-run |

Mechanism adopted for T1 (not the DDK's `DUST_CHANGE/POW_ON`, which is not shown to exist on A9): `fable51-setup-audit-r74.md` I6, "firmware-driven pstate transitions never run on Linux", i.e. the `R1+0x0/0x1000/0x1004/0x8` wrapper traffic of the power tick and `fw_setGPCPerformanceState`. On unit 6 I adopt the later, complete census of `dsx-r75-apple-pio8-table.md` §3.3 (`DisplayUnderrunWA`, reachable only under policy-on, no TA/PM/ARM3 site): the unit-6 write is **not** a geometry lever, which lowers T1's prior relative to `fable51` §C1's clock/domain reading and makes the descriptor a safety item only. Caveat on rank 2: the governor claim rests on `dsx-r74-power-handshake.md` (the firmware computes `policy+0x38 = max(min(policy+0x6f0, policy+0x688), ctrl+0x102c)` and sets `policy+8 = 2` below 100, polarity [I]); `sonnet55-apple-ctrl0-policy-audit.md` §7.1 lists `policy+8/+0xc = 0/4` as host-equal to Apple and ranks the policy axis "OPEN, medium, no evidence ties the stall to policy". The two disagree on whether `policy+8` is host- or firmware-owned, which is exactly what the T1 RAM witness decides.

---

## 8. UNKNOWN / limits

* Every µs datum is 6c8=0 (r33-r47 builds); 6c8=1 has only the +100 ms bank and the host ring (RC §9).
* "VCE stores vertex data in PM pages" and the stage order are architectural INFER.
* `JONES_IDLE` USCS/IPP bits never clear in any flight (so "USC/IPP idle at +100 ms" is not evidence about vertex work); RC §3.1 lists bits "7, 9, 13, 14" as constant 0, but `0x3d7f` has bit 13 set (likely 14).
* Whether `policy+8` is host- or firmware-owned in the 6c8=1 epoch (T1 witness decides); the identity-cache init value (`0x7f` looks "unbound", writer not located); `0xcb8`/PM-poke acceptance; whether `0x5030/0x5060` are live on this core (T2/T4).
* Whether signature capture is gated: the DDK `RGXFWIF_INICFG_*` flags on disk (`rgx_fwif.h:409-422`: context switch, `POW_RASCALDUST`, `HWPERF`, `HWR`, `CHECK_MLIST`, `DISABLE_CLKGATING`, `POLL_COUNTERS`, VDM store mode) contain no signature flag, so the 1466 zeros have no init-config explanation on disk; a hardware-side enable is not excluded (T2/T4).
* Apple's TE write timing before the terminate (AP withdrew the start-of-job reading); the writer of the constant region image (TE via `c50` per AP, undecided in nx10).
* DDK errata (BRN37918/38059/44455/52563) and the DDK `REG_CFG` mechanism: A9 applicability not established.

## 9. Reproduce (read-only)

```text
# flights (ME): jones8328 busy bits, VDM-vs-TE end, PM span, E008 vs VDM start
python3 -I <script>   # regex 'RENDER r\d+ flight-event job=N ns=T ch=(jones8328|e008|vdm0410) value=V' over build/gpu/*diagnostic_blob.txt
# JONES_IDLE bit map
sed -n 4829,4876p build/gpu/refs/linux/pvr_rogue_cr_defs.h
# stream/PPP/PDS/USC parity (Apple stress vs Linux)
sed -n 1,60p build/gpu/run18-linux-diff-dryrun/run18-linux-diff.txt
# PM_META_PROTECT never set on Linux
grep -rn "<< 62\|BIT_ULL(62)\|META_PROTECT" build/gpu/round82/src/work/*.inc patches/gpu/*.patch
# TA epoch locked to dc_variant 7
sed -n 930,950p build/gpu/round82/src/work/boot-r73b.inc
# governor inputs
sed -n 28,60p docs/gpu/experiments/dsx-r74-power-handshake.md ; sed -n 355,360p docs/gpu/experiments/sonnet55-apple-ctrl0-policy-audit.md
```
