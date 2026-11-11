#!/usr/bin/env python3
"""Split the AGX GPU kexts and their META firmware (LDR) out of a prelinked kernelcache.

usage: extract-kext-firmware.py KERNELCACHE OUTDIR [--gpu G5P]

KERNELCACHE is the decompressed arm64 Mach-O kernelcache (the old *prelinked*
layout with __PRELINK_INFO, as on iOS 9-16 for A7-A10 devices; MH_FILESET
kernelcaches are refused). --gpu picks the kext family suffix: the A9 uses
com.apple.AGXG5P / com.apple.AGXFirmwareKextG5P. Other chips use other
suffixes (list the CFBundleIdentifiers with --list first; we have only run
this on the A9, iOS 16.7.10).

Output (keep it out of any public repository: it is Apple code):
  <kext>.macho          analysis copy of each kext, VAs preserved, file offsets repacked
  <kext>.<seg>.<sect>.bin, manifest.json, strings.tsv (kext __cstring + LDR strings)
  agx-<gpu>-c0.ldr      the firmware carried in the firmware kext's __TEXT,__const
  meta-ldr.json, meta-load-*.bin   the decoded IMG META LDR records

No third-party Python modules. Apple XML's ID/IDREF and hexadecimal integers
are deliberately handled rather than silently losing prelink metadata.
Repacked images are for analysis, not loadable/re-signed kext bundles.
"""
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
import struct
import xml.etree.ElementTree as ET


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(data, offset, size):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"out-of-bounds slice {offset:#x}+{size:#x}")
    return data[offset:offset + size]


def cstr(data):
    return data.split(b"\0", 1)[0].decode("ascii")


def macho(data, offset=0):
    magic, cpu, _, kind, count, size, _, _ = struct.unpack_from("<8I", data, offset)
    if magic != 0xFEEDFACF or cpu != 0x100000C or kind == 0xC:
        raise ValueError("expected prelinked arm64 Mach-O, not MH_FILESET")
    checked(data, offset + 32, size)
    commands, segments = [], []
    pos = offset + 32
    for _ in range(count):
        cmd, length = struct.unpack_from("<II", data, pos)
        if length < 8 or pos + length > offset + 32 + size:
            raise ValueError("invalid Mach-O load command")
        commands.append((cmd, pos - offset, length))
        if cmd == 0x19:
            name, va, vs, fo, fs, _, _, ns, _ = struct.unpack_from("<16sQQQQIIII", data, pos + 8)
            if length != 72 + ns * 80:
                raise ValueError("invalid LC_SEGMENT_64")
            seg = dict(name=cstr(name), va=va, vmsize=vs, fileoff=fo, filesize=fs,
                       command_offset=pos - offset, sections=[])
            for i in range(ns):
                sp = pos + 72 + i * 80
                sn, sg, addr, sz, sf, _, rel, nr, flags = struct.unpack_from("<16s16sQQIIIII", data, sp)
                seg["sections"].append(dict(name=cstr(sn), segment=cstr(sg), va=addr,
                                             size=sz, fileoff=sf, flags=flags,
                                             reloff=rel, nreloc=nr, command_offset=sp - offset))
            segments.append(seg)
        pos += length
    if pos != offset + 32 + size:
        raise ValueError("load command length mismatch")
    return dict(header_size=32 + size, commands=commands, segments=segments)


def va_offset(image, va, length):
    for seg in image["segments"]:
        delta = va - seg["va"]
        if delta >= 0 and delta + length <= seg["filesize"]:
            return seg["fileoff"] + delta
    raise ValueError(f"VA not file-backed: {va:#x}+{length:#x}")


def apple_xml(data):
    root = ET.fromstring(data)
    ids = {e.attrib["ID"]: e for e in root.iter() if "ID" in e.attrib}

    def parse(e, active=frozenset()):
        if "IDREF" in e.attrib:
            ref = e.attrib["IDREF"]
            if ref in active:
                raise ValueError("cyclic prelink IDREF")
            return parse(ids[ref], active | {ref})
        if e.tag == "dict":
            q = list(e)
            if len(q) % 2 or any(q[i].tag != "key" for i in range(0, len(q), 2)):
                raise ValueError("invalid plist dictionary")
            return {q[i].text: parse(q[i + 1], active) for i in range(0, len(q), 2)}
        if e.tag in ("array", "plist"):
            values = [parse(v, active) for v in e]
            return values[0] if e.tag == "plist" else values
        if e.tag == "integer":
            return int(e.text or "0", 0)
        if e.tag in ("true", "false"):
            return e.tag == "true"
        if e.tag == "data":
            return {"base64": base64.b64encode(base64.b64decode(e.text or "")).decode()}
        if e.tag == "string":
            return e.text or ""
        raise ValueError(f"unsupported prelink XML element: {e.tag}")
    return parse(root)


def extract_kext(kc, kernel, entry, out):
    va = entry["_PrelinkExecutableLoadAddr"]
    offset = va_offset(kernel, va, 32)
    image = macho(kc, offset)
    result = bytearray(checked(kc, offset, image["header_size"]))
    sections = []
    for seg in image["segments"]:
        if not seg["filesize"]:
            struct.pack_into("<QQ", result, seg["command_offset"] + 40, 0, 0)
            continue
        source = va_offset(kernel, seg["va"], seg["filesize"])
        if seg["va"] == va:
            dest = 0
            result.extend(checked(kc, source + len(result), seg["filesize"] - len(result)))
        else:
            dest = (len(result) + 15) & ~15
            result.extend(b"\0" * (dest - len(result)))
            result.extend(checked(kc, source, seg["filesize"]))
        struct.pack_into("<Q", result, seg["command_offset"] + 40, dest)
        seg.update(kernelcache_offset=source, extracted_offset=dest,
                   sha256=sha(checked(kc, source, seg["filesize"])))
        for sec in seg["sections"]:
            zerofill = (sec["flags"] & 0xFF) in (1, 0xC, 0x12)
            sf = 0 if zerofill else dest + sec["va"] - seg["va"]
            struct.pack_into("<I", result, sec["command_offset"] + 48, sf)
            if sec["nreloc"]:
                raise ValueError("unexpected relocations in linked kext")
            if not zerofill:
                so = va_offset(kernel, sec["va"], sec["size"])
                blob = checked(kc, so, sec["size"])
                name = f"{entry['CFBundleExecutable']}.{seg['name']}.{sec['name']}.bin"
                (out / name).write_bytes(blob)
                sec.update(kernelcache_offset=so, extracted_offset=sf, sha256=sha(blob), path=name)
                sections.append(sec)
    # These stripped images contain no symbol/linkedit payload. Refuse other inputs.
    for cmd, pos, _ in image["commands"]:
        if cmd == 2 and any(struct.unpack_from("<4I", result, pos + 8)):
            raise ValueError("nonempty symbol table requires linkedit reconstruction")
    name = entry["CFBundleExecutable"] + ".macho"
    (out / name).write_bytes(result)
    # Verify all non-header section bytes survived offset rewriting exactly.
    repacked = macho(result)
    for seg in repacked["segments"]:
        for sec in seg["sections"]:
            if (sec["flags"] & 0xFF) not in (1, 0xC, 0x12):
                assert checked(result, sec["fileoff"], sec["size"]) == checked(
                    kc, va_offset(kernel, sec["va"], sec["size"]), sec["size"])
    return dict(path=name, sha256=sha(result), header_kernelcache_offset=offset,
                prelink=entry, segments=image["segments"], sections=sections)


def decode_ldr(blob, out):
    """Decode IMG META LDR records; do not assume the modern FW address map."""
    dev, code, data, control, crc = struct.unpack_from("<IIIHH", blob)
    if dev != 0x01AA5500:
        raise ValueError("not the expected META LDR image")
    checked(blob, code, 1)
    records, seen, loads = [], set(), []
    pos = data

    def l2(offset):
        tag, size = struct.unpack("<HH", checked(blob, offset, 4))
        if size < 6:
            raise ValueError("invalid LDR L2 size")
        raw = checked(blob, offset, size)
        return dict(offset=offset, tag=tag, length=size,
                    payload_offset=offset + 4, payload_size=size - 6,
                    checksum=raw[-2:].hex()), raw[4:-2]

    while pos != 0xFFFFFFFF:
        if pos in seen:
            raise ValueError("cyclic LDR record list")
        seen.add(pos)
        cmd, size, nxt = struct.unpack("<HHI", checked(blob, pos, 8))
        if size < 12 or size % 4:
            raise ValueError("invalid LDR L1 size")
        raw = checked(blob, pos, size)
        words = list(struct.unpack("<" + "I" * ((size - 12) // 4), raw[8:-4]))
        rec = dict(offset=pos, command=cmd, length=size, next=nxt,
                   words=words, checksum=raw[-4:].hex())
        if cmd & 0x10:
            rec["kind"] = "comment"
            rec["l2"], payload = l2(words[0])
            rec["text"] = payload.rstrip(b"\0").decode("ascii", errors="replace")
        elif cmd == 0:
            rec["kind"] = "load"
            addr, ptr = words
            rec["destination"] = addr
            rec["l2"], payload = l2(ptr)
            name = f"meta-load-{pos:05x}-{addr:08x}.bin"
            (out / name).write_bytes(payload)
            rec.update(path=name, size=len(payload), sha256=sha(payload))
            loads.append((addr, addr + len(payload)))
        elif cmd == 4:
            rec.update(kind="zero", destination=words[0], size=words[1])
            rec["l2"], _ = l2(words[2])
        elif cmd in (3, 5):
            rec["kind"] = "start_threads" if cmd == 3 else "config"
            rec["l2"], payload = l2(words[0])
            vals = list(struct.unpack("<" + "I" * (len(payload) // 4), payload))
            rec["payload_words"] = vals
            if cmd == 5:
                if len(vals) % 3 or any(vals[i] != 2 for i in range(0, len(vals), 3)):
                    raise ValueError("unexpected config operation")
                rec["writes"] = [dict(address=vals[i + 1], value=vals[i + 2])
                                 for i in range(0, len(vals), 3)]
            else:
                if len(vals) % 4:
                    raise ValueError("unexpected StartThreads layout")
                # Field semantics follow META loader convention; retained raw too.
                rec["threads_inferred"] = [dict(thread=vals[i], sp=vals[i + 1],
                                                pc=vals[i + 2], catch=vals[i + 3])
                                           for i in range(0, len(vals), 4)]
        else:
            raise ValueError(f"unsupported META LDR command {cmd:#x}")
        records.append(rec)
        pos = nxt
    merged = []
    for start, end in sorted(loads):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    result = dict(format="IMG META LDR", dev_id=dev, secondary_loader_offset=code,
                  command_stream_offset=data, control=control, crc=crc,
                  checksum_validation="not implemented; byte SHA256 recorded",
                  initialized_ranges=merged, records=records)
    (out / "meta-ldr.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kernelcache", type=Path)
    ap.add_argument("output", type=Path, nargs="?")
    ap.add_argument("--gpu", default="G5P", help="AGX kext suffix (A9: G5P)")
    ap.add_argument("--list", action="store_true", help="list prelinked bundle ids that look GPU-related (AGX, GPU, IOAccel, SGX, PowerVR, IMG, Firmware) and exit")
    args = ap.parse_args()
    kc = args.kernelcache.read_bytes()
    kernel = macho(kc)
    prelink = next(s for s in kernel["segments"] if s["name"] == "__PRELINK_INFO")
    xml = checked(kc, prelink["fileoff"], prelink["filesize"]).split(b"\0", 1)[0]
    info = apple_xml(xml)
    if args.list or args.output is None:
        for e in info["_PrelinkInfoDictionary"]:
            b = e.get("CFBundleIdentifier", "")
            if re.search(r"(?i)AGX|GPU|IOAccel|SGX|PowerVR|IMG|Firmware", b):
                print(b)
        return
    args.output = args.output.resolve()
    if (Path(__file__).resolve().parents[1] / ".git").exists() or \
            any((p / ".git").exists() for p in args.output.parents):
        print("warning: OUTDIR is inside a git checkout; never commit the extracted Apple code")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = dict(schema=1, kernelcache=args.kernelcache.name,
                    kernelcache_sha256=sha(kc), kernelcache_size=len(kc),
                    prelink_info_offset=prelink["fileoff"], kexts={})
    fw_bundle = f"com.apple.AGXFirmwareKext{args.gpu}"
    for bundle in (f"com.apple.AGX{args.gpu}", fw_bundle, "com.apple.iokit.IOGPUFamily"):
        matches = [e for e in info["_PrelinkInfoDictionary"] if e.get("CFBundleIdentifier") == bundle]
        if len(matches) != 1:
            raise ValueError(f"expected exactly one {bundle} (try --list)")
        manifest["kexts"][bundle] = extract_kext(kc, kernel, matches[0], args.output)
    carrier = manifest["kexts"][fw_bundle]
    const = next(s for s in carrier["sections"] if s["segment"] == "__TEXT" and s["name"] == "__const")
    blob = (args.output / const["path"]).read_bytes()
    # On the A9 (iOS 16.7.10) the firmware kext's requestFirmwareBinary returns exactly this
    # section's pointer and length; check the same on another chip before trusting it.
    ldr_name = f"agx-{args.gpu.lower()}-c0.ldr"
    (args.output / ldr_name).write_bytes(blob)
    ldr = decode_ldr(blob, args.output)
    manifest["firmware"] = dict(path=ldr_name, size=len(blob), sha256=sha(blob),
                                va=const["va"], kernelcache_offset=const["kernelcache_offset"],
                                format=ldr["format"], metadata="meta-ldr.json")
    # Detect the misleading similarly named section without extracting unrelated
    # firmware. This proves ownership from every kext's own segment commands.
    owners, skipped = [], []
    for entry in info["_PrelinkInfoDictionary"]:
        va = entry.get("_PrelinkExecutableLoadAddr")
        if va is None:
            continue
        try:
            image = macho(kc, va_offset(kernel, va, 32))
        except ValueError as error:
            skipped.append(dict(bundle=entry["CFBundleIdentifier"], reason=str(error)))
            continue
        for seg in image["segments"]:
            for sec in seg["sections"]:
                if sec["name"] == "fwFirmwareImage":
                    owners.append(dict(bundle=entry["CFBundleIdentifier"], va=sec["va"], size=sec["size"]))
    manifest["fwFirmwareImage_owners"] = owners
    manifest["ownership_scan_skipped_pseudokexts"] = skipped
    lines = []
    for bundle, kext in manifest["kexts"].items():
        for section in kext["sections"]:
            if section["name"] == "__cstring":
                raw = (args.output / section["path"]).read_bytes()
                for match in re.finditer(rb"[\x20-\x7e]{4,}", raw):
                    lines.append(f"{bundle}\t{section['va'] + match.start():#x}\t{match.group().decode()}")
    for match in re.finditer(rb"[\x20-\x7e]{8,}", blob):
        lines.append(f"META-LDR\t{match.start():#x}\t{match.group().decode()}")
    (args.output / "strings.tsv").write_text("\n".join(lines) + "\n")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for bundle, entry in manifest["kexts"].items():
        print(f"{bundle}: {entry['path']} (header KC +{entry['header_kernelcache_offset']:#x})")
    print(f"META LDR: {len(blob)} bytes, {len(ldr['records'])} records, SHA256 {sha(blob)}")


if __name__ == "__main__":
    main()
