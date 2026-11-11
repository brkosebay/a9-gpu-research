# r95b: what the natural TA wrote (analysis of the sealed raw folder)

2026-10-30. Claude Sonnet 5.5 research sub-agent. Host only: no device access, no kernel branch touched, no commit, no verdict script used as a gate.
Folder: `build/gpu/round95b/raw/20261030T162028Z/stage01-attempt1/` (entry `tri95b-ad1c099ed8`, payload sha256 `ed1b8865fb57…`, cold-direct, one attempt). Sealed offline in section 1.
Labels: **OBSERVED** = read in a byte or line of the folder (or of a sealed sibling folder / retained capture), the check is named. **DERIVED** = computed from OBSERVED data or argued from it, the assumption is stated. **UNKNOWN** = not in the data. The inspection snippets (appendix) are throwaway readers, not gates, and are not committed.

## 0. Answers

1. **Did the natural TA execute meaningful tiling output? Yes, beyond the retire artifact, for the first time on Linux.** OBSERVED: the TA retired naturally (state 3, stamp 1/1, `pm_saved=1`, consumer = producer = 1, G2 type-1 completion event, no fault / recovery / page-request / channel-error event). The region image holds the r82c/r84a/r84b "retire template" **plus six changed words, and those six words are exactly the six where Apple's region page differs from that template** (r95b equals Apple's value at all six; section 4.1). aux0 holds the 16-entry per-job region record (the "a8" record) with all 16 entries satisfying the documented formula against *our* RT0 VA, and the 13-page PM allocation list; PM control carries the lane state Apple's completed job has (57 of 80 words equal Apple's, the rest are pointer / meta-alias / Linux-only words); 10 PM payload pages changed (138 words). DERIVED: that is TE/PSG and PM work for a real job, not the empty-finish artifact that r82c/r84a/r84b/r70 produced.
2. **Expected to stay zero for this minimal job:** TPC (live-only witness, emptied at the terminate; section 4.3), RT1-RT3 (a 0x500-byte region table lives in RT0 only), aux1-aux4 (one record), the TA store, store-ctx and store-resume (no context store happens when a job completes), `pm-list` unchanged (it is host input). None of these zeros is evidence against the TA. Section 6.
3. **Is the region image valid enough for dependent 3D?** Structurally yes, and where Apple's page is known (first 256 bytes) it is identical. **Not proven that the ISP can follow it**: the link targets (the per-tile blocks in the 10 changed PM payload pages) were not saved, and no capture on either OS has ever read them. Section 6.
4. **3D preconditions now proven** and **what r96 must not assume**: section 7. Two items the headline did not carry and r96 must not ignore: the TA took **11.02 s** here against **0.675 s** in r95 (same pre-TA path, 0.98 s inside the 12 s wait that timed r94 out), and the completion event differs from r95's in one word.

## 1. Closing the folder

The stage wrapper was killed in the liveness-only window, so `header.json`, `SHA256SUMS` and `CLOSED` did not exist. Closed with the repository's own tool, `scripts/gpu/r94-raw-header.py` (the tool `run-raw-stage-r95b.sh` calls; its sha256 `e8e9ef21...` equals the pin in `campaign-start.json`; all 16 pinned tooling hashes match the current files). I first ran `header` + `seal` on a scratch copy outside the repo, then on the real folder.

| step | result |
|---|---|
| `OFFLINE-CLOSURE.json` written first, inside the folder | records every argument's provenance and every field the tool cannot reconstruct; lists the sha256 of the 16 pre-existing files |
| `device-r76-used.txt` | the wrapper's own literal host-side `grep '^@@rc '` over the preserved render-runner (run-raw-stage-r95b.sh line 71): `attach=0 prepare=0 ta=0` |
| `netconsole-post-record-offline.txt` | bytes `[205845352, 205859941)` of the live host netconsole log, copied after the wrapper died, clearly named; `R95B alive n=4 .. n=120`; **not** the wrapper's `netconsole-closed.txt` (not created) |
| `header` args | `--engine-rc -1`, `--t-start 1793377240`, `--t-end 1793377295`, `--netconsole-end 205845352` (the rest straight from receipt / wrapper.log / campaign-start.json) |
| `seal`, `verify` | `OK 20 files`, `closed_epoch 1793378375`, `sha256sums_sha256 ccadaffd...`; the 16 pre-existing files have the same sha256 in `SHA256SUMS` as before (checked); the seal dropped write bits only |

Fields that are **not** faithful measurements (all stated in `OFFLINE-CLOSURE.json`): `runner_rc = -1` is the wrapper's "engine never returned" sentinel (the sealed killed r95 folder has the same), not an observed rc. `t_end_epoch / t_end_utc / duration_s (55)` are a **lower bound** (the last liveness line; the kill time is not in the folder). `netconsole.offset_end 205845352` is the end of `netconsole-at-record.txt` (verified byte-identical to the live log slice), not the wrapper's close offset. `reachable`, `freeze`, `boot_id_after`, `bootstrap_rc`, `render_rc`, `export_rc` stay `null` because the engine's final receipt line (engine line 241) never ran; `receipt.txt` was not edited. For the reader only: `@@r95b-record-end` is present (the engine's own `reachable=1` condition) and host.log ends `stop: done rc=0`. The `r82c / r85 / r88 / r87b / r94` sections are `present=false` and `header.files` omits the r95b files (`r94-raw-header.py` parses blobs r95b never reads); `SHA256SUMS` covers them. `header.json` otherwise: `submitted / consumed / completed = true`, `timed_out = false`, `refused = false`, `kexec = false`, 3D counters 0.

## 2. Run facts (what the headline said, verified)

| claim | check | status |
|---|---|---|
| `state=3 done=18 ret=0` | record line 1; `R95B cap-end ... objs=18 lines=42 raw_bytes=171936`; `record-end state=3 done=18` | OBSERVED, confirmed |
| stamp 1/1, `pm_saved=1`, cons = prod = 1 | record line 1 and `R74B TA RAM complete stamp=00000001 pm_saved=1 consumer=1 producer=1`; `pm80=3`, `idle=0/0/0`, `ctl=2/2` | OBSERVED |
| region image `nz=254`, RT0 aliases it | both `nz=254 dlt=254 first=8 last=0x4f8`; same VA `0x1_0102_0000`, PA `0x8_1e0f_4000`, leaf; region image is RT0 window `[0,0x500)` (`roff=0 rlen=1280` inside `roff=0 rlen=16384`); the rest of the 16 KiB page is zero | OBSERVED, confirmed |
| TPC zero | `nz=0 fnv=76efddc5` (the all-zero 16 KiB digest), unchanged | OBSERVED |
| PM free changed 1024 words | `dlt=1024`; **but the same happened in r93 and r94 (TA not complete)**: not a completion discriminator (section 5) | OBSERVED; headline needs the qualifier |
| aux0 descriptor-like | much more exactly: the documented a8 record plus the 13-PFN a0 list (section 4.6) | OBSERVED, sharpened |
| SoC survived, liveness healthy | `liveness.log` 6/6 `rc=0` (uptime 89.83 .. 100.71 s); **all 120 `R95B alive n=1..120` lines arrived, no gap** (n=1..3 in `netconsole-at-record.txt`, n=4..120 in `netconsole-post-record-offline.txt`), n=120 at kernel 209.01 s, about 123 s after the record; 120 is the kernel's designed heartbeat cap (`G5P_R95B_HB_COUNT`), not a stop. Second (refused) invocation, sealed: n=44..46 on the same boot id. Live host log at analysis time (not preserved in any folder): charger / firewall lines continue to kernel 242.88 s | OBSERVED (folder-backed: >= 123 s); the 242.88 s figure is live-log only |
| TA "natural" | publish -> completion latency | **see next row** |
| TA latency | printk clock: `ta-publish` 75.128915 -> `G2 event index=142 type=1` 86.150781 = **11.022 s**; r95: 73.363276 -> 74.038362 = **0.675 s**; r94 (stall): publish 61.771 -> timeout 73.771 (`ret=-110`, 12 s) | OBSERVED, not in the headline |
| completion event | r95b raw event words (omitted); r95 identical **except word 5: 0 there, 1 here** | OBSERVED, meaning UNKNOWN |

Timeline inside the capture (kernel `ktime`, `t_ns`): capture A start 86.133054 s, end +0.743 ms (18 objects, 171936 B memcpy, 42 console lines); the checkpoint's own END digests 86.133810-86.133936 s; capture B end 86.136917 s. DERIVED: the capture-A digests equal the END-checkpoint digests for all 18 objects (len, fnv, nz, delta, was, now; checked), so nothing moved across the ~0.9 ms between them.

Event / IRQ cadence during the wait: events 2590 -> 5775 and irqs 5179 -> 11549 over 11.0 s, i.e. about 290 events/s and 580 IRQ/s, the same rate as r95's 0.675 s window (3107-2906 events). DERIVED: the 11 s was ordinary DC ALIVE traffic, not an error storm. Why the TA took 16 times longer than in r95 is UNKNOWN (n = 1 each; the pre-completion path of r95b is r95's byte for byte, the r95b hooks act only from capture A on).

**Survival, honestly (DERIVED, n = 1):** r95 was alive about 0.77 s after its TA complete and then stopped during `r73b-export` (end bank MMIO, IRQ-thread banks, blob export). r95b removed the whole export command and every post-retirement MMIO, and the SoC lived at least 123 s after the record (folder-backed: kernel 86.13 -> 209.01 s; the live log reaches 242.88 s, not preserved). That weighs against the "spontaneous stop after TA completion" rank of `r95-post-ta-freeze-analysis.md` for this path (one MMIO-free survival cannot refute a possibly probabilistic stop), and fits the MMIO-induced ranks; it does **not** isolate which of the removed pieces (end bank, IRQ bank slot 1, the `command` write, blob export) caused r95's stop.

## 3. Layout of the 171936-byte raw file

OBSERVED. `r95b-raw.bin` sha256 `c231d314...4519a4`; the `.b64` decodes to it (trailing newline only). The 14 copied objects are back to back in capture order; the region image, store-ctx and store-resume are windows of their parents. **Every object's FNV-1a over u32 words, nonzero count and first / last nonzero offset, recomputed from the raw bytes, equals the kernel's printed value (18 / 18).** The record's `R95B region` (1280 B) and `R95B pmc` (320 B) rows equal the raw bytes. The 42 `R95B raw` console lines equal the raw bytes and their running FNV (`f0f2a43e`) equals `cap-end chain_fnv`: no console line was dropped.

| object | raw offset | bytes | VA / PA (mapped objects) | nz | words changed vs pre-TA | note |
|---|---:|---:|---|---:|---:|---|
| rt0 / region-image | 0 | 16384 / 1280 | `0x1_0102_0000` / `0x8_1e0f_4000` | 254 / 254 | 254 / 254 | one object, two views |
| tpc | 16384 | 16384 | `0x1_0103_0000` / `0x8_4765_4000` | 0 | 0 | |
| rt1 / rt2 / rt3 | 32768 / 49152 / 65536 | 16384 each | `0x1_0102_4000` / `_8000` / `_c000` | 0 | 0 | |
| pm-control | 81920 | 320 | (PM RAM) | 37 | 22 | |
| ta-w | 82240 | 1376 | | 70 | 2 | |
| store (+ store-ctx 484 B @83616, store-resume 92 B @84128) | 83616 | 1024 | | 8 / 0 / 0 | 0 | |
| aux0 .. aux4 | 84640, 101024, 117408, 133792, 150176 | 16384 each | `0x1_0100_0000` + k*0x4000 | 44, 0, 0, 0, 0 | 44, 0, 0, 0, 0 | |
| pm-list | 166560 | 1280 | | 288 | 0 | |
| pm-free | 167840 | 4096 | | 1024 | 1024 | end = 171936 |

Every mapped object's page-table leaf equals the leaf the mapper would write (`leaf == exp`, flags 3): mappings were intact at the capture. The pre-TA baseline words themselves are **not** in the folder; only `was / now` of the first changed word per object. So per-word "what changed" below uses a stated reconstruction where needed.

## 4. Object by object

### 4.1 Region image / RT0 alias

Decode (OBSERVED): 256 five-byte entries (u32 LE + tag byte) = 0x500 bytes. 228 entries `0x60`, 24 entries `0x70` at idx 7, 13, 15, 29, 31, 45, 47, 61, 63, 71, 79, 95, 111, 127, 135, 143, 159, 175, 191, 199, 207, 223, 239, 255 (the same set `82-ta-output-observation-audit.md` pre-registered), tag 0. Only entries 0-5 differ from that template:

| entry (real-tile slots 0, 1, 4, 5 per `84b-device-analysis.md`) | retire artifact r82c/r84a/r84b/r70 (u32, tag) | r95b (u32, tag) |
|---|---|---|
| 0 | `0x20`, 0 | `0x0`, 0 |
| 1 | `0x20`, 0 | `0x0`, **`0x80`** |
| 2, 3 | `0x60`, 0 | `0x60`, 0 (template) |
| 4 | `0x20`, 0 | **`0x2000`**, 0 |
| 5 | `0xb0`, 0 | **`0x2090`**, **`0x80`** |

Checks (OBSERVED, computed):
- Setting the six dwords `+0x0, +0x4, +0x8, +0x14, +0x18, +0x1c` of r95b back to the r70 / r84 retire values `0x20, 0x2000, 0x600000, 0x20, 0xb000, 0x600000` reproduces **word-FNV `ff1a1445`, nz = 256 (0x500 span) and `783ad345` (16 KiB page)**, the digests `84b-device-analysis.md` section 2.4 recorded for the r82c / r84a / r84b retire image. So r95b = the retire template + exactly those six words, nothing else on the page.
- The Linux r70 `region.bin` (256 B) and Apple's page differ in exactly six words (`run18c-clearonly-...-diff.txt`, "region vs linux region": `+0x0 / +0x4 / +0x8 / +0x14 / +0x18 / +0x1c`). r95b has Apple's value at **all six** (values omitted); patching Apple's six values into r70 reproduces r95b's first 256 bytes exactly.
- The older prediction: `ios-te-edge-observation-options.md` ("Apple's TE got primitives; ours holds only empty-tile setup codes") and `84b-device-analysis.md` ("no region link byte was written for any tile, including the four real ones"). Both stood until this run.

DERIVED: the TE/PSG reached the terminate with real work for the real-tile slots and wrote the link-style fields (tag `0x80`, `0x2000`, `0x2090`) that Apple's TE writes for its minimal job. Limits: (a) Apple's page is known only over the first 256 B (the `p18` sample beyond is a 0-byte file; `j000-0044-ta_region_headers_at_hold.bin` is 0 bytes): bytes `0x100-0x4ff` are compared only with Linux's own template (identical). (b) Apple's source is a clear-only / min job, not our fixture's quad: "same as Apple's" means same minimal-job class. (c) Meaning of `0x2000 / 0x2090 / tag 0x80`: UNKNOWN beyond `dsx-nx40-run16-decode.md` (u32 + tag, tag `0x80` = populated link); the value << 4 reading (0x20000, 0x20900) is not tested here.

### 4.2 RT1-RT3

OBSERVED all-zero (`76efddc5`), unchanged. DERIVED expected zero: `region_stride` counts 4 KiB pages of region headers per RT with a 0x500 maximum; the minimal job's whole table is the 0x500 B in RT0. Same zero in every earlier run, so it carries no information either way.

### 4.3 TPC

OBSERVED: all zero, unchanged, mapped, no fault. DERIVED expected: `dsx-nx40-run16-decode.md` shows Apple's TPC is a live-only witness (per-tile records marched during the job and "emptied by the COT invalidate at the terminate"), and `completeonterminate` invalidates TPC entries on terminate (`dsx-nx4`). Apple's own TPC at completion was an observer gap in run18c, so "zero is the end state" is a model, not a measurement. UNKNOWN: whether the TE ever filled the TPC here (r95b only saw the end), and whether the 3D needs any TPC content (the Apple model says it does not).

### 4.4 PM control (320 B)

OBSERVED: 37 nonzero words, 22 changed against the pre-TA baseline (`first=+0x4 was 0 now 8`). Against Apple's `pm_state_end2ms` (run18c clear-only) 57 of 80 words are equal (17 nonzero in both, 40 zero in both; the 23 unequal are pointer / meta-alias / address-shaped words, `+0x24`, `+0x38`, `+0x3c` and words equal to r70's); against the r70 injected-completion state the lane words the injection lacked are now present:

| word | r95b | Apple | r70 injected | reading |
|---|---|---|---|---|
| `+0x80` | `3` | `3` | 0 | equals `pm80`; the "S" word the r96 precondition needs nonzero |
| `+0x88`, `+0x3c` | `0xd`, `0xd` | `0xd`, 0 | 5, 0 | 13 = the length of aux0's PFN list (4.6) |
| `+0x90 / +0xb0 / +0x110` | `0x8_4754_3001 / 0x8_1e29_6001 / 0x8_0dca_b001` | pointer-class, differ by design | 0x807d77001 / 0 / 0 | lane slots 1-3 valid; the PFNs `0x847543 / 0x81e296 / 0x80dcab` are all in aux0's list |
| `+0x94 +0x98 +0x9c +0xb4 +0xb8 +0xbc +0xd0 +0xd8 +0xdc +0xfc +0x114` | equal | equal | only `+0x94 +0x98 +0x9c +0xd0 +0xd8 +0xdc` present, rest 0 | lane bookkeeping now as Apple's |
| `+0x24` | `0x3e2` | `0xff` | `0x3ff` | free-stack count (4.5) |
| `+0x38` | `0x10` | 0 | 0 | Linux-only change, meaning UNKNOWN |

DERIVED composition of the 22 changed words (reconstruction: pre-TA baseline = the r70 stall shape, nz = 18 as in r94's `before-ta`, with `+0x4` forced 0): 21 words reproduce (`+0x4 +0xc +0x24 +0x38 +0x3c +0x80 +0x88 +0x90 +0x94 +0x98 +0x9c +0xb0 +0xb4 +0xb8 +0xbc +0xd0 +0xd8 +0xdc +0xfc +0x110 +0x114`); the 22nd cannot be identified from the raw. r60-r62 "did not install the expected parameter-manager lanes": they are installed now. In the stalled r93 / r94 only 2 words moved (`+0x4` 0 -> 8 and one more).

### 4.5 PM list, PM free stack, PM payload pages

- **pm-list**: 288 nonzero, 0 changed: host-provided input, expected unchanged. OBSERVED.
- **pm-free**: all 1024 words differ from the baseline (`was[0] = 0x80dca8`, `now[0] = 0x83cc0c`). OBSERVED. **Not a discriminator**: r93 (`was 0x8118d8`, `now 0x84b3cc`) and r94 (`0x849398 -> 0x8494d0`) changed all 1024 words too, with the TA not completing. DERIVED: the stack is rewritten when PM starts, whatever the TA does. Structure now: mostly runs of consecutive PFNs (751 of 1023 steps are +1), 1007 distinct values (17 values appear twice: copies at indices 974-994 and 998-1016), count field `pm-control+0x24 = 994`. Eight of the 13 PFNs in aux0's list sit in the free stack at indices **995-1019, i.e. at or above the count field** (the stale / dead region); five are not in the stack. DERIVED reading: 994 live entries, 30 consumed or dead. UNKNOWN: why 30 slots against 13 allocations, and what the duplicates are.
- **PM payload pages** (`R95B phys`, the kernel's before / after compare of the 256 `physical[]` pages): `nz=10 changed=10 delta=138 first=page 0 offset 0x3000 was 0 now 0x08475d01`. OBSERVED. `0x08475d01 >> 4 = 0x8475d0`, a PFN in aux0's list: DERIVED link-like word. Comparison: r94 0 pages / 0 words (TA stalled), r93 3 pages / 70 words (stalled, `first=1/0x3000 now=3d724001`). DERIVED: the completing run wrote more PM payload than either stalled run; these 138 words in 10 pages are the only candidate for the per-tile data the region links point at, and **their content was not saved** (only digest and count).

### 4.6 aux0 .. aux4

aux1-aux4: OBSERVED zero. **aux0** (44 nonzero words, all changed from a zero baseline; aux0 is zero in every pre-TA checkpoint of r93 / r94): two parts.
- `[0x00, 0x80)`: 31 nonzero words = the **a8 per-job record**, 16 entries of `{lo, hi}` at `+8k`. OBSERVED, computed: for all k = 0..15, `address(k) = (hi << 8) | ((lo & 0x7f) << 1) = 0x1_0102_0000 + k * 0x50`, `lo >> 24 = k | (k == 15 ? 0x80 : 0)`, `lo & 0x00ffff80 = 0`: exactly the formula of `ds-r44-te-inputs.md` ("a8: 16 region-pointer descriptors") with `region_base = our RT0 VA` and stride `0x500 / 16`. The 16 `lo` words are **byte-identical** to Apple's `job-min` a8 record (`ios-probe-run16/20261025T173057Z/job-min/j000-0012-pm_aux_a8.bin`); the `hi` words differ only by the region base (Apple's `0x1_0049_0000`). `dsx-nx40` called this "a host-written region-geometry table ours never writes ... our payload never publishes it": here it exists, and it was written **between the pre-TA baseline and the capture** (zero before in r93 / r94; r95b `dlt = nz = 44`). DERIVED: not by the host payload. By which engine (firmware, PM, TE): UNKNOWN.
- `[0x80, 0xb4)`: 13 PFNs (`0x847543 0x847542 0x847541 0x8461d0 0x8475d3 0x81e296 0x81e295 0x81e294 0x810eab 0x810eaa 0x80dcab 0x8475d0 0x8475d1`) = the a0 state. Apple's `job-min` a0 record also holds exactly 13 PFNs (grouping differs). PM control `+0x3c / +0x88 = 0xd` equals this count.

### 4.7 TA record (W) and store

- **ta-w** (1376 B, 70 nonzero): OBSERVED equal to r94's `w-prep.bin` (= `w-end.bin`) except exactly two words: `+0x550 = 0xcc3f9159`, `+0x554 = 0xffffe702` (both 0 before). The rest, including the addresses, is r94's W byte for byte, so the TA record the 3D will depend on was not modified by the firmware except those words. `W+0x550` is a firmware timestamp (`ios-te-edge-observation-options.md`: on r68-01 only `W+0x550` changed); `+0x554` is undocumented. DERIVED: completion-side words, "retirement only" (they say nothing about the TE). `W+0x88 = 0x100` (matches `render_status w88=00000100`).
- **store** (1024 B, 8 nonzero `+0x3a8..+0x3c8`: `0xc00`, `0x80000001`, `1`, floats `32.0 32.0 32.0 -32.0 1.0`): `cf518c93`, identical to the r93 / r94 `before-ta` digest, unchanged. **store-ctx / store-resume**: zero. DERIVED: host-seeded input, and no context store occurred, as expected for a job that completes.

## 5. Comparison with the controls

| run | TA ended | region image | aux0 | pm-control | pm-free | PM payload pages | ta-w | store |
|---|---|---|---|---|---|---|---|---|
| r93 (`tri93`) | timeout, `ret=-110` | zero | zero | nz 18, 2 words moved | 1024 moved | 3 pages / 70 w | unchanged | unchanged |
| r94 (`tri94`) | fault event 4, timeout | zero | zero | nz 18, 2 moved | 1024 moved | 0 / 0 | unchanged | unchanged |
| r82c / r84a / r84b | stalled / finish | retire template (`ff1a1445`, nz 256, no link byte) | zero | n/a | n/a | n/a | n/a | unchanged |
| r70 / r68 injected `TA_FINISHED` | retired by injection | retire template | n/a | lanes mostly empty | n/a | n/a | only `+0x550` | n/a |
| Apple min / clear-only | completes | template + the six Apple words (first 256 B) | a8 record (same `lo` words) + 13-PFN a0 | lanes valid (57/80 equal ours) | n/a | n/a | n/a | n/a |
| **r95b** | natural, 11.02 s, `stamp 1/1` | **template + the six Apple words** | **a8 + 13 PFNs** | **22 moved, lanes valid** | 1024 moved | **10 pages / 138 w** | **+0x550, +0x554** | unchanged |

Downstream note: `scripts/gpu/r96-parent-evidence.py` pins only the record and raw sha256 of this folder (both equal the pre-closure hashes), so the four added files do not affect it; its docstring still says the folder is unsealed.

The six-word region delta, the aux0 record and the PM lanes are what separate r95b from every earlier Linux run; the `pm-free` change and the unchanged store / pm-list do not.

## 6. The three questions

**Natural TA output.** Meaningful: the six Apple words in the region image; the a8 record pointing at our region base; PM lanes and the 13-page allocation; 10 PM payload pages written. Retirement-only: `W+0x550 / +0x554`, `stamp`, `pm_saved`. Neither: `pm-free` (moves in stalled runs too).

**Expected zero (minimal job):** TPC (live-only, section 4.3; zero is a model-consistent end state, not a measured Apple one), RT1-RT3, aux1-aux4, store / store-ctx / store-resume, and `pm-list` unchanged. None needs a further explanation; none can be used to claim failure.

**Region image for dependent 3D.** Valid structure: yes (256 entries; 252 template + 4 real-tile slots; identical to Apple wherever Apple is known; RT0-aliased so a 3D reading `0x1_0102_0000` sees these bytes, leaf intact). Not shown: that the ISP's walk from these entries succeeds. Slot 0 and 1 carry u32 = 0 (one with tag `0x80`), slot 4 `0x2000`, slot 5 `0x2090` + tag: whether those are valid control-stream links in our address layout is exactly what the per-tile data in the changed PM pages would tell, and those pages were not saved. Apple's own min-job page has the same values, which is the only evidence.

## 7. 3D preconditions

**Proven by r95b (OBSERVED), at the first RAM read after retirement and for the ~0.9 ms to the END digests. The first two bullets are r96's C2 refusal conditions (`96-natural-3d-brief.md` section 3); the page-table, TPC, store and 3D-side items are not in C2:**
- natural TA retirement: `stamp 1/1`, `pm80 = 3` (S word nonzero), `pm_saved = 1`, `cons = prod = 1`, `ret = 0`, `ctl = 2/2`, idle words `0x724/728/72c = 0`, no fault / recovery / page-request / channel-error event, `event_failed = 0`, `g2_pending = 0`, `fault_valid = 0`;
- TA record intact except `+0x550 / +0x554`; `W+0x88 = 0x100`, `stream_len 0x36c` as r94;
- all page-table leaves intact; RT0 (region) and aux0 populated as above; TPC zero; store untouched; 3D side clean (`3D_submitted/consumed/complete = 0`);
- the RAM-only path (zero MMIO after retirement, no export command) keeps the SoC and ssh / netconsole alive for at least 123 s after the record (folder-backed; the live log reaches 156 s, not preserved);
- a natural TA complete now has two samples (r95, r95b); the RAM-only post-TA survival has one (r95b). r95b's capture shows the objects r96 reads through the RT0 alias exist with these contents.

**Must not be assumed by r96 (UNKNOWN or n = 1):**
1. **TA latency.** 0.675 s (r95) vs 11.02 s (r95b) against a 12 s wait. r94 (same PDS contract, pages not all mapped) timed out at 12 s; with every page mapped, 2 of 2 runs completed, at very different latencies, so P(complete inside the window) is not established. The cause of the 11 s is unknown; a TA that finishes at 11-12 s leaves a 3D publish at the edge of the window, and a timeout leaves no 3D. Do not size anything on 0.7 s.
2. **Completion event payload.** word 5 differs (0 / 1); do not match the event words exactly.
3. **ISP link-following.** Region link semantics and targets are unverified (section 6); the PM payload pages (10 pages, 138 words) hold the unsaved data.
4. **Free stack / PM state acceptability** to the 3D: `+0x24 = 994`, 30 dead slots, 17 duplicates, `+0x38 = 0x10`, the 22nd changed pm-control word are unexplained; Apple's stack size differs (`+0x24 = 0xff`). The r96 brief keeps the F-stack arms out; this run adds no evidence either way.
5. **TPC.** Mid-job TPC content unknown; zero after completion is the model's end state.
6. **Survival through a 3D leg.** r95b ran no GPU work after the TA. The inference "the r95 stop was MMIO-induced" is DERIVED from one sample and does not isolate the cause; a 3D engine active after the TA is untested.
7. **Per-word deltas.** The folder keeps only the first changed word per object; the pm-control composition (4.4) is a reconstruction against an assumed baseline.
8. **Warm routes.** r95b's epoch is dirty (the second invocation was refused; the wrapper died during liveness); r96 stays fresh-DFU cold-direct as the brief says.

## Appendix: reading the folder (throwaway, not gates)

Layout and digest check (per object `fnv = ((fnv ^ u32) * 16777619) mod 2^32` from 2166136261 over `raw[roff:roff+rlen]`, compared with the record's `R95B obj=` line); six-word revert: copy RT0 `[0,0x500)` as 320 u32, set the six changed offsets back to their template values, expect fnv `ff1a1445` and 256 nonzero; a8 formula: for k in 0..15, `((hi << 8) | ((lo & 0x7f) << 1)) == 0x0101020000 + k * 0x50`; chain FNV: over `(obj idx byte, off as u32 LE, 64-byte line)` of every `R95B raw` line in order, expect `f0f2a43e`. Controls read: `build/gpu/round93|94|95/raw/*/stage01-attempt1`, `build/gpu/linux-objects-r70/{region,pm_state,pm_state_stall}.bin`, `build/gpu/ios-probe-run18/20261027T094122Z/job-clear-only/j000-0015-pm_state_end2ms.bin`, `docs/gpu/experiments/logs/run18/run18c-clearonly-20261027T094122Z-diff.txt`, `build/gpu/ios-probe-run16/20261025T173057Z/job-min/j000-001{2,3}-pm_aux_a{8,0}.bin`.
