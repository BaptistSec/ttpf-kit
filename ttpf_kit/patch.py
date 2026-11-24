"""Deterministic, reversible chunk-payload patches with hash checks and 3-way merge."""
import base64, hashlib, json, os, shutil, tempfile
from . import container as c

FORMAT = "ttpf-patch/2"

class PatchError(ValueError):
    pass

class Conflict(PatchError):
    pass

def sha(b): return hashlib.sha256(b).hexdigest()
def _b64(b): return base64.b64encode(b).decode("ascii")

def make_patch(old: bytes, new: bytes) -> dict:
    """Patch from old to new. Same chunk count required. Output is a plain dict; dump_patch()
    serialises it deterministically (sorted keys, no timestamps)."""
    a, b = c.parse(old), c.parse(new)
    if len(a.chunks) != len(b.chunks):
        raise PatchError("chunk count differs; patches only replace chunk payloads")
    ops = []
    for i in range(len(a.chunks)):
        pa, pb = c.chunk_payload(a, i), c.chunk_payload(b, i)
        if pa != pb:
            ops.append({"chunk": i, "old_sha256": sha(pa), "new_sha256": sha(pb),
                        "old": _b64(pa), "new": _b64(pb)})
    return {"format": FORMAT, "base_sha256": sha(old), "result_sha256": sha(new), "ops": ops}

def dump_patch(patch: dict) -> str:
    return json.dumps(patch, sort_keys=True, indent=1) + "\n"

def load_patch(text: str) -> dict:
    try:
        p = json.loads(text)
    except json.JSONDecodeError as ex:
        raise PatchError(f"patch is not valid JSON: {ex}")
    if not isinstance(p, dict) or p.get("format") != FORMAT:
        raise PatchError(f"unsupported patch format (want {FORMAT})")
    for k in ("base_sha256", "result_sha256", "ops"):
        if k not in p: raise PatchError(f"patch missing '{k}'")
    if not isinstance(p["ops"], list):
        raise PatchError("patch 'ops' is not a list")
    for op in p["ops"]:
        if not isinstance(op, dict): raise PatchError("patch op is not an object")
        for k in ("chunk", "old_sha256", "new_sha256", "old", "new"):
            if k not in op: raise PatchError(f"patch op missing '{k}'")
        if type(op["chunk"]) is not int or op["chunk"] < 0:
            raise PatchError("patch op has an invalid chunk number")
        try:
            old, new = base64.b64decode(op["old"], validate=True), base64.b64decode(op["new"], validate=True)
        except (ValueError, TypeError):
            raise PatchError(f"patch op for chunk {op['chunk']} has invalid base64")
        if sha(old) != op["old_sha256"] or sha(new) != op["new_sha256"]:
            raise PatchError(f"patch op for chunk {op['chunk']} is corrupt (payload hash mismatch)")
    return p

def invert(patch: dict) -> dict:
    """The patch that undoes this one."""
    return {"format": FORMAT, "base_sha256": patch["result_sha256"], "result_sha256": patch["base_sha256"],
            "ops": [{"chunk": o["chunk"], "old_sha256": o["new_sha256"], "new_sha256": o["old_sha256"],
                     "old": o["new"], "new": o["old"]} for o in patch["ops"]]}

def apply_patch(data: bytes, patch: dict) -> bytes:
    """Apply, then check the result: every op's old hash must match first, the result hash must match
    the patch, and the rebuilt file must pass structural verification. Nothing is returned on failure."""
    if sha(data) != patch["base_sha256"]:
        raise PatchError("file does not match the patch base (sha256 differs)")
    cur = data
    for op in patch["ops"]:
        t = c.parse(cur)
        if not 0 <= op["chunk"] < len(t.chunks):
            raise PatchError(f"chunk {op['chunk']} does not exist")
        if sha(c.chunk_payload(t, op["chunk"])) != op["old_sha256"]:
            raise PatchError(f"chunk {op['chunk']} differs from what the patch expects")
        cur = c.replace_chunk(t, op["chunk"], base64.b64decode(op["new"]))
    if sha(cur) != patch["result_sha256"]:
        raise PatchError("result hash mismatch after applying")
    # only problems the patch introduced count: a base file the checks already flag must stay patchable
    known = set(c.verify(c.parse(data)))
    problems = [x for x in c.verify(c.parse(cur)) if x not in known]
    if problems:
        raise PatchError("result fails verification: " + "; ".join(problems[:3]))
    return cur

def merge(base: bytes, left: bytes, right: bytes) -> bytes:
    """3-way merge of two edited copies of base. Different chunks combine; the same chunk changed to
    different bytes on both sides raises Conflict naming the chunks."""
    pl, pr = make_patch(base, left), make_patch(base, right)
    L = {o["chunk"]: o for o in pl["ops"]}; R = {o["chunk"]: o for o in pr["ops"]}
    clash = sorted(i for i in L.keys() & R.keys() if L[i]["new_sha256"] != R[i]["new_sha256"])
    if clash:
        raise Conflict("both sides changed chunk(s) " + ", ".join(map(str, clash)) + " differently")
    ops = [L.get(i) or R[i] for i in sorted(L.keys() | R.keys())]
    return apply_patch(base, _with_result(base, ops))

def _with_result(base, ops):
    cur = base
    for op in ops:
        t = c.parse(cur)
        cur = c.replace_chunk(t, op["chunk"], base64.b64decode(op["new"]))
    return {"format": FORMAT, "base_sha256": sha(base), "result_sha256": sha(cur), "ops": ops}

def write_atomic(path: str, data: bytes, backup: bool = False):
    """Write via a temp file in the same directory, then os.replace (atomic on Linux and Windows).
    With backup=True an existing file is copied to path + '.bak' first, so the original is never
    missing at any point. On any failure the temp file is removed and the destination is untouched."""
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".ttpf-kit-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data); fh.flush(); os.fsync(fh.fileno())
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        else:
            m = os.umask(0); os.umask(m); os.chmod(tmp, 0o666 & ~m)
        if backup and os.path.exists(path):
            shutil.copyfile(path, path + ".bak"); shutil.copystat(path, path + ".bak")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp): os.remove(tmp)
        raise
