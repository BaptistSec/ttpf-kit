import argparse, sys, zlib
from . import container as c, patch as p

EXIT_ERROR, EXIT_CONFLICT, EXIT_VERIFY = 2, 3, 1

def _read(path):
    with open(path, "rb") as fh: return fh.read()

def main(argv=None):
    ap = argparse.ArgumentParser(prog="ttpf-kit", description="Inspect, verify, patch and merge .ttpf containers. Outputs are never written in place unless you ask; writes are atomic.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n, h in (("info", "list chunks and textures"), ("verify", "structural checks; exit 1 if problems")):
        sub.add_parser(n, help=h).add_argument("file")
    x = sub.add_parser("extract", help="write one chunk (zlib chunks are decompressed)")
    x.add_argument("file"); x.add_argument("chunk", type=int); x.add_argument("out")
    r = sub.add_parser("replace", help="replace one chunk payload")
    r.add_argument("file"); r.add_argument("chunk", type=int); r.add_argument("payload"); r.add_argument("out")
    r.add_argument("--zlib", action="store_true", help="compress the payload with zlib first")
    d = sub.add_parser("diff", help="write a deterministic, reversible patch")
    d.add_argument("old"); d.add_argument("new"); d.add_argument("patch")
    a = sub.add_parser("apply", help="apply a patch; checks hashes before and after")
    a.add_argument("file"); a.add_argument("patch"); a.add_argument("out")
    a.add_argument("--reverse", action="store_true", help="undo the patch instead")
    a.add_argument("--in-place", action="store_true", help="overwrite FILE (keeps FILE.bak); OUT is ignored")
    m = sub.add_parser("merge", help="3-way merge of two edited copies of a base; exit 3 on conflict")
    m.add_argument("base"); m.add_argument("left"); m.add_argument("right"); m.add_argument("out")
    o = ap.parse_args(argv)
    try:
        if o.cmd == "info":
            t = c.parse(_read(o.file))
            print(f"chunks {len(t.chunks)}  textures {len(t.descriptors)}  etpf word A={t.etpf_a} C={t.etpf_c:#x} (meaning of C: unknown)")
            for i, (s, e) in enumerate(c.chunk_spans(t)):
                print(f"chunk {i:4}  {c.CODECS.get(c.chunk_codec(t, i), '?'):5} file {s:#x}-{e:#x}  unpacked end {t.chunks[i].virt_end:#x}")
            for k, ds in enumerate(t.descriptors):
                print(f"tex {k:5}  {ds.width}x{ds.height}  dxgi {ds.dxgi}  tile {ds.tile_mode}  slices {ds.array_size}  start {ds.page * 0x1000:#x}")
        elif o.cmd == "verify":
            errs = c.verify(c.parse(_read(o.file)))
            for e in errs: print("problem:", e)
            print("ok" if not errs else f"{len(errs)} problem(s)")
            return EXIT_VERIFY if errs else 0
        elif o.cmd == "extract":
            t = c.parse(_read(o.file)); b = c.chunk_payload(t, o.chunk)
            if c.chunk_codec(t, o.chunk) == 8: b = zlib.decompressobj().decompress(b)
            p.write_atomic(o.out, b)
        elif o.cmd == "replace":
            t = c.parse(_read(o.file)); b = _read(o.payload)
            if o.zlib: b = zlib.compress(b, 9)
            p.write_atomic(o.out, c.replace_chunk(t, o.chunk, b))
        elif o.cmd == "diff":
            p.write_atomic(o.patch, p.dump_patch(p.make_patch(_read(o.old), _read(o.new))).encode())
        elif o.cmd == "apply":
            patch = p.load_patch(_read(o.patch).decode("utf-8"))
            if o.reverse: patch = p.invert(patch)
            res = p.apply_patch(_read(o.file), patch)
            if o.in_place: p.write_atomic(o.file, res, backup=True)
            else: p.write_atomic(o.out, res)
        elif o.cmd == "merge":
            p.write_atomic(o.out, p.merge(_read(o.base), _read(o.left), _read(o.right)))
    except p.Conflict as ex:
        print("conflict:", ex, file=sys.stderr); return EXIT_CONFLICT
    except (ValueError, OSError, zlib.error, IndexError, KeyError, UnicodeDecodeError) as ex:
        print("error:", ex, file=sys.stderr); return EXIT_ERROR
    except Exception as ex:   # struct.error and friends on malformed input
        print("error: malformed input:", ex, file=sys.stderr); return EXIT_ERROR
    return 0

if __name__ == "__main__":
    sys.exit(main())
