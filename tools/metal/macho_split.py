#!/usr/bin/env python3
"""Split Apple GPU binaries (metal-tt output, MTLBinaryArchive) into shaders.

Scans any file for nested 64-bit GPU Mach-O objects (magic 0xfeedfacf,
cputype 0x01000013 = CPU_TYPE_APPLE_GPU|ABI64), and for each one records
the containing outer section (stage), the function name found in its
__GPU_LD_MD/__GPU_METADATA strings, and its __TEXT,__text bytes (USC code).

Usage: python3 -I macho_split.py FILE [OUTDIR]
Writes OUTDIR/NNN-stage-name.text.bin and OUTDIR/index.tsv
(default OUTDIR: FILE + ".split"). Standard library only.
"""
import os
import re
import struct
import sys

MH_MAGIC_64 = 0xFEEDFACF
CPU_APPLE_GPU = 0x01000013
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2


def parse_macho(d, base):
    """Return (header dict, [sections], symbols) for the Mach-O at d[base:]."""
    magic, cputype, subtype, ftype, ncmds, sizeofcmds = struct.unpack_from(
        "<IIIIII", d, base)
    if magic != MH_MAGIC_64:
        return None
    hdr = dict(cputype=cputype, subtype=subtype, filetype=ftype, ncmds=ncmds)
    sects, syms = [], []
    p = base + 32
    for _ in range(ncmds):
        if p + 8 > len(d):
            break
        cmd, sz = struct.unpack_from("<II", d, p)
        if sz < 8:
            break
        if cmd == LC_SEGMENT_64:
            nsect = struct.unpack_from("<I", d, p + 64)[0]
            for s in range(nsect):
                q = p + 72 + s * 80
                sect = d[q:q + 16].rstrip(b"\0").decode("latin1")
                seg = d[q + 16:q + 32].rstrip(b"\0").decode("latin1")
                addr, size, off = struct.unpack_from("<QQI", d, q + 32)
                sects.append(dict(seg=seg, sect=sect, addr=addr, size=size,
                                  off=off))
        elif cmd == LC_SYMTAB:
            symoff, nsyms, stroff, strsize = struct.unpack_from(
                "<IIII", d, p + 8)
            for i in range(nsyms):
                e = base + symoff + i * 16
                if e + 16 > len(d):
                    break
                strx, ntype, nsect, desc, value = struct.unpack_from(
                    "<IBBHQ", d, e)
                s0 = base + stroff + strx
                s1 = d.find(b"\0", s0)
                syms.append((d[s0:s1].decode("latin1"), value))
        p += sz
    return hdr, sects, syms


def outer_sections(d):
    r = parse_macho(d, 0)
    if not r or r[0]["cputype"] != CPU_APPLE_GPU:
        return []
    return [s for s in r[1] if s["seg"] == "__TEXT"]


IDENT = re.compile(rb"[A-Za-z_][A-Za-z0-9_.]{2,}")
STAGES = ("vertex", "fragment", "compute", "kernel", "tile", "object",
          "mesh", "visible", "intersection")


def guess_name(blob):
    names = [m.group().decode() for m in IDENT.finditer(blob)]
    # __GPU_LD_MD appends <entry-name>\0<stage>. Earlier strings may name
    # generated varying producers (e.g. generated\0bDv4_f). Do not mistake
    # those for the entry point when a fragment has stage_in arguments.
    for i in range(len(names) - 1, 0, -1):
        if names[i] in STAGES and not names[i - 1].startswith(("_agc", "agc.", "__")):
            return names[i - 1]
    for n in names:
        if n.startswith(("_agc", "agc.", "__")) or n in STAGES:
            continue
        return n
    return "?"


def gpu_slices(d):
    """(offset, size) of each GPU Mach-O: the whole file, or the GPU slices
    of a fat file. MTLBinaryArchive serializes as a fat file with magic
    0xCBFEBABE (standard 32-bit fat_arch layout) holding AIR + GPU slices."""
    magic = struct.unpack_from(">I", d, 0)[0]
    if magic not in (0xCAFEBABE, 0xCBFEBABE, 0xCAFEBABF):
        return [(0, len(d))]
    out = []
    for i in range(struct.unpack_from(">I", d, 4)[0]):
        if magic != 0xCAFEBABF:
            cpu, _, off, size, _ = struct.unpack_from(">IIIII", d, 8 + i * 20)
        else:
            cpu, _, off, size, _, _ = struct.unpack_from(">IIQQII", d, 8 + i * 32)
        if cpu == CPU_APPLE_GPU:
            out.append((off, size))
    return out


def nested_objects(d):
    """Yield (base, stage) for every per-shader object, slice by slice."""
    for off, size in gpu_slices(d):
        outer = [dict(s, off=s["off"] + off) for s in outer_sections(d[off:off + size])]
        pat = re.finditer(rb"\xcf\xfa\xed\xfe\x13\x00\x00\x01", d[off:off + size])
        for m in pat:
            base = off + m.start()
            if base == off:
                continue
            stage = "?"
            for s in outer:
                if s["off"] <= base < s["off"] + s["size"]:
                    stage = s["sect"].strip("_")
            yield base, stage


def split(path, outdir):
    d = open(path, "rb").read()
    os.makedirs(outdir, exist_ok=True)
    # Repeat compiles can reorder objects. Remove this tool's generated shader
    # files so old index/name combinations cannot inflate corpus counts.
    for filename in os.listdir(outdir):
        if re.fullmatch(r'\d+-[A-Za-z?]+-[A-Za-z0-9_.?]+\.text\.bin', filename):
            os.unlink(os.path.join(outdir, filename))
    rows = []
    for idx, (base, stage) in enumerate(nested_objects(d)):
        r = parse_macho(d, base)
        if not r:
            continue
        hdr, sects, syms = r
        text = next((s for s in sects if s["sect"] == "__text"), None)
        md = b"".join(d[base + s["off"]:base + s["off"] + s["size"]]
                      for s in sects if s["seg"].startswith("__GPU_"))
        name = guess_name(md)
        code = d[base + text["off"]:base + text["off"] + text["size"]] if text else b""
        fn = "%03d-%s-%s.text.bin" % (idx, stage, name)
        with open(os.path.join(outdir, fn), "wb") as f:
            f.write(code)
        rows.append((idx, hex(base), stage, name, "0x%x" % hdr["subtype"],
                     len(code), ",".join("%s.%s=%d" % (s["seg"], s["sect"], s["size"])
                                         for s in sects),
                     ",".join("%s@%x" % sv for sv in syms), fn))
    with open(os.path.join(outdir, "index.tsv"), "w") as f:
        f.write("idx\toffset\tstage\tname\tsubtype\ttext_len\tsections\tsymbols\tfile\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")
    return rows


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else path + ".split"
    rows = split(path, outdir)
    for r in rows:
        print("%3d %-9s %-16s text=%4d  %s" % (r[0], r[2], r[3], r[5], r[8]))
    print("%d shaders -> %s" % (len(rows), outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
