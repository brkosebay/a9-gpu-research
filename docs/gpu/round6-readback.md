# Round 6 device follow-up: META reset and state-dependent readback

**Actionable conclusion:** remove the META slave-port accesses from the
reset-held arm/load path. Removing the after-arm register dump alone is
insufficient: the previous load stage's first `g5p_meta_write()` immediately
polls the same R0+0xa18 register. Apple's recovered loader supplies its
segment/configuration pairs in RAM, so a CPU/DMA-only load verification
followed by the complete reset-release FIFO is the evidence-backed next
experiment. This note describes evidence and recommendations; the kernel
implementation is maintained by the parent GPU agent.

## What the device actually proved

**Verified device evidence:** the
Omarchy netconsole log
ends with these completed reads and the next attempted read:

- File lines 186–189: R0+0x100 = 0, R0+0x104 = 1, so the 64-bit soft reset
  value is **0x0000000100000000**.
- File line 190: the driver prints its pre-access marker for **R0+0xa18**;
  there is no corresponding raw readback. The orchestrator reports that
  this access hard-locked the system.
- Fender had completed the 0→1 transition and R1+0x1000 was 1. Several
  low clock/ID/reset words had returned before the failing META-port read.

**Verified public register definition:** the sampled primary Linux Rogue
header `pvr_rogue_cr_defs.h`, lines 586–591, names soft-reset bit 32 both
`GARTEN` and `CPU`; its enable value is `0x0000000100000000`.
R0+0xa18 is `META_SP_MSLVCTRL1`; bits 24 and 26 are READY and
GBLPORT_IDLE. The address/bit names agree with Apple's actual port-polling
instructions. **Inferred explanation:** holding the firmware CPU/Garten
domain in reset made this port inaccessible. The log establishes the
state and failed access; it does not independently prove the internal bus
reason for the lock.

**Scope of proof:** these results support actual reset FIFO effects. They
do not prove the later catalogue, scratch and SLC words were read or
programmed correctly, because the old snapshot stopped before reaching
them. An earlier successful read in a different reset state is not evidence
that the same register is safe in this state.

## What Apple does with R0+0xa18

The host reads the port in several paths; it is not an always-on status
register. Inspected examples, all **verified ARM host operations**:

| Function / instruction | Conditions and operation |
|---|---|
| `prepareHardwareForBoot`, `0xfffffff006c9fc10`; read at `...6c9fc98` | Calls firmware virtual +0x290 and checks flags in its other input object before entering the port path. Reads/modifies CTRL1 bit4, invokes `...6ca2fa0`, then polls port readiness while writing T0/T1 enable and internal thread registers. It does not assert SOFT_RESET bit32 immediately before these accesses. |
| Slave-port helper `...6ca2fa0`; first poll load `...6ca2fd0` | Polls CTRL1 until `(value & 0x05000000) == 0x05000000`, then writes CTRL0=0x04800001 and polls again. It does not itself check reset or establish power/reset safety. |
| Stop path `...6c9fa10`; first poll `...6c9fb14` | The port-polling branch is used when the Fender object is absent and virtual +0x290 allows it. The enabled-Fender branch instead requests core=0 and GPC=0 through wrapper operations; it does not take this port path. |
| Controller event handler `...6ca263c`; first poll `...6ca26d8` | Event type 6 executes thread-stop slave writes before subsequent reset/power operations. This is an event-driven lifecycle path, not a reset-held boot snapshot. |
| Diagnostic/thread inspection `...6ca0890` | In its `param_2 == 0` branch, repeatedly uses the same port-ready mask and accesses thread/debug selectors. This routine does not create a valid access state by polling. |

**Verified predicate limitation:** virtual +0x290 resolves to
`...6ca10ec`. With a Fender object, it calls Fender slot +0x18 to get
GPC state, compares it against META init +0x710, and checks Fender slot
+0x78. The actual GPC getter `...6ca4d68` reads **R1+0x1000 low nibble**;
slot +0x78 → `...6ca6624` extracts bit29 from R1 control via
`...6ca6618`. Without Fender, software flags affect the decision. None of
these checks reads RGX SOFT_RESET. This is not a portable predicate saying
“R1 active implies the META port is accessible.”

**Bounded conclusion:** the inspected Apple paths do not demonstrate a
slave-port access while reset bit32 is deliberately held by the host.
They also do not provide a universal local guard proving that every port
access runs out of reset; complete lifecycle state is external to the port
helper. Therefore the new Linux artificial checkpoint cannot borrow the
helper's timeout as proof of safety. A single non-returning MMIO read does
not let a software polling deadline execute.

## Apple boot path has no mid-stream slave copy

**Verified:** `prepareBoot ...6c9feb4` appends the large reset masks,
bit32-only hold, META_BOOT=1, MMU and SLC settings. In the enabled-Fender
path it then appends **final SOFT_RESET=0** and terminates the FIFO. The
bit32-only value is an intermediate entry in this complete stream.
`bootFirmwareAndWait ...6c9f954` requests core=0 then GPC=1 in Fender mode,
and waits for the boot event. It does not interpose a CPU slave-port copy
between the held-reset entry and release.

**Verified RAM loader:** `layoutAndLoadLDR ...6c9f1bc` allocates and maps
the firmware image, copies LoadMem bytes through a CPU mapping, compares
the copied bytes, and applies the selected ZeroMem operations. Its virtual
slot +0x7a8 resolves in G5 to `appendSegmentMMU ...6ca43b0`, which writes
register/value **pairs into the RAM list at image+0x200**. For C0 it appends
the 13 segment pairs. Its LDR case 5 appends the 27 Config register/value
pairs to that list, then a zero terminator and converted pointer handoff.
Those stores are to the RAM list, not R0+0xa10/+0xa08.

The diagnostic's `g5p_make_boot_config()` already constructs that RAM list,
and `map` copies the complete image into coherent DMA pages. Consequently,
the old load-stage slave-port mapping probes, segment writes, payload
copies and Config writes are an added Linux composition, not a requirement
established by this Apple path. **Inferred intended consumer:** the master
bootstrap/firmware consumes the RAM configuration list. Its META instruction
implementation is not decoded, but the host-side staging and absence of
slave copies in this loader are verified.

## Restricted next experiment

Recommended state policy, distinguishing **device-proven access** from
the new staged experiment:

| State | Access policy for this experiment |
|---|---|
| Baseline after initial Fender wake, before any diagnostic reset stream | The existing ordered ID and META sample stages succeeded on device here. Record them once; this does not license repeating them after a reset transition. |
| Wrapper off/busy or transition incomplete | Wrapper only; no R0 access. Preserve the first failure. |
| Experimental arm, bit32 held | Wrapper plus the already observed R0+0x100/+0x104 reset words only. Skip META, BIF/MMU/SLC and other broad R0 snapshots. Do not describe skipped catalogue/SLC values as read back. |
| Load after arm | Verify all image/config bytes through the CPU coherent mappings, bounds and pointer handoffs; perform DMA publication barriers. No GPU MMIO and no META slave primitive. |
| Complete release FIFO, META now potentially running | Execute the recovered complete stream ending reset=0 and observe wrapper completion. Read the coherent event ring for alive. Avoid an automatic R0 snapshot because firmware may change domain power immediately. |
| Failure, released, or any later attempt to re-run baseline META sampling | Reject baseline/sample operations until reboot or a separately proven recovery sequence. Keep status/queues as cached or CPU-RAM-only views. |

The reset-held arm remains an experimental stopping point. A passing reset
read proves that reset gate only, not that every FIFO target executed.
CPU table verification plus release/event observation preserves useful
staging without inventing extra MMIO safety. Timeout must not trigger a
fallback dump, direct MMU write, slave probe or reset recovery sequence.

**Requested next-run evidence:** entire compact runner summary; wrapper
transition values; reset low/high raw words at arm; CPU load/config
verification; all raw event words and IRQ count after release. If alive
does not arrive, preserve that failure shape without more register probes.
No new device access was performed for this analysis.

## Captures and shared analysis

New captures are `build/gpu/round6-readback-*`; the evidence index records
their hashes and the supplied device-log hash. Existing auxiliary ARM64
loader captures were copied into that prefix so the host-store evidence is
retained together. They do not decode META instructions.

Shared Ghidra comments were added at `...6c9feb4`, `...6ca2fa0`,
`...6ca43b0` and `...6ca10ec` describing the distinction between the full
Apple sequence and the experimental reset-held state. The parent agent
will save the shared analysis; no restart was performed.
