"""Asset/build comparison. A manifest records every file a handler recognises under a folder: sha256 and
size for all, plus "parts" (hashes of sub-units such as chunks) and "meta" (small descriptor records) when
the handler can parse the format. Comparing two manifests reports added, removed, changed and unchanged
files and, for changed files, which parts and meta records differ. Manifests hold hashes and descriptors
only, never game data. New formats plug in by registering a handler (see HANDLERS and docs/MANIFEST.md)."""
import hashlib, json, os
from . import container as c

FORMAT = "asset-manifest/1"
LEGACY = "ttpf-manifest/1"

def _sha(b): return hashlib.sha256(b).hexdigest()

def ttpf_handler(data: bytes) -> dict:
    t = c.parse(data)
    return {"parts": [_sha(c.chunk_payload(t, i)) for i in range(len(t.chunks))],
            "meta": [[d.width, d.height, d.dxgi, d.tile_mode, d.array_size, d.page] for d in t.descriptors],
            "problems": len(c.verify(t))}

# extension -> (kind, handler). A handler returns {"parts": [...], "meta": [...], ...} or raises on malformed input.
HANDLERS = {".ttpf": ("ttpf", ttpf_handler)}

def file_entry(data: bytes, kind: str = None, handler=None) -> dict:
    e = {"sha256": _sha(data), "size": len(data)}
    if kind: e["kind"] = kind
    if handler:
        try: e.update(handler(data))
        except Exception as ex:   # malformed file: keep the hash, record why
            e["unparsed"] = str(ex)[:120]
    return e

def build(root: str) -> dict:
    files = {}
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for n in sorted(fn):
            ext = os.path.splitext(n)[1].lower()
            if ext in HANDLERS:
                kind, h = HANDLERS[ext]
                path = os.path.join(dp, n)
                rel = os.path.relpath(path, root).replace(os.sep, "/")   # same keys on Windows and Linux
                with open(path, "rb") as fh: files[rel] = file_entry(fh.read(), kind, h)
    return {"format": FORMAT, "files": files}

def dumps(m: dict) -> str:
    return json.dumps(m, sort_keys=True, indent=1) + "\n"

def loads(text: str) -> dict:
    try: m = json.loads(text)
    except json.JSONDecodeError as ex: raise ValueError(f"manifest is not valid JSON: {ex}")
    if not isinstance(m, dict) or m.get("format") not in (FORMAT, LEGACY) or not isinstance(m.get("files"), dict):
        raise ValueError(f"not a {FORMAT} manifest")
    if m["format"] == LEGACY:   # 0.3 manifests used chunks/textures
        for e in m["files"].values():
            if "chunks" in e: e["parts"] = e.pop("chunks"); e["meta"] = e.pop("textures", []); e.setdefault("kind", "ttpf")
        m["format"] = FORMAT
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
        if x.get("kind") != y.get("kind"):
            d["note"] = "file kind differs"
        elif "parts" in x and "parts" in y:
            if len(x["parts"]) != len(y["parts"]):
                d["part_count"] = [len(x["parts"]), len(y["parts"])]
            d["parts_changed"] = [i for i, (p, q) in enumerate(zip(x["parts"], y["parts"])) if p != q]
            if x.get("meta") != y.get("meta"):
                xm, ym = x.get("meta", []), y.get("meta", [])
                d["meta_changed"] = [i for i in range(min(len(xm), len(ym))) if xm[i] != ym[i]]
                if len(xm) != len(ym): d["meta_count"] = [len(xm), len(ym)]
        else:
            d["note"] = "one side could not be parsed; whole-file hash differs"
        out["changed"][k] = d
    return out

def render(r: dict) -> str:
    lines = [f"added {len(r['added'])}  removed {len(r['removed'])}  changed {len(r['changed'])}  unchanged {len(r['unchanged'])}"]
    lines += [f"+ {k}" for k in r["added"]] + [f"- {k}" for k in r["removed"]]
    for k, d in r["changed"].items():
        bits = []
        pc = d.get("parts_changed")
        if pc: bits.append(f"{len(pc)} part(s): {pc[:8]}{'...' if len(pc) > 8 else ''}")
        if d.get("meta_changed"): bits.append(f"{len(d['meta_changed'])} descriptor(s)")
        if "part_count" in d: bits.append(f"part count {d['part_count'][0]} -> {d['part_count'][1]}")
        if "meta_count" in d: bits.append(f"descriptor count {d['meta_count'][0]} -> {d['meta_count'][1]}")
        if "note" in d: bits.append(d["note"])
        lines.append(f"~ {k}  " + "; ".join(bits))
    return "\n".join(lines)
