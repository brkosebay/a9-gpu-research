# Porting to older Apple PowerVR generations: a subsystem map

This page maps our A9 stack, piece by piece, onto other Apple GPUs of the PowerVR lineage: the A7, the A8/A8X,
the A9/A9X, and the A10 (T8010, "G9P"), which OrchardLinux brings up and which shares our Mesa driver. For each
subsystem it says what is **probably common across the generation**, what is **chip-specific**, and **how to
re-derive** it on your chip.

**Read this as inference.** We have analysed only the A9 (iOS 16.7.10 kernelcache, J71t) and, through the
OrchardLinux collaboration, compared notes with the A10. We have never looked at A7, A8 or A8X firmware or
kexts. When this page names the A8, it is an example of where to look, not a finding. Where we compared A9
against A10 directly, it says so.

- **Labels:** **[P]** proven on the A9 from code or data. **[V]** verified on our device. **[I]** inference.
- Start with [FIRST-TRIANGLE.md](FIRST-TRIANGLE.md) for the order of bring-up.
  [HARD-PROBLEMS.md](HARD-PROBLEMS.md) has the problems that came after.

## Before anything else: what to identify on your chip

1. **Which firmware core does the GPU run?** On the A9 it is Imagination's **META**. The firmware ships inside
   the kernelcache, in the firmware kext's `__TEXT,__const`, as a META "LDR" image, and the host loads it. On the
   A10 it is **ARM firmware on an IOP behind RTKit**, a different transport. [P/V for A9, from the A10 side for A10]
   - On an A7/A8, find out first: look for a firmware kext and an LDR-shaped blob. Our
     [extractor](tools/README.md) has a `--list` mode that prints the AGX bundle ids, and its LDR decoder checks
     the META device id.
2. **Which kext family?** On the A9 the classes are `AGXMetaFender`, `AGXMetaFirmware`, `AGXG5P`,
   `AGXFirmwareKextG5P`, plus the shared `IOGPUFamily`. The "Meta" in the class names is a strong hint that the
   META design is a family. The GART class is `AGXSharedGartTableBackingG3ThruG9`, which suggests one page-table
   format from "G3" to "G9". [P names, I scope]
3. **Which kernelcache layout?** Our tools handle the old *prelinked* layout (`__PRELINK_INFO`), which our A9 iOS
   16.7.10 kernelcache uses. We expect the older iOS releases for A7/A8 to use it too. [I]
4. **Can you compile shaders with Apple's compiler offline?**
   - The current Xcode Metal toolchain (2026-11, toolchain 27.1) compiles `applegpu_g5p` (A9) only for
     deployment target iOS 16.0 or later. [V]
   - A strings scan of one of its GPU backend libraries lists architecture names `applegpu_g4p` and
     `applegpu_g4g`, but `metal-tt` reports "No available translator" for both. [V]
   - Those two names are plausibly A8 and A8X; the mapping is [I].
   - So for an A8 you need another reference compiler: an older Xcode, or the compiler in the device's own iOS.
     [I]

## Subsystem by subsystem

### Boot and platform (SoC, loader, device tree)

| | |
|---|---|
| Probably common | The Asahi/HoolockLinux lineage: m1n1 as the loader, Apple's ADT as the hardware description, PMGR power domains, AIC interrupts. A7–A11 have no EL2, so PSCI (and therefore SMP kexec) depends on the loader build ([HARD-PROBLEMS T11](HARD-PROBLEMS.md#t11)). |
| Chip-specific | Register window addresses (A9: GPU core `0x201000000`, Fender `0x201e00000`), PMGR gate numbers, the AIC IRQ of the firmware's software interrupt (A9: 174), and DRAM/SoC performance states ([HARD-PROBLEMS P6](HARD-PROBLEMS.md#p6)). |
| Re-derive | Read the ADT: the GPU node's `reg` ranges, its `meta-sw-interrupt` tuple, its power gates. Read the kext's IOService calls (`getDeviceMemoryCount` / `…WithIndex`) for which range is which. Treat warm (kexec) and cold boots as two configurations, and diff them ([HARD-PROBLEMS T12](HARD-PROBLEMS.md#t12)). |

### Firmware load and the boot handshake

| | |
|---|---|
| Probably common (META chips) | A **Fender** power wrapper in front of the GPU core. A **reset FIFO** of register/value pairs that the Fender executes on the way to boot. The firmware loaded through mapped RAM, from an LDR. A type-0 ALIVE event. A power-policy gate in front of the first control command. Every wake from park is a **firmware reboot** ([HARD-PROBLEMS F2](HARD-PROBLEMS.md#f2)). [I] |
| Chip-specific | The FIFO contents and mode (built from per-SKU tables and ADT flags on the A9), the LDR record set, the META init field offsets (A9: PIO table at `+0x630`, policy flags at `+0x6c0`/`+0x6c8`), and the firmware's private word layout. The A10 has a different transport altogether. |
| Re-derive | In Ghidra, find the kext's reset-stream builder, the boot-and-wait routine and the LDR loader (on the A9: `programResetStream`, `bootFirmwareAndWait`, `layoutAndLoadLDR`). Extract the LDR and disassemble it ([tools](tools/README.md)). The kext's strings, and the few strings inside the LDR, are the first index. Then follow [FIRST-TRIANGLE steps 1–5](FIRST-TRIANGLE.md#step-1) in order, with one device run per stage. |

### Control and render queues (DC, TA, 3D, compute; doorbells; events)

| | |
|---|---|
| Probably common | Host↔firmware rings in shared RAM with consumer/producer indices and a barrier before the producer store. A doorbell kick preceded by a Fender pre-kick (`R1+0x14 = 7`). A firmware→host event ring with typed events. TA and 3D kicked per submission with no wait for earlier retires; 3D waiting on its own TA stamp; dependencies attached only to the TA ([HARD-PROBLEMS J1](HARD-PROBLEMS.md#j1), [J6](HARD-PROBLEMS.md#j6)). [I] |
| Chip-specific | Ring offsets, entry sizes, doorbell values (A9: `0x10` DC/TA, `0x11` 3D), the TA/3D work-record layouts, the `W+0x88` → `R0+0x470` program word ([FIRST-TRIANGLE step 8](FIRST-TRIANGLE.md#step-8)), and the firmware routine addresses. |
| Re-derive | The kext's submit path (A9: `submitDeviceControl`, `AGXChannelQueue_submitBlockInvoke`) and event drain. Capture the working OS's work records at kick and **classify every word**: our longest stall came from misreading one word ([FIRST-TRIANGLE step 9](FIRST-TRIANGLE.md#step-9)). Expect the A10's four TA-stall causes, and our `R0+0x470` contract, to be worth checking first. [I] |

### Power: park, wake, sleep

| | |
|---|---|
| Probably common | The firmware self-parks when its rings empty, with no hold-off. A host-written control word gates the park (A9: `ctrl+0x20`). The doorbell is rung at any GPC nibble, with no settle wait. The quiescence certificate equals "the firmware's own park state". There is no separate GPU system-sleep path on iOS. Registers are readable only under an accessibility check. [I] ([HARD-PROBLEMS P1–P5, P8](HARD-PROBLEMS.md#p1)) |
| Chip-specific | Which platform bit sets the park veto on your board; pstate tables and clock records; governor words; timeouts. |
| Re-derive | Find where the kext initialises the shared control object (A9: just after `AGXMetaFirmware_initializeSharedRootsAndControl`, inside an **undefined code region** that Ghidra had not made a function). Find the quiescence check (A9: `AGXMetaFender_isQuiescent`). Then disassemble the firmware's idle tail for its veto order. Measure park and wake with per-job counters, not with fps. |

### Performance states (GPU clock, SoC/memory state)

| | |
|---|---|
| Probably common | DVFS applied only by the firmware's boot sampler, i.e. across park → wake ([HARD-PROBLEMS P2](HARD-PROBLEMS.md#p2)). The GPU clock as a per-pstate PMGR record (24 MHz × mult / prediv / postdiv). A kext power table of up to 16 states. A CLPC-driven SoC/memory performance state that the bootloader leaves low. [I; the SoC state is also present on the A10, from the T8010 driver] |
| Chip-specific | Every number: pstate frequencies, voltages, the SoC state register and its values (A9: 12 vs 13), the clock ceiling of your unit. |
| Re-derive | Read the GPU `perf-states` from the ADT. Find the kext's per-pstate power-table builder (the panic string `max_pstate < AGF_MAX_NUM_PMGR_PERF_STATES` leads there). Read the PMGR SoC state at runtime before any benchmark. **Always quote the SoC memory state next to a GPU number.** |

### MMU, GART and the GPU VM

| | |
|---|---|
| Probably common | A three-level catalogue/directory/leaf table with 16 KiB pages and 40-bit VAs (seen in both the A9 and A10 trees). PTE bits with public Rogue meanings. MMU fault status decoding as in IMG's public `rgxdebug.c`. [P for A9/A10, I beyond] |
| Chip-specific | The per-range attribute table for firmware memory, the user context slot base (A9: slot 7; slots 1–6 belong to the parameter manager), the firmware GPU base. |
| Re-derive | The GART class's geometry initialiser and PTE flag encoder, and the range-attribute table that feeds the leaf flags. A VA 0 sink page in context 0 before release ([FIRST-TRIANGLE step 6](FIRST-TRIANGLE.md#step-6)). |

### Shader compiler and ISA (USC, PDS)

| | |
|---|---|
| Probably common | Mesa's PowerVR (pco) framework, the PDS program model (loaders, DOUTU/DOUTW), the per-draw PDS loading of uniforms and attributes. |
| Chip-specific | **The ISA encodings.** Apple's USC ISA differs from Imagination's public one and between generations (G5P vs G9P per our A9/A10 comparison). Register-file sizing rules ([HARD-PROBLEMS Z6](HARD-PROBLEMS.md#z6)), fp16 behaviour ([Z9](HARD-PROBLEMS.md#z9)), unroll heuristics ([Z5](HARD-PROBLEMS.md#z5)). |
| Re-derive | Compile small Metal probes with Apple's compiler for your architecture, split the per-shader code ([tools/metal](tools/README.md)), and diff against your backend for the same shader. Find heuristics with one-parameter ladders (trip count, body size). For the A8 you first need a working reference compiler (see "before anything else"). |

### PBE (render targets) and TPU (textures)

| | |
|---|---|
| Probably common | The Rogue twiddled layout. The texture unit and the PBE agree on it (POT-padded extents, mip offsets). ISP pass types and hidden-surface tags (opaque replaces the background tag, [HARD-PROBLEMS Z7](HARD-PROBLEMS.md#z7)). `PROCESS_EMPTY_TILES` semantics ([J5](HARD-PROBLEMS.md#j5)). |
| Chip-specific | The PBE word layout (A9: a twiddle bit in word 0, no row pitch in word 1), the supported texture formats (A9: ETC2/EAC, ASTC LDR, PVRTC, **no BC**), MSAA sample patterns. |
| Re-derive | iOS render captures, reproduced bit for bit in a host unit test before you flip a default ([Z1](HARD-PROBLEMS.md#z1)). For formats, read the userspace Metal driver's per-pixel-format table: on the A9, `AGX::G5::TextureFormatTable::chooseTextureFormatOBJC` in AGXMetalA9. Check it against format codes from captures ([Z4](HARD-PROBLEMS.md#z4)). |

### Zink and GL

| | |
|---|---|
| Probably common | Everything in Mesa above the driver: the one-frame swap throttle ([J3](HARD-PROBLEMS.md#j3)), over-broad Zink barriers ([J6](HARD-PROBLEMS.md#j6)), lost-batch hangs ([Z3](HARD-PROBLEMS.md#z3)), CPU mip/blit fallbacks ([Z2](HARD-PROBLEMS.md#z2)), slab parents ([M3](HARD-PROBLEMS.md#m3)), the loader's kmsro fallback for a renamed DRM driver ([M5](HARD-PROBLEMS.md#m5)), and `pvr_stage_mask()` changing under a rebase ([J7](HARD-PROBLEMS.md#j7)). generation-wide. |
| Chip-specific | Which formats need transcoding, MSAA sampled counts, arena and BO limits. |
| Re-derive | Measure GPU ms/frame and GPU busy % per glmark2 scene ([tools/census](tools/README.md)) in the compositor's real environment, and fix whatever leaves the GPU idle first. |

### Video decode (VXD)

| | |
|---|---|
| Probably common | Imagination's VXD family behind a V4L2 stateless driver. The A10 has a VXD of the same family. The DPB-slot-identity bug ([HARD-PROBLEMS V1](HARD-PROBLEMS.md#v1)) applies to any stateless driver that keys hardware state by userspace DPB index. |
| Chip-specific | Core ID values, ring geometry, the mailbox and boot messages, supported profiles. |
| Re-derive | The vendor driver's core-discovery code for the ID gates. A read-only probe before any firmware boot, and hardware-decode checks that count interrupts ([V2](HARD-PROBLEMS.md#v2), [V3](HARD-PROBLEMS.md#v3)). |

## Using these notes with an AI agent

What to feed it first:
1. This page, [FIRST-TRIANGLE.md](FIRST-TRIANGLE.md) and [HARD-PROBLEMS.md](HARD-PROBLEMS.md): the short versions.
2. [agx-g5p-bringup](docs/gpu/agx-g5p-bringup.md) for register-level detail of steps 1–6, and
   [STATUS](docs/gpu/STATUS.md) for the state of the A9 driver.
3. The step docs linked from FIRST-TRIANGLE, only when the agent works on that step. They are long lab notebooks
   and will flood a context window.
4. [tools/README.md](tools/README.md), so the agent can extract its own kexts and firmware rather than guess.

The rules that saved us the most time:
- **Apple first.** For any hardware behaviour (registers, pass types, reset, power), read it in the kext or the
  firmware first (we use a shared Ghidra project with our renames). If static analysis doesn't settle it within
  about an hour, get one targeted capture from the working OS, read-only. **Never fly variant after variant of a
  guess.**
- **Diff against the last known-good build** before you reverse engineer a regression: patches, dmesg, the words
  written. RE only explains the diff ([HARD-PROBLEMS F1](HARD-PROBLEMS.md#f1), [T1](HARD-PROBLEMS.md#t1)).
- **One factor per hypothesis per boot,** with the stop rule written down before the flight ("if X doesn't
  move, Y is not the cause"). Our TA stall was broken by a one-factor flip, and the earlier multi-factor rounds
  mostly measured symptoms.
- **Check captured fixtures for truncation and zero-fill.** Both of our longest stalls were bytes our own
  capture or fixture tooling had dropped ([FIRST-TRIANGLE steps 7–8](FIRST-TRIANGLE.md#step-7)).
- **Measure GPU ms/frame and GPU busy %,** not just fps. Count firmware time from the firmware's own stamps in the
  work records, and state the SoC memory state with every number.
- **Never read GPU registers after a job retires** or near a park. Use RAM stamps and events. A stalled read takes
  the whole SoC down ([HARD-PROBLEMS P5](HARD-PROBLEMS.md#p5)).
- **Name every refusal.** Every silent `-EBUSY`/`-EIO` cost us flights ([P7](HARD-PROBLEMS.md#p7),
  [P10](HARD-PROBLEMS.md#p10)).
- **Cold equals warm.** Any behavioural difference between a cold boot and a kexec boot is a bug, so test both
  ([T12](HARD-PROBLEMS.md#t12)).
- **Corrections are part of the record.** When a later doc corrects an earlier one, carry the correction and
  the label ([P]/[V]/[I]) forward, and don't let a plausible register name stand in for a census.
