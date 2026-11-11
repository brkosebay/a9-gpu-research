# 87 (RE): do Apple's PMGR/GFX bridge writes ("37 bridge writes", "bridge-9 replay") enable, clock, reset, route or unstall the VDM->PPP consumer behind the U584 park?

2026-10-30. Claude Sonnet 5.5, research sub-agent. **Offline only: no device, no build, no workspace commit, nobody's work reverted.** Files written: this one; Ghidra annotations in section 9 (shared server).
Labels: **OBSERVED** = a byte, instruction, register read or raw capture read this session (address or path given). **DERIVED** = arithmetic or a join over OBSERVED data. **INFERRED** = judgement from code structure or analogy. **UNKNOWN** = neither. **PRIOR** = taken from an earlier report, not re-read. Percentages are judgement.
Inputs read: `86-apple-consumer-gate-delta-re.md`, `86-status-430-8328-re.md`, `87-single-pass-boot-re.md`, `87-zero-page-address-re.md`, `r87-brief.md`, `r88-draw-first-drain-brief.md`, `dsx-r74-linux-reset-gap.md`, `dsx-nx18-pmgr-fabric.md`, `41-gfx-bridge-replay.md`, `night-20261030-summary.md`; retained captures `build/gpu/r39-14-*`, `r39-15-*`, `r47-01-*`; live ADT the private live ADT dump (not published) and `IOService.txt`; Linux sources `/tmp/g5p-tri86/{power-r41.inc,core.inc,kick.inc,pmgr-pwrstate.c}` (read-only copy of the tri86 g5p tree).

---

## 0. Answer

1. **No credible bridge subset survives as a mechanism, and I do not propose a new experiment.** The 37 words are plain MMIO stores into two fabric-port register files at `0x201f00000` / `0x201f80000`, outside both GPU windows (`R0 0x201000000`, `R1 0x201e00000..0x201efffff`). They are **AXI2AF bridge** configuration and byte-counter controls (kext strings, section 2.4). They cannot enable, clock, reset or route anything inside the PPP/VDM/TE/PM front end, and they cannot produce an exact dword-weighted 584-slot window. DERIVED + INFERRED (section 5).
2. **The sequence is fully resolved and unconditional for GFX** (section 2): after the PMGR `PS` register of device 124 (`0x20e080340`) reaches actual `0xf`, the PMGR kext stores table 8 (`+0x00=0x120`, `+0x18=0x80010005`, `+0x1c=0x10001`), then the byte-counter controls (`bridge8+0x410c=3`, `+0x4100=3`), then table 9 (32 x `0x00697101` at `+0x00..+0x7c`). Full-width stores, no read-modify-write, no readback, no poll, no barrier, IRQs masked. It runs on every transition to level `0xf`, never per job. OBSERVED (decompiles, section 2).
3. **The AGX kext writes none of them.** The sgx node has exactly two IODeviceMemory ranges (`0x201000000`+1 MiB, `0x201e00000`+1 MiB); bridge 8 starts at `0x201f00000`, the first byte after R1. The kext's extra range table is mapped read-only (`startImageMaps` `0xfffffff006c9e968`). OBSERVED (section 2.1).
4. **Linux reproduces the PS write but not the bridges by default.** Defaults: bridge 8 `+0x18 = 0x4`, counters `0`, bridge 9 `0` x32; `+0x00 = 0x120` and `+0x1c = 0x10001` already equal Apple's programmed values (closed). Section 4. The whole 37-word replay was flown once (`r39-15`): all words latched, survived to firmware-alive, `TA_consumed=1 TA_complete=0` (OBSERVED, re-read here). A bridge-9-only factor is strictly weaker than that flown negative.
5. **Two Apple PMGR items no earlier note had resolved, both closed:** (a) Apple sets `AUTO_PM_EN` (PS bit 28) on GFX after power-on; Linux skips it on warm boots by design, but the DFU boot `r47-01` writes it and still reads `0x3ff auto=0` at every GPU readback: no register-level delta survives at job time (section 3.3). (b) The two provider calls (clock gate, then power gate) cause one transition and one bridge restore, not two (cached-level test, section 2.2).
6. **Rank (section 8): r88 first, FenceBuffer/zero-page pair about 2 %, single-pass about 1 %, bridge replay at most 0.5 %.** It stays unqueued. The one condition that would change that is stated in section 7.

---

## 1. What was read fresh

| item | where |
|---|---|
| Ghidra decompiles (kernelcache `20H350 iPad6,11`, shared server) | `ApplePMGR_restoreDeviceBridgeSettings` `0xfffffff005a39918`; `_configureBridge` (was `ApplePMGR_applyBridgeSettings`) `5a3473c`; `_enableBridgeByteCounters` body `5a34854..5a34914` (no function start); `5a346ac` setter leaf (raw bytes); `5a35704`; `_syncDeviceStatusChange` `5a38a10`; `requestDeviceLevel` `5a382a4` (callers `5a3df0c`, `5a43c1c`); `setPSLevelAndWait` `5a257e0`; `setPSMinLevelClearHistory` `5a256a8`; `restoreRunMaxDeviceStates` `5a2ce18`; `5a3a0cc`; `5a31c38`, `5a31ec0`, `5a31c80`, `5a32a40`; `5a388c4`; `5a34920`; S8000 init `0xfffffff00642f9dc`; ADT parse `5a1e640..5a1e6ac` (raw) |
| ADT (live, hex) | pmgr node: `devices` row 97 (GFX), `bridge-settings-8/9`, `bridge-counters`, `bridge-counter-version`, `perf-domains`, `power-domains`, `clocks`; sgx node `IODeviceMemory` and `reg` |
| Captures | `r39-14` (mode 1 read-only), `r39-15` (mode 2 full replay): every `BRIDGE r41 stage=` line re-extracted; `r47-01` (DFU boot) PMGR trace and GPU PS readbacks |
| Linux | `power-r41.inc` (replay), `core.inc:150-186` (`g5p_fender_wake`), `pmgr-pwrstate.c:100-150, 410-425` (PS set, `keep_on`), `r87` cmdline (813 bytes) |
| Searches | public: the web searches for `bridge-settings` / Apple PMGR bridge returned nothing (only the kernel PMGR bindings, no bridge property). Kext strings: section 2.4 |

---

## 2. Census: every host-side PMGR/bridge write on Apple's path to the first TA (fresh)

### 2.1 Who can write, and what is MMIO versus memory

* **AGX kext: no PMGR or bridge writes.** `sgx@1000000` `IODeviceMemory` = `{0x201000000, 0x100000}`, `{0x201e00000, 0x100000}` (OBSERVED, `IOService.txt` sgx node; `reg` agrees). `0x201f00000` (bridge 8) is one byte past R1. The 9-entry range table at `acc+0x580` (Fender, AIC timer, AIC SW-interrupt, UVD) is mapped by `AGXMetaFirmware::startImageMaps` `0xfffffff006c9e968` with `kIOMapReadOnly` (decompile comment, PRIOR annotation re-read). The AGX text (functions named `AGX*` span `0xfffffff006c587bc..6cbc9dc`) contains two `IOMemoryDescriptor::withPhysicalAddress` call sites: `6c7c144` in `AGXAccelerator_startAndInitializeContextPool` (`AGXG5P_RGXPhysicalBase + offset`, i.e. inside R0) and `6c9ea34` in `startImageMaps` (the read-only table). A third hit at `6c4b6f0` belongs to `AppleARMWatchdogTimer::start` (its decompile reads `wdt-version`, `panic-save-flag-bit`), not to AGX. OBSERVED. (A static scan cannot prove a negative through vtable-dispatched calls; the sgx `IODeviceMemory` list is the stronger statement.)
* **AGX power entry**: `AGXMetaFirmware_setPlatformPower` `6ca0f78` calls the ADT provider twice: `v+0x568(on)` (clock-gates `[124]`), `v+0x570(on)` (power-gates `[124]`) (PRIOR `86` row 1, re-read). Both end in PMGR code.
* **PMGR writes are all device MMIO** through the S8000 accessor slots of the PMGR object: `+0x9d8` read, `+0x9e0` write, `+0x9e8` mask-poll (`5a257e0` calls it as `(reg, off, 0xf0, target<<4, 0x2ee00 us)`), `+0x9f0` bridge write. Role names are INFERRED from the call patterns; the bridge-write leaf is OBSERVED raw: (instruction omitted), i.e. one 32-bit store at `map_base[bridge][die] + offset`, no barrier. (That vtable `+0x9f0` resolves to `6e10820` and then to this leaf is PRIOR, `nx18` 3.1; `6e10820` is not a Ghidra function, so I did not re-read it. The callers `5a3473c`/`5a34854` OBSERVED call `+0x9f0` and nothing else.)
* **Cached / shared-memory side**: the bridge tables (`bridge-settings-N`) are only *read* from kernel memory (ADT copies). No cached store feeds the GPU. The AGX boot-record words (`meta+0x76c`, `[init+0x450]`, `meta+0x6c4`) are a different class (section 6 of `86`), not PMGR.

### 2.2 The call chain and its conditions

| step | function (address) | OBSERVED behaviour |
|---|---|---|
| entry | `5a3df0c` (`id`, `flags`) and `5a43c1c` (power-gates list index) | both call `ApplePMGR_requestDeviceLevel` `5a382a4(pmgr, id, on, clockOnly, die)` |
| level | `5a382a4` | `level = on ? 0xf : (clockOnly&1)<<2` (4 clock-gated, 0 power-gated). Compares with the cached level at `this + die*0x280 + id + 0x1abd0`; **only if different** it runs `5a388c4`, builds the device list (`5a27a68`) and calls `_syncDeviceStatusChange` (`5a385b4`). **Therefore clock-gate(on) followed by power-gate(on) is one transition and one restore; the second call is a cache hit.** (Not "twice".) |
| sync | `5a38a10` `_syncDeviceStatusChange` (panic string names it) | IRQs masked (`_ml_set_interrupts_enabled(0)` unless `+0x77c`), acquires device locks `5a39e94`, per device: `5a256a8` (only if `flags&4 == 0`), `5a257e0`, **if requested level == 0xf: `5a39918` restore at `5a39028`**, then the optional perf-domain restore `5a3a0cc` (needs a perf-domain record), `5a3a004` unlock |
| boot path | `5a2ce18` (`restoreRunMaxDeviceStates`) | for devices whose boot level is `0xf`: same three calls, restore at `5a2d07c` |
| restore | `5a39918` | `count = row[0x18]`; bridge ids `row[0x1c..]`; per id: `_configureBridge(bridge, die)` then, if the bridge has a counter descriptor (`+0x20 != 0`), `5a35704(bridge, 1, 1, die)` |
| tables | `5a3473c` `_configureBridge` | `this+0x29c4 == 0` (version, ADT property `bridge-settings-version` absent on j71t, parse at `5a1e684`): for `i < count`: store `table[2i+1]` at `table[2i]` in stored order. (`==1` would be the driver-managed callback at vtable `+0x9a0`.) |
| counters | `5a35704` -> body `5a34854` | `this+0x29c0 == 0` (ADT `bridge-counter-version = 0`): `ctl = *(u16*)desc`; stores `ctl+0x10c = 3`, then `ctl+0x100 = 3` (`value = enable | 2` clear). `bridge-counters` ADT word for bridge 8 is `0x4000`, for bridge 9 `0` |

**Readbacks and polls: none** in `_configureBridge`, the counter body, or the restore. The only polls on the path are the PS `ACTUAL` waits in `5a257e0`, **before** the restore. Power-state context: PS target `f`, actual `f`, device locks held, IRQs masked. All OBSERVED.

### 2.3 What Apple does to the GFX PS register itself (`0x20e080340`, ps-regs map 4 index 8)

GFX is `devices` row 97, 48 bytes (OBSERVED, ADT hex): `00 00 00 7c | 00*4 | 00 00 08 04 | 00*4 | 00*8 | 02 00 00 00 | 08 09 00 00 | "GFX"`. So: flags `[0]=0x00`, id `0x7c` (124), PS index `[0xa]=8`, map `[0xb]=4`, `[0xe]=0`, `[0xf]=0`, `[0x18]=2` bridges `[8, 9]`, `[0x19]=0`, `[0x1a..]=0`.

| # | write (function) | value | condition for GFX |
|---|---|---|---|
| P1 | `5a256a8`: `PS = (PS & 0xfff00000) \| (PS & 0xfcff) \| ((row[0xf]&0xf)<<16)` | MIN field = 0, history bits 9:8 written 0 | runs because `flags&4 == 0`; MIN = 0 equals the measured value |
| P2 | `5a257e0`: if AUTO (bit 28) set at level `f`: clear bit 28 and history, write, poll `0xf0 == 0xf0` | n/a on first power-on | skipped (AUTO not set) |
| P3 | `5a257e0`: `PS = (PS & 0xfffffcf0) \| 0xf`, write, poll `ACTUAL == f` (`0xf0`, 192 ms) | target f | always |
| P4 | `5a257e0`: `PS &= 0xfffffcff`; **if `(flags&4)==0`: `PS \|= 0x10000000` (AUTO_PM_EN), write** | bit 28 | true for GFX (flags `0x00`) |
| P5 | clear bit 30 (`0x40000000`) / bit 10 (`DEV_DISABLE`) with a write if set | n/a | only if set |
| not run for GFX | `5a3a0cc` perf-domain PS level: needs a perf-domain record (`5a380e8`); ADT `perf-domains` = SOC, CPU only | skipped |
| not run for GFX | clock-id gate: `row[0x19] = 0`; ADT `clocks` = AF, SBR, ISP_SENSOR0/1_REF, VENC, PCIE_APP, PMP, LPO, AOP, no GFX | skipped |
| not run | TVM (temperature/voltage monitor, `events` `GFX_TVM_TEMP_0..3`): S8000 init `642f9dc` reads `gfx-tvm-enable`; j71t ADT has only `gfx-tvm = 1` (different key) | sensor block, no datapath |

### 2.4 What the 37 words are, from the kext's own names

OBSERVED strings (kernelcache): `axi2af-axi-config`, `axi2afConfigDataCount == _bridgeCount`, `AXI2AF Stats`, `fAXI2AFDualRegisterMap`, `ApplePMGR::_configureBridge`, `_enableBridgeByteCounters`, `_readBridgeByteCounters`, `_saveBridgeByteCounters`, `_enableBridgeEventCounters`. `5a34920` reads `ctl+0x110/+0x114` (read bytes) and `ctl+0x104/+0x108` (write bytes) into `IOSimpleReporter` channels tagged `DEVRD` / `DEVWR`. So:

* the two `+0x410c / +0x4100 = 3` stores are **byte-counter enable/clear** for the AXI2AF port of bridge 8 (telemetry); r39-15 read them back as `1` (bit 1 self-clears) (OBSERVED);
* the other 35 words are the per-bridge **AXI port configuration** that `_configureBridge` applies. Their field meaning is UNKNOWN: `0x00697101` x32 (nothing in kext, header or firmware names it; PRIOR `nx18` 2.4 warning stands), `0x80010005` shares its shape with the PCIE (`+0x18`), VDEC-B (`+0x14`), RTMUX and MEDIA tail words (PRIOR). INFERRED: per-master / per-ID attribute tables (32 entries for port B) and a port enable/mode word, i.e. arbitration and accounting.

---

## 3. Linux versus Apple, write by write

| write | Apple | Linux default | Linux switch | captured evidence | status |
|---|---|---|---|---|---|
| PS target f + poll actual (P3) | yes | yes (`apple_pmgr_ps_set`, `pmgr-pwrstate.c:100-150`); warm boots add a 0->f cycle before probe (`kexec_gpu_cycle`) | n/a | `3ff target=f actual=f` in every capture | **closed (equal)** |
| MIN = 0, history clear (P1) | yes | `reg &= ~FLAGS`; MIN untouched (`idle_power_gate` off) | n/a | `min=0` | **closed (equal)** |
| AUTO_PM_EN (P4) | yes (INFERRED from code; no iOS PS read exists) | **skipped on warm j71t**: `auto_enable && !ps->keep_on`, `keep_on = warm && kexec_keep_on` (default true, `pmgr-pwrstate.c:143, 418-421`); **written on a DFU boot** | `apple_pmgr.kexec_keep_on=0` (also changes `power_off`, `~:271`) | `r47-01` (DFU, `warm=0 hold=0`): `PMGR gfx set end @80340 reg=100000ff` at lines 5084 and 5109, then every GPU readback (first `5190`, 13 in the file) is `0x3ff auto=0` | **closed at register level**: same job-time word on both boot classes (section 3.3) |
| bridge8 `+0x00 = 0x120`, `+0x1c = 0x10001` | yes | not written; **already equal** | `gfx_bridge_replay` | `r39-14` before/after/firmware-alive: `0x120`, `0x10001` | **closed (equal)** |
| bridge8 `+0x18 = 0x80010005` | yes | not written; reads `0x4` | `gfx_bridge_replay=2/3` | `r39-14` `0x4`; `r39-15` latched `0x80010005` | **differs** |
| bridge8 `+0x410c`, `+0x4100` = 3 | yes (byte counters on) | not written; read `0` | same | `r39-15` read back `1`, `1` | **differs, telemetry only** |
| bridge9 `+0x00..+0x7c` = `0x00697101` x32 | yes | not written; read `0` x32 | `gfx_bridge_replay=2/4` | `r39-14` all `0`; `r39-15` latched x32 | **differs** |

### 3.1 Placement is already Apple's

`g5p_fender_wake` (`core.inc:152-186`): `g5p_power` (runtime-PM get, genpd on) -> optional r33 hold -> `g5p_r41_bridge_prepare` -> first Fender write (`R1+0x10000`). Apple: PS actual `f` -> restore -> everything else. Same slot. The replay logs all 37 reads at `before`, `after`, `firmware-alive` (`boot.inc:1186`) and `first-TA-kick` (`kick.inc:7`, only for the name `RENDER-TA`). The order inside `g5p_r41_writes[]` is Apple's (table 8, two counter strobes, table 9). OBSERVED (source).

### 3.2 Nothing re-erases them after the replay

No runtime-PM put between `g5p_power` and the kick except at remove (`core.inc:657`); the r33 hold is off by default. `r39-15` shows the values at `firmware-alive`. OBSERVED. The `first-TA-kick` snapshot is **absent from both r39 captures** (grep over `build/gpu/*boot-dmesg.txt`), so "still latched at the first TA bell" is DERIVED, not OBSERVED.

### 3.3 The AUTO_PM_EN delta, closed

`r47-01` is a DFU boot (no `linux,booted-from-kexec`, `warm=0 hold=0`): PMGR trace lines 5083-5109 show the GFX domain starting `reg=00000300` (off), then on with `set end reg=100000ff`, off, on again with `100000ff`. Linux therefore executed the same AUTO write Apple does. The first GPU-driver readback (line 5190, `51.87 s`) and the 12 later ones are `000003ff target=f actual=f auto=0`, the same word the warm boots read. **Either the bit does not latch on this domain or the hardware clears it; in both readings the register state at job time is identical across boot classes**, and both boot classes stall. No further AUTO test is warranted. (The history bits 9:8 reading `1` again after a write of `0` is the usual sticky behaviour; unresolved but equal on both classes.)

---

## 4. Register state immediately before the first TA, Apple versus Linux (retained captures)

Apple column is DERIVED (ADT tables applied by the decompiled sequence); **no iOS-side readback of any bridge word or of the GFX PS register exists** (searched `docs/`, `build/` for `201f0`: only Linux captures and designs).

| word | Apple (derived) | Linux before (`r39-14` 9158, warm) | Linux after mode 2 (`r39-15` 8780) | Linux firmware-alive (`r39-15` 9139) | verdict |
|---|---|---|---|---|---|
| b8 `+0x00` | `0x120` | `0x120` | `0x120` | `0x120` | equal, closed |
| b8 `+0x18` | `0x80010005` | `0x00000004` | `0x80010005` | `0x80010005` | delta unless replayed |
| b8 `+0x1c` | `0x00010001` | `0x00010001` | `0x00010001` | `0x00010001` | equal, closed |
| b8 `+0x4100`, `+0x410c` | `3` strobes (read `1`) | `0`, `0` | `1`, `1` | `1`, `1` | telemetry |
| b9 `+0x00..+0x7c` | `0x00697101` x32 | `0` x32 | `0x00697101` x32 | `0x00697101` x32 | delta unless replayed |
| PS `0x20e080340` | target f, actual f, MIN 0, AUTO written | `0x3ff`, `auto=0` | same | same | equal at readback (3.3) |

Job outcome (OBSERVED, `summary.json` re-read): `r39-14` (no write) and `r39-15` (all 37 written) both `TA_consumed=1 TA_complete=0 terminal=1 memory=0 pixels=0`.

DFU boots: `r47-01` shows GFX *off* (`0x300`) before Linux powers it on, so the bridge registers had no chance to carry anything from the boot chain; there is no reason to expect the DFU state to differ from the warm state. INFERRED (the DFU bridge words themselves were never read, `nx18` case B1).

---

## 5. What the words can and cannot touch

| question | answer | label |
|---|---|---|
| clock gate / PLL / divider of GFX or any sub-block | No. GFX has no clock id (`row[0x19]=0`), no `clocks` entry, no perf domain; the only clock-like control is the PS target, already equal. Bridge words are not clock controls | OBSERVED |
| reset of PPP/VDM/TE/PM | No. Resets are `R0+0x100` SOFT_RESET (firmware), the PS `RESET` bit (31, untouched) and the FIFO reset stream; none is a bridge word | OBSERVED + PRIOR |
| power domain | No. No GPU sub-domain exists (`nx18` 2.3, re-checked: `power-domains`, `perf-domains`, `clocks` above) | OBSERVED |
| routing/enable of the VDM->PPP path | No. That path is inside R0 (VDM block `0x400..0x4ff`, PPP, TE); the bridge ports sit between the GPU's external AXI masters and the SoC fabric. A word at `0x201f0xxxx` is not decoded by R0 | INFERRED (address decode) + DERIVED |
| unstall the output window | Only through a memory-transaction dependency: a slot would have to be returned by something that waits on an external read/write that the bridge config blocks. Against that: stream fetch (VDM consumed whole streams) and PSG region-header writes demonstrably traverse the same fabric (`nx18` 3.5, PRIOR); `JONES_IDLE` shows PM, TILING, IPP, USCS, CDM, HOSTIF idle at every park, only VDM and BIF busy (`86-status` 0.3); compute, which hammers BIF reads/writes, works with the bridges un-restored; and U counts forwarded stream dwords (a 584-slot scalar with per-class weights), which a fabric attribute table cannot produce | DERIVED + INFERRED |
| what only they could change | arbitration and accounting of the GPU's external traffic (QoS, outstanding limits, byte counters) | INFERRED |

**Exact bridge-to-master mapping is UNKNOWN.** The one open corner is "a PPP/TE/PM master class that compute never uses sits on a port-B ID whose zero default blocks it". `r39-15` tests exactly that (port B written, all 32 IDs) and the TA still did not retire; the only way to keep it alive is a conjunction with another missing factor, which a one-factor run cannot see by construction.

---

## 6. Does a credible missing subset survive?

No.

* **bridge 8 `+0x00`, `+0x1c`**: equal. Closed.
* **bridge 8 counters**: telemetry (`DEVRD/DEVWR` reporters). Cannot gate anything. Closed.
* **bridge 8 `+0x18 = 0x80010005`**: the only differing word on port A (1 write). A port enable/mode word at most; port A traffic demonstrably works without it. Not a mechanism for a dword-weighted window.
* **bridge 9 x32**: 32 identical attribute words; port-B traffic classes. Same objection; plus the flown `r39-15` negative.
* **PS AUTO_PM_EN**: closed by `r47-01` (3.3).
* **Everything else in the PMGR path** (retention, sleep depth, perf domain, clock id, TVM): not executed for GFX (2.3).

I therefore do not design a subset experiment. Splitting the 37 words buys nothing: modes 3 (bridge 8: 5 stores, only `+0x18` and two strobes change state) and 4 (bridge 9: 32 stores) already exist as parameter values of the tri86 lineage, and a 1-store mode would need a kernel build, which the question excludes.

---

## 7. The only condition under which I would spend a boot pair (not queued)

If r88 reads **H1/H2** (Δ = 0: closed consumer / credit never returned, `r88` section 2) **and** the zero-page factor and the single-pass factor are both flown and null, bridge replay becomes the last cheap item of the host-authored list (`86` section 4 row 3). Then, and only then, the smallest honest run needs no build:

* **Factor**: `a9_gpu_drm.gfx_bridge_replay=2` (module parameter, `0400`, default 0, present in the tri87/tri87b parent: `build/gpu/round87/src/parent/power-r41.inc`). Delivered as a **same-payload entry variant**: hard-link `Image.gz`, `dtb`, `initramfs.gz`, `COMMIT` of the pinned r87b/r88 entry, new `cmdline` = old plus one token (813 bytes + 31 < the 1024-byte m1n1 limit), new `linux_a9.entry=<entry>-bridge2`, regenerate `SHA256SUMS` (the `package-tri39b.sh:166-180` pattern). Kernel bytes are identical to the control.
* **Exact stores, in order** (`power-r41.inc` `g5p_r41_writes[]`): bridge 8 `+0x0000=0x00000120`, `+0x0018=0x80010005`, `+0x001c=0x00010001`, `+0x410c=0x00000003`, `+0x4100=0x00000003`; bridge 9 `+0x0000 .. +0x007c` (step 4) `=0x00697101`. Placement: `g5p_fender_wake`, before the first Fender write; once per boot.
* **Receipts / void rules**: `BRIDGE r41 stage=before` equals the `r39-14` row (`b8: 0x120, 0x4, 0x10001, 0, 0; b9: 0` x32), `after` equals `0x120, 0x80010005, 0x10001, 1, 1; 0x00697101` x32, `firmware-alive` (and `first-TA-kick` if present) equals `after`. A mismatch, a missing `BRIDGE r41 write` line, `-ENOMEM`, or a `firmware-alive` that differs from `after` is `void-construction`. A `before` that is not the zero state would be a new finding in itself.
* **Meter** (one matched pair, same campaign, same epoch): r87b stage 6 (`s6-edge-n137`, one dword of margin, `86` section 5): control triple `(0x410, 0x420, 0x430) = (0x40364, 0x8a, 0x12)`, `0x5118 = 0`. Pre-registered: any retire flips it to `0x4036c`, `0x5118 = 0x0800033c`. If r88 has flown, the second meter is r88 stage 2 (FF, M=176), `Δ = (0x410 - 0x40eb4)/4` (control 0). Identical triple/Δ = closed at that resolution, nothing more. A move = bisect with modes 3 and 4, one boot each.
* **Hazard**: volatile fabric MMIO only, reset by a power cycle, precedent `r39-15`; no storage, NVRAM, syscfg or boot-firmware write. Worst case a one-boot wedge, warm-kexec recovery.

This is a contingency, not a recommendation.

---

## 8. Ranking

| rank | item | P(moves the U584 park) | why |
|---:|---|---:|---|
| 1 | **r88** (draw-first drain) | not a factor; decides what a factor means | separates closed consumer (Δ=0, `0x5118=0`), credit never returned (Δ=0, `0x5118=0x0800033c`) and lazy retire (Δ>0); every host-state factor is scored against it |
| 2 | FenceBuffer / zero-page VA pair (`meta+0x76c`, `[init+0x450]`) | about 2 % | the only never-flown host-authored word pair that the firmware writes to GPU registers (`R0+0x138a0`, `R0+0xe240`); register identity UNKNOWN (`87-zero-page-address-re`) |
| 3 | single-pass boot | about 1 % | the only unflown ordering delta (`87-single-pass-boot-re`) |
| 4 | **bridge replay (any subset)** | **at most 0.5 %** | no mechanism (section 5); already flown at the TA-completion meter with every word latched; same-class null expected |
| - | AUTO_PM_EN | below 0.5 % | closed by `r47-01` readbacks |

---

## 9. Ghidra annotations (shared server)

Renames: `5a3473c` `ApplePMGR_applyBridgeSettings` -> **`ApplePMGR__configureBridge`**; `5a38a10` -> `ApplePMGR__syncDeviceStatusChange`; `5a382a4` -> `ApplePMGR_requestDeviceLevel`; `5a257e0` -> `ApplePMGR_setPSLevelAndWait`; `5a256a8` -> `ApplePMGR_setPSMinLevelClearHistory`; `5a2ce18` -> `ApplePMGR_restoreRunMaxDeviceStates`; `5a35704` -> `ApplePMGR__enableBridgeEventCounters`; `5a3a0cc` -> `ApplePMGR_setPerfDomainPSLevel`; `5a31ec0` -> `ApplePMGR_setPowerDomainRetention`; `5a31c80` -> `ApplePMGR_setPowerDomainSleepDepth`; `5a31c38` -> `ApplePMGR_getDevicePowerDomainRecord`; `5a32a40` -> `ApplePMGR_powerDomainRecordByID`; `642f9dc` -> `AppleS8000PMGR_initFromDeviceTree`. (Older reports cite `5a3473c` as `applyBridgeSettings`; the address is the key.)
Comments: `5a34854` (`_enableBridgeByteCounters`, not a function start), `5a34920` (`_readBridgeByteCounters`, DEVRD/DEVWR), `5a257e0` (PS sequence incl. AUTO_PM_EN rule), `5a39028` and `5a2d07c` (restore call sites and conditions), `5a382a4` (level mapping, cached-level gate), `5a1e684` (`this+0x29c0/29c4/29b0/29a8` fields), `642f9dc` (TVM keys). `scripts/ghidra-mcp.sh save`: two attempts answered "deferred: server active (need 60 s idle)", the third reported `SAVED ok, changed now=False`, so the renames and comments are persisted.

---

## 10. UNKNOWN

* The meaning of the bridge words (`0x80010005`, `0x00697101`) and which GPU masters sit on which port.
* Whether PS bit 28 latches on GFX (`auto=0` after a documented write says no or cleared by hardware).
* The Apple-side values on a running iPad: no iOS read of bridge or PS words exists (the Apple column of section 4 stays DERIVED; it does not change the verdict).
* The device list builder `5a27a68` was not decompiled: that GFX is a single-entry request is INFERRED from the empty parent field.
* The bridge byte counters could answer "does port A carry traffic at the park"; reading them needs a kernel change (`+0x4104..+0x4114`), so it is not same-build and not proposed.

## 11. Reproduce (read-only)

*(Listing omitted under the no-Apple-code rule; the surrounding text describes the behaviour.)*

## 12. Morning-queue recommendation

1. **Do not queue the bridge replay.** At most 0.5 %, below FenceBuffer (about 2 %) and single-pass (about 1 %), and already flown once with every word latched.
2. **Order unchanged:** r87b stages 1-3 (calibrate `matches-U584`) -> r88 stages 1,2,3 -> zero-page (FenceBuffer) factor -> single-pass factor. Section 7 is the only trigger for the bridge pair.
3. **AUTO_PM_EN is recorded and closed** (r47-01 readbacks); no action, no build.
4. **Free, orchestrator-only, optional:** one read-only iOS observation of `bridge8+0x18`, `bridge9+0x00` and the GFX PS word; only worth it if a later result makes the bridge axis live again.
