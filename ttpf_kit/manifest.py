"""Build-to-build comparison: a manifest records every .ttpf under a folder (file sha256, size, and per-chunk
sha256 plus texture descriptors). Comparing two manifests reports added, removed, changed and unchanged
files and, for changed files, which chunks and textures differ. Manifests hold hashes only, never game data."""
import hashlib, json, os
from . import container as c

FORMAT = "ttpf-manifest/1"

def _sha(b): return hashlib.sha256(b).hexdigest()

def file_entry(data: bytes) -> dict:
    e = {"sha256": _sha(data), "size": len(data)}
    try:
        t = c.parse(data)
        e["chunks"] = [_sha(c.chunk_payload(t, i)) for i in range(len(t.chunks))]
        e["textures"] = [[d.width, d.height, d.dxgi, d.tile_mode, d.array_size, d.page] for d in t.descriptors]
        e["problems"] = len(c.verify(t))
    except (ValueError, Exception) as ex:   # malformed file: keep the hash, record why
        e["unparsed"] = str(ex)[:120]
    return e

def build(root: str) -> dict:
    files = {}
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for n in sorted(fn):
            if n.lower().endswith(".ttpf"):
                path = os.path.join(dp, n)
                rel = os.path.relpath(path, root).replace(os.sep, "/")   # same keys on Windows and Linux
                with open(path, "rb") as fh: files[rel] = file_entry(fh.read())
    return {"format": FORMAT, "files": files}

def dumps(m: dict) -> str:
    return json.dumps(m, sort_keys=True, indent=1) + "\n"

def loads(text: str) -> dict:
    try: m = json.loads(text)
    except json.JSONDecodeError as ex: raise ValueError(f"manifest is not valid JSON: {ex}")
    if not isinstance(m, dict) or m.get("format") != FORMAT or not isinstance(m.get("files"), dict):
        raise ValueError(f"not a {FORMAT} manifest")
    return m

def compare(old: dict, new: dict) -> dict:
    a, b = old["files"], new["files"]
    out = {"added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys()),
           "unchanged": [], "changed": {}}
    for k in sorted(a.keys() & b.keys()):
        x, y = a[k], b[k]
        if x["sha256"] == y["sha256"]:
            out["unchanged"].append(k); continue
        d = {}
        if "chunks" in x and "chunks" in y:
            if len(x["chunks"]) != len(y["chunks"]):
                d["chunk_count"] = [len(x["chunks"]), len(y["chunks"])]
            d["chunks_changed"] = [i for i, (p, q) in enumerate(zip(x["chunks"], y["chunks"])) if p != q]
            if x["textures"] != y["textures"]:
                n = min(len(x["textures"]), len(y["textures"]))
                d["textures_changed"] = [i for i in range(n) if x["textures"][i] != y["textures"][i]]
                if len(x["textures"]) != len(y["textures"]):
                    d["texture_count"] = [len(x["textures"]), len(y["textures"])]
        else:
            d["note"] = "one side could not be parsed; whole-file hash differs"
        out["changed"][k] = d
    return out

def render(r: dict) -> str:
    lines = [f"added {len(r['added'])}  removed {len(r['removed'])}  changed {len(r['changed'])}  unchanged {len(r['unchanged'])}"]
    lines += [f"+ {k}" for k in r["added"]] + [f"- {k}" for k in r["removed"]]
    for k, d in r["changed"].items():
        bits = []
        if d.get("chunks_changed"): bits.append(f"{len(d['chunks_changed'])} chunk(s): {d['chunks_changed'][:8]}{'...' if len(d['chunks_changed']) > 8 else ''}")
        if d.get("textures_changed"): bits.append(f"{len(d['textures_changed'])} texture descriptor(s)")
        if "chunk_count" in d: bits.append(f"chunk count {d['chunk_count'][0]} -> {d['chunk_count'][1]}")
        if "note" in d: bits.append(d["note"])
        lines.append(f"~ {k}  " + "; ".join(bits))
    return "\n".join(lines)
