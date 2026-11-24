"""Corpus runner: run every check over a folder of .ttpf files and report only counts and failure classes.
No file names, hashes or contents appear in the summary unless names=True (for local use).
It also tallies the open questions in docs/SPEC.md (which reading of an ambiguous field holds), so a private
sample set can settle them without publishing anything from the files."""
import os, re, struct, collections
from . import container as c

def _cls(msg: str) -> str:
    return re.sub(r"0x[0-9a-fA-F]+|\d+", "N", msg)[:100]

def check_file(data: bytes) -> dict:
    """Returns {'class': [...], 'tally': {...}} for one file."""
    r = {"fail": [], "tally": collections.Counter(), "codecs": collections.Counter(), "dxgi": collections.Counter()}
    try:
        t = c.parse(data)
    except Exception as ex:
        r["fail"].append("unparsed: " + _cls(str(ex))); return r
    for p in c.verify(t): r["fail"].append("verify: " + _cls(p))
    # round trip: replacing every chunk with itself must give the original bytes back
    try:
        for i in range(len(t.chunks)):
            if c.replace_chunk(t, i, c.chunk_payload(t, i)) != data:
                r["fail"].append("roundtrip: identity replace changed bytes"); break
    except Exception as ex:
        r["fail"].append("roundtrip: " + _cls(str(ex)))
    k = r["tally"]; n = len(t.descriptors)
    k["files"] += 1
    k["etpf_A_is_634"] += t.etpf_a == 634
    k["etpf_C_eq_16_plus_16B"] += t.etpf_c == 16 + 16 * n
    k["etpf_C_eq_16_plus_24B"] += t.etpf_c == 16 + 24 * n
    k["etpf_C_unexplained"] += t.etpf_c not in (16 + 16 * n, 16 + 24 * n)
    size_low = struct.unpack_from("<I", data, 8)[0]
    k["hdr08_eq_total_unpacked_low32"] += size_low == (t.chunks[-1].virt_end & 0xFFFFFFFF)
    k["hdr08_not_total"] += size_low != (t.chunks[-1].virt_end & 0xFFFFFFFF)
    k["entries_hi_bits_52_63_nonzero"] += sum(1 for e in t.chunks if e.hi >> 20)
    k["entries_total"] += len(t.chunks)
    k["desc_start_bit20_set"] += sum(1 for d in t.descriptors if d.raw[2] >> 20 & 1)
    k["desc_u3_nonzero"] += sum(1 for d in t.descriptors if d.raw[3])
    k["desc_total"] += n
    k["desc_mipfield_nonzero"] += sum(1 for d in t.descriptors if d.mip_field)
    k["desc_tile_mode_nonzero"] += sum(1 for d in t.descriptors if d.tile_mode)
    k["desc_u1_bits28_31_nonzero"] += sum(1 for d in t.descriptors if d.raw[1] >> 28)
    for i in range(1, len(t.chunks)): r["codecs"][c.CODECS.get(c.chunk_codec(t, i), "?")] += 1
    for d in t.descriptors: r["dxgi"][d.dxgi] += 1
    return r

def run(root: str, names: bool = False) -> dict:
    out = {"files": 0, "ok": 0, "classes": collections.Counter(), "tally": collections.Counter(),
           "codecs": collections.Counter(), "dxgi": collections.Counter(), "names": collections.defaultdict(list)}
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for n in sorted(fn):
            if not n.lower().endswith(".ttpf"): continue
            with open(os.path.join(dp, n), "rb") as fh: data = fh.read()
            r = check_file(data); out["files"] += 1
            if not r["fail"]: out["ok"] += 1
            for f in set(r["fail"]):
                out["classes"][f] += 1
                if names: out["names"][f].append(os.path.relpath(os.path.join(dp, n), root).replace(os.sep, "/"))
            for key in ("tally", "codecs", "dxgi"): out[key].update(r[key])
    return out

def render(o: dict) -> str:
    L = [f"files {o['files']}  clean {o['ok']}  with failures {o['files'] - o['ok']}"]
    if o["classes"]:
        L.append("failure classes (files affected):")
        L += [f"  {n:6}  {k}" for k, n in o["classes"].most_common()]
    if o["tally"]:
        L.append("field readings (counts over parsed files):")
        L += [f"  {k}: {v}" for k, v in sorted(o["tally"].items())]
        L.append("chunk codecs: " + ", ".join(f"{k} {v}" for k, v in sorted(o["codecs"].items())))
        L.append("dxgi formats: " + ", ".join(f"{k} {v}" for k, v in sorted(o["dxgi"].items())))
    return "\n".join(L)
