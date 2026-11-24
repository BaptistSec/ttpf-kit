import sys, os, zlib, tempfile; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ttpf_kit import container as c, fixtures as f, patch as p, cli

def test_verify_clean_and_corrupt():
    raw = f.sample(); assert c.verify(c.parse(raw)) == []
    bad = c.replace_chunk(c.parse(raw), 2, b"not zlib at all")
    assert any("bad zlib" in e for e in c.verify(c.parse(bad)))

def test_replace_keeps_other_chunks_and_roundtrips():
    raw = f.sample(); t = c.parse(raw)
    new = bytes(range(1, 256)) + bytes(range(1, 46))
    out = c.replace_chunk(t, 1, new)
    t2 = c.parse(out)
    assert c.chunk_payload(t2, 1).rstrip(b"\0") == new.rstrip(b"\0")
    assert c.chunk_payload(t2, 2) == c.chunk_payload(t, 2)
    assert c.chunk_payload(t2, 0) == c.chunk_payload(t, 0)
    assert [x.virt_end for x in t2.chunks] == [x.virt_end for x in t.chunks]
    assert c.replace_chunk(t, 1, c.chunk_payload(t, 1)) == raw   # identity replace is byte exact

def test_diff_apply():
    a = f.sample(); b = c.replace_chunk(c.parse(a), 2, zlib.compress(b"hello" * 100))
    patch = p.make_patch(a, b)
    assert len(patch["ops"]) == 1 and p.apply_patch(a, patch) == b
    try: p.apply_patch(b, patch); assert False
    except ValueError: pass

def test_cli_verify_and_info(tmp=None):
    d = tempfile.mkdtemp(); fp = os.path.join(d, "a.ttpf"); open(fp, "wb").write(f.sample())
    assert cli.main(["verify", fp]) == 0 and cli.main(["info", fp]) == 0
    assert cli.main(["verify", os.path.join(d, "missing")]) == 2

def test_unknown_bits_survive_replace():
    import struct
    raw = bytearray(f.sample())
    lo, hi = struct.unpack_from("<II", raw, 0x18 + 8)
    struct.pack_into("<II", raw, 0x18 + 8, lo, hi | (0xABC << 20))      # bits 52..63 set (unknown in notes)
    d0 = struct.unpack_from("<IIII", raw, 0x100 + 0x10)
    struct.pack_into("<IIII", raw, 0x100 + 0x10, d0[0], d0[1] | (0x3 << 20), d0[2], 0xDEAD)  # unknown bits + u3
    t = c.parse(bytes(raw))
    out = c.replace_chunk(t, 2, c.chunk_payload(t, 2) + b"\0" * 0x100)
    t2 = c.parse(out)
    assert t2.chunks[1].hi == hi | (0xABC << 20)
    assert t2.descriptors[0].raw[3] == 0xDEAD and t2.descriptors[0].raw[1] >> 20 & 3 == 3
    assert c.verify(t2) == []
