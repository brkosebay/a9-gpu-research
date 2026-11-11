# r91 build report: CONSTRUCTION-REFUSED (`W+0x88 = 0x380`), plus the data lineage of `W+0x88` (host only)

2026-10-30. Claude Sonnet 5.5, r91 implementation sub-agent. **No device, no kernel branch, no compile, no build slot, no payload, no commit.**
Authority: `r91-p1-installer-readiness.md` (read only), `r88-draw-first-drain-brief.md`, the sealed r88 stage 3, `AGENTS.md`, then two later instructions that changed the task: the independent-review safety correction (B+0x380 is a context-store program, not proven same-role) and the owner direction (Orchard's working path is the golden reference; do not assume a one-word patch suffices; data lineage and Mesa-port compatibility first).
Labels: **[V]** = run or read this session (file, command); **[INFER]** = my reading, dependency named; **[UNKNOWN]**.

## 0. Owner summary

* **`build/gpu/round91/DEVICE-READY.md` does not exist; there is no r91 entry or payload.** The one-factor build as specified (`W+0x88 = 0x380`) failed its own proof 1 (role), so construction stopped before any fixture, patch or compile. `patches/gpu/0154-*`, `scripts/gpu/*-tri91.sh` and `build/gpu/round91/` were not created.
* **Why 0x380 is refused [V].** `B+0x380` is the context-**store** task program (`W+0x60` -> `R0+0x440`), not the program Apple's `R0+0x470` word names. It decodes that store program: it launches a USC kernel. Pointing the 0x470 role at it is an unproven second factor, as the review said. Apple's same-role program (layout B: `B+0x100`; layout A: `B+0x640`) has never been captured anywhere in this workspace.
* **Where the mismatch comes from (the owner's question), answered from data [V]:** both of our layers, in this order. (1) **The hand-built test record.** Apple's kernel only copies a userspace-authored record word (`record+0x40`, masked to 16 bytes); the captured iOS record carries `0x100` there. Our fixture builder overwrote it with our own `vdm.size = 0x288` (-> `W+0x88 = 0x280`). (2) **Our kernel's own transformation.** r36/r37 then rewrote `W+0x88` from the stream end (`0x4e0`), and r71 pinned `0x370`, inherited by r85/r88. **Apple's kernel does neither: it is a mask-only copy.** A Mesa path through today's typed UAPI inherits (1) by construction (`vdm_control` is validated as "multiple of 16, <= 0x10000", a length-style check).
* **A one-word patch is not the right unit.** In Apple's flow the `0x470` word **and the heap bytes it points at** are authored together by the userspace driver (Metal), and the kernel copies. The word we got wrong has a partner (the program) we never had. So the fix belongs in the record contract that a Mesa port will use, not in a kernel `W` poke. Orchard's record builder is not in this workspace (section 6); that is the missing reference.

## 1. The data path of `W+0x88`, Apple vs ours [V unless marked]

*(Listing omitted under the no-Apple-code rule; the surrounding text describes the behaviour.)*

| link | fact | evidence (reproduce: `python3 -B -I scripts/gpu/r91-w88-lineage.py`, exit 0) |
|---|---|---|
| importer | `d+0xab8 <- the argument record word 1 = record+0x40`; `d+0xab0 <- record+0x38` (VDM VA); `d+0xb20..0xb48 <- record+0x68..0x90` (store/resume tasks); plain copies, no arithmetic | L1: decompile `build/gpu/firmware-re/round16/fffffff006cba8a0.c` |
| W writer | `W+0x88 = d+0xab8 & ~15`; `W+0x98 = d+0xab0 & ~3`; `W+0x58..0x80 = d+0xb20..0xb48` unmasked | L2: transcription in `make-render-fixture-r22.py` (comment cites kext `6ca9710`). **`6ca9710` was not re-read: it is not in the loaded kernelcache analysis (round16 addresses come from kernelcache `c6b95fcf...`, the shared one is iPad6,11 16.7.10).** Corroborated by data: the captured record's fields equal the W fields they map to |
| Apple's value | captured submit record (identical to the kernel-side capture `submit-pass-linear-000-kernel.bin`): `+0x40 = 0x100` (also `+0x1f0`), store `0x24001002/0x380/0x390_4820`, resume `0x21001002/0x6c0/0x6d0_4820` (layout B) | L3 |
| Apple census | 19 retained W records: `0x100` with store `0x380` (8), `0x640` with store `0x8c0` (11); **`0x280` never occurs** | L5 (`re91-w-regdiff.py --census`) |
| our record | `vdm.size = 0x288` (= terminate VA `0x1_00040284` - VDM VA + 4); builder: `put(record,0x40,m['vdm']['size'])`; template `W+0x88 = 0x280`. Every other copied W field (`W+0x58..0x80`) equals the captured record | L4 |
| our kernel | `render-r36.inc` `g5p_put32(w + 0x88, end)`, `render-r37.inc` `g5p_put32(w + 0x88, len)`, `render-r71.inc` `G5P_R71_REQUIRE(g, "w88", 0x370, ...)`; r85/r88 re-require `G5P_R85_W88 = 0x370` before and after their edit | L6 |
| typed UAPI | `vdm_control`: "multiple of 16, <= 0x10000" -> `W+0x88`, source `record+40`, flagged "r23 open question"; LINEAR64_V1 default `render_user_profile1_vdm_control = 0x280` | L8: `docs/gpu/render-uapi.md` |

Reading **[INFER]**: `record+0x40` was named `size` because the first reading of the word was "stream length" (ds-r32/ds-r36). The census (r91 readiness 3.2) shows it moves in lockstep with the store/resume code offsets (`W+0x88 = store - 0x280` in both layouts), which a stream length cannot do. Apple's userspace therefore writes a heap offset there. The hardware consumer of `R0+0x470` is **[UNKNOWN]**; the only firmware writer found is `start23` (`80007a00`), and `10021abc`/`10021d00` also name `0x470` (`dsx-nx1` 2.5.9) but I did not decode them this session (my decoder call failed), so "firmware never reads it back" is **not** established here.

## 2. The four requested proofs, honestly

| # | requested | result |
|---|---|---|
| 1 | exact code BO `B`, bytes at `B+0x380`, which Linux task uses them, valid PDS entry or data | **Done; this is the failing proof.** `B = 0x3_00000000` (16 KiB, fixture BO0 == `round16-input/code.bin`, byte-identical, L7). `B+0x380` = (captured state words omitted) = a four-instruction context-store program (two data writes, a USC task launch, a halt; decoded with Mesa's public PDS disassembler). Used by: `W+0x60 = 0x380` -> `R0+0x440 VDM_CONTEXT_STORE_TASK1` (`pds_code_addr 0x3_00000380`); the resume twin is byte-identical at `B+0x6c0`. It is a valid, terminating program in the **store** role. It is not shown to be valid in the `0x470` role |
| 2 | `B+0x370` zero in the exact r88 prepared image | Zero in the fixture BO0 (L7), and **inferred** zero in the prepared image: grep of the r71-r88 render sources finds no reference to BO0 (the r85-r88 edits write BO7 and BO5); the only BO0 touch in prepare is the digest refresh under `r58_case`, which r88 does not set (not re-proved). **r88's raw does not dump BO0**, so the prepared bytes are not observed [UNKNOWN until a capture reads them] |
| 3 | fixtures r88 control vs r91 factor, differ at exactly `W+0x88` | **Not generated** (stopped at proof 1) |
| 4 | VAs/PAs < 2^38, PPP terminate then STREAM_TERMINATE, TE_PSG `0x20000`, TA slot 8 | **Not re-run**; the r91 readiness note sections 4 and 5 already show these matched for r88 stage 3 |

The reviewer's flag also lands on the zero bytes: at `B+0x370`, four zero dwords decode as no-op `mad` instructions (disassembler reading only), and the next dword is the store program. If hardware ever executes straight-line from `0x370`, r88 would already fall into the store program, so `0x370 -> 0x380` could be near-equivalent rather than a clean "valid vs zeros" factor. Unproven; it is a second reason the factor is not clean.

## 3. Values `W+0x88` has already flown (prior rounds) [V from docs; the stall persisted in all]

| value | rounds | what `B+value` held | caveat |
|---|---|---|---|
| `0x100` | r23-r26 probe bit 1 (`W88=100 does not resolve this stall`, `24-ta-hardware.md`) | zero | flown with the probe's replaced first VDM word and the early stall state; not the current r88 park |
| `0x280` | r27-r36 and every r31 capture | non-zero bytes that are not the store program (role unestablished) | the hand-built value |
| `0x4e0` / `0x290` | r37 `len16` (`dsx-nx2`: "delivered and read back exactly; the stall is unchanged") | non-zero (`0x4e0`) | stream-derived |
| `0x370` | r51-r88 | zero | stream-derived (walk end) |

So the *value alone* (length-like vs pointer-like) has been varied over four targets without moving the headline TA stall, but never to a **same-role valid program**, because that program is unknown. These flights neither support nor refute the program hypothesis; they do mean a one-word change is unlikely to be a cheap decisive test.

## 4. What a bounded diagnostic would be (NOT built, not offered as a fix)

Only if the orchestrator wants one before Orchard's builder is available:

* **cfg A (record-faithful):** `W+0x88 = 0x100`, nothing else. This is the value in the matched iOS record; with it our `start23` register file equals Apple layout B on every PDS-heap constant (r91 readiness 3.3). The heap target stays zero, so it says nothing about "valid program".
* **cfg B (A plus a minimal HALT):** additionally write one halt instruction (the same one the store program ends with) at `B+0x100`, refresh BO0's digest. Bounded question: *does `R0+0x470` naming a valid, terminating, side-effect-free program instead of zeros change the park?* It does not launch a USC kernel and does not claim to be Apple's program. "Unchanged" would retire only "zeros at the target" as the cause; it cannot confirm the contract. It is meaningful only if hardware executes the target at all (unproven), otherwise it is inert.

Both need the full r88 clone chain (patch 0154, kernel branches, 6 scripts, runner, header parser, `write-ready`) and a BO0 capture (`B+0x360..0x3a0`, `B+0xf0..0x110`). I did not start them: the owner's direction deprioritizes a one-word device build, and the Orchard builder may change what the right record is.

## 5. Compatibility requirements for the Mesa port [INFER from section 1; each is checkable against Orchard's code]

1. **One owner for the word and its target.** `record+0x40` / `W+0x88` and the program at `B+W88` are one userspace-authored unit; the kernel should do Apple's mask-only copy (`& ~0xf`). No stream-derived value, no kernel pin.
2. **Do not name the field a length.** The typed UAPI's `vdm_control` ("multiple of 16, <= 0x10000") encodes the retired reading; validation should be "16-aligned offset inside the PDS/code heap window", plus the program bytes' placement.
3. **The Mesa fork shows no equivalent in what I read.** `pvr_arch_job_context.c` static-state init (lines ~770-830) authors `vdm_ctx_store_task0..2` and `resume_task0..2` like Metal does, but I found nothing there that maps to the `0x470` word (the job-submit path was not audited). Whatever Orchard calls it, Mesa must emit it and its heap bytes.
4. **Store/resume offsets and the 0x470 offset move together** (`store - 0x280`; layout B `0x100/0x380/0x6c0`, layout A `0x640/0x8c0/0xc00`); a Mesa allocator that places store/resume must place the third object by the same rule or Orchard's rule.
5. **Ask Orchard for:** the function/field that fills their `R0+0x470` analogue; its value and the heap bytes for a clear-only and a one-draw job; whether their kernel copies or computes it; then their full TA-record builder for a field-by-field diff against `build/gpu/render-fixture-r22/ta-template.bin` (we already match Apple layout B on 57 of 58 firmware-loaded registers, so a diff beyond `W` is likely in heap content and record fields we do not model).

I did **not** start the Mesa interface itself: it is outside the r91 artifact ownership, and the standing routing sends Mesa work to Codex. Section 1 and section 5 are the input for that lane.

## 6. What was and was not available [V]

*(Passage removed: boot-chain or iOS-side tooling detail, out of scope for this repository.)*

## 7. State left for the parent

* Created: `scripts/gpu/r91-w88-lineage.py` (0755, stdout only, `-B -I`, read-only), this report. Nothing else.
* Not touched: `r91-p1-installer-readiness.md`, any r88/r87x/r90 file, other agents' edits, kernel trees, the build slot, the device. No commit.
* `build/gpu/round91/DEVICE-READY.md`: **absent** (by design).

## 8. UNKNOWN

Apple's program at `B+0x100`/`B+0x640` and its author; the hardware consumer of `R0+0x470` and whether it executes the target; the decode of `10021abc`/`10021d00` (firmware accessors of `0x470`); `6ca9710` re-read against the matching kernelcache; whether the typed `SUBMIT_RENDER_TYPED` path applies the r36/r37 overrides (I only verified the fixed-path sources); the prepared-image BO0 bytes (not in r88 raw); provenance of the store/resume bytes in our code BO (readiness 3.4 says our userland, the manifest says capture-backed retained helpers).

## 9. Reproduce

*(Device/host command block omitted; it targets the private workspace.)*
