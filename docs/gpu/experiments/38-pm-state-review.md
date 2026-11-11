# R38: ds-r38-a checked against the device dumps and Apple's reset function. No round built.

2026-10-24. **Offline only: no device access, no kernel edit, no build, no commit.**
This reviews ds-r38-a before encoding its round-38
cases. Sources:
- all 33 `build/gpu/r3*-diagnostic_blob.txt` captures;
- the a9/gpu tree at `64aae1246b` (`boot-layout.h`, `render-layout-r22.h`,
  `render-fixed.inc`);
- raw disassembly of the shared kernelcache (`scripts/ghidra.py read_memory` +
  capstone, since `6cb1108` has no Ghidra function);
- firmware-re/README.md lines 120-190 and 5005-5030.

**Verdict: none of the four ds-r38-a cases is built.** Each one contradicts a
store in Apple's own PM constructor. The headline finding (firmware writes
`0xe1` into `pm+0x18`) is our own host write. So **a9/gpu stays at `64aae1246b`**.
There is no a9/tri38, no payload, no entry and no ladder. A device epoch spent on
these cases would replace fields that already match Apple with values that
don't.

---

## 0. Three checks that settle it

1. **The `0xe1` comes from us.**
   - `G5P_SHARED_VA = 0xe1c0200000` (`boot-layout.h:11`).
     `render-fixed.inc:685` passes
     `fva = G5P_SHARED_VA + G5P_SHARED_SIZE + G5P_GPU_PAGE = 0xe1c0264000`.
   - `g5p_r22_pm` then calls `g5p_put64(control + 0x14, fva)`. That stores
     `0xc0264000` at `+0x14` and **`0x000000e1` at `+0x18`**, the high half of our
     40-bit GPU VA.
   - The device agrees. In every capture, the first snapshot is taken at stage
     `attached-no-launch` (`r37-01` blob line 1672 → 2393), before any kick. It
     already reads `+0x18 = 0xe1`, while `+0x04` (which the firmware sets to 8) is
     still 0. All 31 boots with a PM section show the same, in every snapshot.
     **[V]**
2. **Apple writes `+0x14` as a u64.** `6cb1108` is the PM reset function.
   README:5021 already documented it, but it has no Ghidra function, so
   ds-r38-a's nine-function census missed it.
   - (instruction omitted) loads the control CPU base.
   - (instruction omitted) is an **unaligned 64-bit store**.
   - `x0` comes from `[[P+0x30]+0x20]→vtable+0x98`. The constructor uses that same
     accessor to obtain the control GPU base `P+0x98` (`cafd30..cafd40`) and the
     list GPU base `P+0xa0` (`cafe68..cafe74`). Apple converts the list base with
     META at `control+0x40`, and that value equals ours (`0xc0260000`).
   - So `+0x14` holds **F's GPU virtual address**, exactly what round 22 encoded
     ("F_GPU is the unaligned u64 at control+14", `22-fixed-render.md` (not published)).
   - **[V] width and accessor.** iOS's numeric value is not captured; see §4 item 1.
3. **Apple places the page-list slices at `+0x80`.**
   - `fffffff006caff8c: add x9,x0,#0x80` / (instruction omitted) sets
     `P+0x90 = list_cpu + 0x80`.
   - `caff88` / (instruction omitted) sets `P+0xc8 = list_gpu + 0x80`.
   - `6cb124c` (`cb12fc..cb1308`) places block `id` at `P+0x90 + 0x24·id` (CPU) and
     at `M(P+0xc8 + 0x24·id)` (META). That is our `list + 0x80 + j·0x24`.
   - The `0x44 + M·0x24` request is only the allocation size, and it is rounded up
     to a page. **[V]**

## 1. What Apple's three allocations really are

ds-r38-a §0.1 says Apple has three allocations and that we merge two of them. That
is wrong. Ours are the same three:

| Apple (object field) | size | role | ours |
|---|---|---|---|
| `P+0x30` wrapper (`+0x20` GPU object, `+0x28` descriptor, `+0x78` length) | `M·u32(P+0x1c0)·4` = `0x1000` at M=32 | **F**, the 4 KiB free-frame array. `6cb14dc` maps `[P+0x30]+0x28` and writes the expanded `PPN+j` frames into it (`cb15dc..cb1638`). `6cb1108` publishes its GPU VA at `control+0x14` and its length at `+0x1c`. | `render_meta[1]` at GPU `0xe1c0264000`, 1024 frames, `+0x1c = 0x1000` |
| control (`P+0x70` CPU, `P+0x98` GPU) | `0x80 + N·0xc0` (`cafc8c..cafc98`) | control header `+0x00..0x7f`, plus records at `+0x80 + i·0xc0` (`cafef4..caff74`) | the `pm` page; header plus record 0 at `pm+0x80` |
| page list (`P+0x78` CPU, `P+0xa0` GPU) | `0x44 + M·0x24` (`cafdd4..cafde0`) | usage block at `+0x40`, slices at `+0x80` | `render_meta[0]` |

ds-r38-a labels `P+0x30` as the "shared control … this is our `pm`" and `P+0x70`
as the "record array". In fact `P+0x30` is F, and `P+0x70` is the control block,
which holds both the header and the records. Both `6cb1108` and `6cb14dc` write the
control header through `P+0x70`.

## 2. Our control block next to Apple's reset plus initial list

`6cb1108` performs the reset. `6cb14dc` then rebuilds the counts and the head.
Values are from `r37-01`, snapshot 1:

| off | Apple writer → value | ours | |
|---|---|---|---|
| `+0x00` | `6cb1108` → 0 | 0 | = |
| `+0x04`, `+0x08` | none | 0 (firmware sets `+0x04 = 8`) | = |
| `+0x0c` | `6cb1108` → 0 (`finish24` increments it) | 0 | = |
| `+0x10` | `6cb1108` → 0, then `6cb14dc` → META of the last slice | `0xc02604dc` = M(list+0x80+31·0x24) | = |
| `+0x14` u64 | `6cb1108` → F GPU VA | `0xe1_c0264000` | = (form) |
| `+0x1c` | `6cb1108` → F length | `0x1000` | = |
| `+0x20/+0x24/+0x28` | `6cb1108` → `{0, 0xffffffff, 0}` (constant at `fffffff005941070`), then `6cb14dc` → count, count−1, 0 | `0x400`, `0x3ff`, 0 | = |
| `+0x30`, `+0x34` | `6cb1108` → 0, host page size | 0, `0x4000` | = |
| `+0x38` u64, `+0x44`, `+0x48` u64, `+0x50` | `6cb1108` → 0 | 0 | = |
| `+0x40` | `6cb1108` → M(`P+0xa0`) = M(list GPU) | `0xc0260000` | = |
| `+0x54` / `+0x58` | `6cb1108` → `P+0x14c<<5` / `P+0x144<<5`, where `P+0x14c = PMconfig+0x18` and `P+0x144 = PMconfig+0x14` (`cb0004..cb0014`) | `0x400` / `0x400` | **iOS value unknown** |
| `+0x5c..+0x7f` | none | 0 | = |
| list `+0x00`, `+0x40..0x4f`, `+0x60` | `6cb1108` → 0, 0, **1** (`cb11e0..cb1200`) | 0, 0, 1 | = |
| record `+0xa0/a8/b0/b8` | `6cb2378` | ds-r38-a §1.3 | = |

The control block, the page list and F equal Apple's constructor in every field
Apple writes. The two exceptions are the `PMconfig`-derived limits at
`+0x54/+0x58` and the numeric value of the F VA, which lives in our VM.

## 3. ds-r38-a, section by section

| § | claim | status | evidence |
|---|---|---|---|
| 0.1, 1.2 | three allocations, and ours merges "shared control" and "record array" | **wrong** | §1: the `M·32·4` allocation is F, and ours has the same three |
| 0.2, 2 | `S = control + 0x80 + i·0xc0`; the `S − pm` delta carries no information | stands | the same arithmetic in `caff64/68` |
| 0.3, 2 "integrity check" | the parameter buffer, chain, counts and PFN table are present and consistent | stands | |
| 0.4, 3.1 (rank 1) | the firmware writes `0xe1` to `+0x18`; `+0x14` must be 32-bit | **withdrawn** | §0 items 1 and 2: it is the host's high half, and Apple stores a u64 |
| 0.5, 3.1, 3.4 | the `RGXFWIF_FREELIST` reading of `+0x00..0x30` | **refuted for this block** | Apple writes `+0x00 = 0` and `+0x14 =` a u64 address. Under that reading, `+0x00` would be `psFreeListDevVAddr` and `+0x14` would be `ui32MaxPages`. The DDK names cannot override Apple's own store widths. |
| 0.6 | the TA start reads only `S+0xa0/a8/b0` | not re-checked | ds-fw-ta-kick |
| 0.7, 2 "free witness" | `pm+0x0c == 0` ⇒ `finish24` never ran | stands | `6cb1108` zeroes `+0x0c`, so a nonzero value can only come from `finish24` |
| 1.1 | `P+0xa0/+0xa8` are "u32 0x24/0x64"; `P+0xc8` is "u32 0xa4" | **wrong** | (instruction omitted) stores the u64 list GPU base and base+0x40; `caff90` stores `P+0xc8` = u64 list GPU + 0x80 |
| 1.2 | "only six writes"; no writer for `0x00..0x0f`, `0x14..0x1f`, `0x34..0x7f` | **wrong** | `6cb1108` writes `0x00`, `0x0c`, `0x14..0x1f` and `0x34..0x5b`. Only `0x04`, `0x08` and `0x5c..0x7f` have no host writer. |
| 1.4, 3.3 (rank 3) | slice base `0x44` vs `0x80` is unresolved | **resolved: `0x80`** | §0 item 3 |
| 3.2 (rank 2) | the aux backing is all zero, and that is the only PM data the start reads | stands, still open | needs iOS (§4 item 5) |
| 3.5 (rank 5) | `0x34`, `0x40`, `0x54`, `0x58` "have no Apple writer" | **wrong** | `6cb1108`, §2 |
| 3.6 | N = 1 vs iOS N ≥ 32, rotating | stands, still deferred | |
| 3.7 | fields proven equal | stands, and the list grows | §2 adds `+0x14`, `+0x1c`, `+0x34`, `+0x38..0x50`, `+0x40` and the list usage block |
| 1.3, 3.8 | the S1/S2/S3 ↔ `PM_MLIST` match; the DDK register names | not re-checked | |

## 4. The four proposed cases

| case | what it would do on this tree | disposition |
|---|---|---|
| 01 `pm_counts` | replaces Apple's u64 F GPU VA at `+0x14` with `0x400` and `+0x1c` (F length) with `0x400`. `0x24 = 0x400` would also break Apple's `count−1` (`6cb14dc` `cb1564/1568`). | **not built**: it removes an Apple-matching pointer. Its decision rule ("`+0x18` still `0xe1` ⇒ freelist reading") can only fire on our own write. |
| 02 `pm_apple_six` | zeroes `0x14..0x1c`, `0x34`, `0x40`, `0x54`, `0x58` | **not built**: `6cb1108` writes every one of them |
| 03 `pm_list44` | moves the slices to `0x44` and drops `list+0x60 = 1` | **not built**: Apple uses `+0x80` and writes `list+0x60 = 1` |
| 04 `pm_psFreeList` | `+0x00 = F`, `+0x10 = 0x400` | **not built**: Apple writes `+0x00 = 0`, and `+0x10` is the META head |

No substitute factor is derivable on the host side either.
- `+0x54/+0x58` need iOS's `PMconfig+0x14/+0x18`. ds-r29 already rated PM growth
  low for this stall, because `head` and the counts never move.
- N rotation stays deferred for ds-r38-a §3.6's reason: with one job in flight it
  cannot start or stop a TA.
- Everything else needs iOS run 8.

If the orchestrator still wants the four cases run as falsification tests, the
r37 pipeline carries over unchanged. That is a build of about one hour, and it is
the orchestrator's call.

## 6. Ghidra

Disassembly comments were added at three addresses and then saved:
- `fffffff006cb1108`: the reset-control store map;
- `fffffff006cb1168`: the u64 store at `+0x14`;
- `fffffff006caff94`: `P+0x90/+0xc8` = list + 0x80. No
function was created, so the shared analysis's function list is unchanged.

## 7. Limits

- `vtable+0x98` on `[[P+0x30]+0x20]` is identified by use: it is the same accessor
  that yields `P+0x98` and `P+0xa0`. It is not identified by its class name. The
  iOS numeric value of `+0x14` is run 8 item 1.
- The `PMconfig` source of `+0x54/+0x58` was not traced. That `x20` in
  `cb0004..cb0014` is the init call's config argument is an inference **[I]**.
  Only the stores themselves were read.
- F's size formula `M·u32(P+0x1c0)·4` comes from ds-r38-a §1.2 and was not
  re-derived here. Its role as F rests on `6cb14dc` and `6cb1108`, which were
  re-read.
- The firmware PM helper chain (`8000a874 → 10005f30 → 1002706c`, plus tag6's
  `100056dc/10005368`) remains the bounded static job ds-r38-a §7 names.
