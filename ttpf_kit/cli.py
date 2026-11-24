import argparse, json, sys, zlib
from . import container as c, patch as p

def _read(path): return open(path, "rb").read()

def main(argv=None):
    ap = argparse.ArgumentParser(prog="ttpf-kit", description="Inspect, verify, patch .ttpf containers.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("info", "verify"): sub.add_parser(n).add_argument("file")
    x = sub.add_parser("extract"); x.add_argument("file"); x.add_argument("chunk", type=int); x.add_argument("out")
    r = sub.add_parser("replace"); r.add_argument("file"); r.add_argument("chunk", type=int)
    r.add_argument("payload"); r.add_argument("out"); r.add_argument("--zlib", action="store_true", help="compress payload")
    d = sub.add_parser("diff"); d.add_argument("old"); d.add_argument("new"); d.add_argument("patch")
    a = sub.add_parser("apply"); a.add_argument("file"); a.add_argument("patch"); a.add_argument("out")
    o = ap.parse_args(argv)
    try:
        if o.cmd == "info":
            t = c.parse(_read(o.file))
            print(f"chunks {len(t.chunks)}  descriptors {len(t.descriptors)}  etpf A={t.etpf_a} C={t.etpf_c:#x}")
            for i, (s, e) in enumerate(c.chunk_spans(t)):
                print(f"chunk {i:4} {c.CODECS.get(c.chunk_codec(t, i), '?'):5} file {s:#x}-{e:#x} virt_end {t.chunks[i].virt_end:#x}")
            for k, ds in enumerate(t.descriptors):
                print(f"tex {k:4} {ds.width}x{ds.height} dxgi {ds.dxgi} fmt {ds.fmt} mips {ds.mips} page {ds.page:#x}")
        elif o.cmd == "verify":
            errs = c.verify(c.parse(_read(o.file)))
            for e in errs: print("ERROR", e)
            print("ok" if not errs else f"{len(errs)} problem(s)")
            return 1 if errs else 0
        elif o.cmd == "extract":
            t = c.parse(_read(o.file)); b = c.chunk_payload(t, o.chunk)
            if c.chunk_codec(t, o.chunk) == 8: b = zlib.decompressobj().decompress(b)
            open(o.out, "wb").write(b)
        elif o.cmd == "replace":
            t = c.parse(_read(o.file)); b = _read(o.payload)
            if o.zlib: b = zlib.compress(b, 9)
            open(o.out, "wb").write(c.replace_chunk(t, o.chunk, b))
        elif o.cmd == "diff":
            json.dump(p.make_patch(_read(o.old), _read(o.new)), open(o.patch, "w"), indent=1)
        elif o.cmd == "apply":
            open(o.out, "wb").write(p.apply_patch(_read(o.file), json.load(open(o.patch))))
    except (ValueError, OSError, zlib.error, IndexError) as ex:
        print("error:", ex, file=sys.stderr); return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
