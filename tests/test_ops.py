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

def test_diff_apply_reverse_and_determinism():
    a = f.sample(); b = c.replace_chunk(c.parse(a), 2, f.zpad(b"hello" * 100))
    patch = p.make_patch(a, b)
    assert p.dump_patch(patch) == p.dump_patch(p.make_patch(a, b))          # deterministic
    assert len(patch["ops"]) == 1 and p.apply_patch(a, patch) == b
    assert p.apply_patch(b, p.invert(patch)) == a                          # reversible
    try: p.apply_patch(b, patch); assert False
    except p.PatchError: pass

def test_corrupt_patch_rejected():
    a = f.sample(); b = c.replace_chunk(c.parse(a), 2, f.zpad(b"x" * 50))
    text = p.dump_patch(p.make_patch(a, b))
    p.load_patch(text)
    bad = text.replace('"new_sha256"', '"new_sha256x"', 1)
    for s in (bad, "not json", "{}"):
        try: p.load_patch(s); assert False
        except p.PatchError: pass

def test_merge_clean_and_conflict():
    base = f.sample(); t = c.parse(base)
    left = c.replace_chunk(t, 1, bytes(range(16)) * 4 + b"L")
    right = c.replace_chunk(t, 2, f.zpad(b"right side"))
    m = p.merge(base, left, right); tm = c.parse(m)
    assert c.chunk_payload(tm, 1).startswith(bytes(range(16))) and zlib.decompress(c.chunk_payload(tm, 2).rstrip(b"\0")).rstrip(b"\0") == b"right side"
    assert p.merge(base, left, left) == left                                # same edit both sides is fine
    other = c.replace_chunk(t, 1, b"different")
    try: p.merge(base, left, other); assert False
    except p.Conflict as ex: assert "1" in str(ex)

def test_atomic_write_backup_and_no_partial_files():
    d = tempfile.mkdtemp(); fp = os.path.join(d, "x.bin")
    p.write_atomic(fp, b"one"); p.write_atomic(fp, b"two", backup=True)
    assert open(fp, "rb").read() == b"two" and open(fp + ".bak", "rb").read() == b"one"
    assert [n for n in os.listdir(d) if n.startswith(".ttpf-kit-")] == []

def test_cli_apply_reverse_in_place_and_merge_exit_codes():
    d = tempfile.mkdtemp(); j = lambda n: os.path.join(d, n)
    base = f.sample(); t = c.parse(base)
    open(j("a"), "wb").write(base)
    open(j("b"), "wb").write(c.replace_chunk(t, 2, f.zpad(b"new")))
    open(j("c"), "wb").write(c.replace_chunk(t, 2, f.zpad(b"other")))
    assert cli.main(["diff", j("a"), j("b"), j("p")]) == 0
    assert cli.main(["apply", j("a"), j("p"), j("o"), ]) == 0 and open(j("o"), "rb").read() == open(j("b"), "rb").read()
    assert cli.main(["apply", j("a"), j("p"), "-", "--in-place"]) == 0 and os.path.exists(j("a.bak"))
    assert cli.main(["apply", j("a"), j("p"), "-", "--reverse", "--in-place"]) == 0 and open(j("a"), "rb").read() == base
    assert cli.main(["merge", j("a"), j("b"), j("c"), j("m")]) == 3
    assert cli.main(["apply", j("o"), j("p"), j("zz")]) == 2                # wrong base

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

def test_verify_cross_checks_sizes():
    base = f.sample(); t = c.parse(base)
    assert c.verify(t) == []
    short = c.replace_chunk(t, 2, zlib.compress(b"too short"))
    assert any("chunk table says" in e for e in c.verify(c.parse(short)))
    big = c.replace_chunk(t, 2, zlib.compress(bytes(0x5000)))
    assert any("longer than" in e for e in c.verify(c.parse(big)))
    trunc = c.replace_chunk(t, 2, f.zpad(b"abc")[:20])
    assert c.verify(c.parse(trunc))
    import struct
    bad = bytearray(base); d = struct.unpack_from("<IIII", bad, 0x100 + 0x10)
    struct.pack_into("<IIII", bad, 0x100 + 0x10, d[0], d[1], 0x100000, d[3])
    assert any("past the end" in e for e in c.verify(c.parse(bytes(bad))))

def test_apply_only_rejects_newly_introduced_problems():
    t = c.parse(f.sample())
    flawed = c.replace_chunk(t, 2, zlib.compress(b"short"))                  # base already fails verify
    assert c.verify(c.parse(flawed))
    fixed = c.replace_chunk(c.parse(flawed), 1, bytes(range(16)) * 4 + b"x")  # unrelated edit
    assert p.apply_patch(flawed, p.make_patch(flawed, fixed)) == fixed
    worse = c.replace_chunk(c.parse(f.sample()), 2, zlib.compress(b"short"))
    try: p.apply_patch(f.sample(), p.make_patch(f.sample(), worse)); assert False
    except p.PatchError as ex: assert "verification" in str(ex)
