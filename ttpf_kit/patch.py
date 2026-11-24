import base64, hashlib, json
from . import container as c

def sha(b): return hashlib.sha256(b).hexdigest()

def make_patch(old: bytes, new: bytes) -> dict:
    a, b = c.parse(old), c.parse(new)
    if len(a.chunks) != len(b.chunks):
        raise ValueError("chunk count differs; patch format only covers chunk payload replacement")
    ops = []
    for i in range(len(a.chunks)):
        pa, pb = c.chunk_payload(a, i), c.chunk_payload(b, i)
        if pa != pb:
            ops.append({"chunk": i, "old_sha256": sha(pa), "new_len": len(pb),
                        "data": base64.b64encode(pb).decode()})
    return {"format": "ttpf-patch/1", "base_sha256": sha(old), "result_sha256": sha(new), "ops": ops}

def apply_patch(old: bytes, patch: dict) -> bytes:
    if patch.get("format") != "ttpf-patch/1": raise ValueError("unknown patch format")
    if sha(old) != patch["base_sha256"]: raise ValueError("base file does not match patch")
    cur = old
    for op in patch["ops"]:
        t = c.parse(cur)
        if sha(c.chunk_payload(t, op["chunk"])) != op["old_sha256"]:
            raise ValueError(f"chunk {op['chunk']} differs from patch base")
        cur = c.replace_chunk(t, op["chunk"], base64.b64decode(op["data"]))
    if sha(cur) != patch["result_sha256"]: raise ValueError("result hash mismatch")
    return cur
