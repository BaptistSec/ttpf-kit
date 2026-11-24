import sys, os, random, struct, json, base64, tempfile, zlib
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ttpf_kit import container as c, fixtures as f, patch as p, cli, corpus

def _set(raw, off, fmt, v):
    b = bytearray(raw); struct.pack_into(fmt, b, off, v); return bytes(b)

def _tmp():
    return tempfile.mkdtemp()

def _leftovers(d):
    return [x for x in os.listdir(d) if x.startswith(".ttpf-kit-")]

def test_header_counts_that_lie_are_rejected_cheaply():
    raw = f.sample()
    for off, v in ((4, 0xFFFFFFFF), (4, 0), (16, 0xFFFFFF), (16, 0x7FFFFFFF)):
        try: c.parse(_set(raw, off, "<I", v)); assert False, (off, v)
        except c.ParseError: pass
    t = c.parse(raw); eoff = t.header_pages * 0x100
    try: c.parse(_set(raw, eoff + 8, "<I", 0xFFFFFFFF)); assert False
    except c.ParseError: pass
    for n in range(0, 0x18):
        try: c.parse(raw[:n]); assert False
        except c.ParseError: pass

def test_bad_offsets_block_rewrite_and_extract():
    raw = f.sample(); t = c.parse(raw)
    # chunk 1 ends past the end of the file
    bad = _set(raw, 0x18 + 8, "<I", (len(raw) // 0x100 + 50) | (t.chunks[1].lo & ~0x03FFFFFF))
    t2 = c.parse(bad)
    assert c.verify(t2)
    for fn in (lambda: c.replace_chunk(t2, 0, b"x"), lambda: c.chunk_payload(t2, 1)):
        try: fn(); assert False
        except c.ParseError: pass
    # chunk 1 ends before it starts
    bad = _set(raw, 0x18, "<I", t.chunks[0].lo & ~0x03FFFFFF)
    t3 = c.parse(bad)
    assert any("before start" in e for e in c.verify(t3))
    try: c.replace_chunk(t3, 1, b"x"); assert False
    except c.ParseError: pass

def test_chunk_index_out_of_range_and_negative():
    t = c.parse(f.sample())
    for i in (-1, len(t.chunks), 10**9):
        for fn in (lambda: c.chunk_payload(t, i), lambda: c.replace_chunk(t, i, b"x")):
            try: fn(); assert False
            except c.ParseError: pass

def test_oversize_payload_cannot_overflow_the_offset_field():
    t = c.parse(f.sample())
    # simulate by shrinking the limit rather than allocating 16 GiB
    old = c.MAX_FILE_END; c.MAX_FILE_END = 0x1000
    try: c.replace_chunk(t, 1, b"\0" * 0x2000); assert False
    except c.ParseError: pass
    finally: c.MAX_FILE_END = old

def test_trailing_bytes_and_overlapping_table_are_reported():
    raw = f.sample()
    assert any("after the last chunk" in e for e in c.verify(c.parse(raw + b"extra")))
    t = c.parse(raw)
    t.header_pages = 0   # ETPF "at" offset 0 cannot parse, so exercise the overlap rule on a built object
    assert any("overlaps" in e for e in c.verify(t))

def test_zlib_bomb_is_capped_on_extract_and_verify():
    raw = f.sample(); t = c.parse(raw)
    bomb = zlib.compress(b"\0" * (50 * 1024 * 1024), 9)
    out = c.replace_chunk(t, 2, bomb)
    assert any("zlib" in e for e in c.verify(c.parse(out)))
    d = _tmp(); src = os.path.join(d, "a.ttpf"); open(src, "wb").write(out)
    assert cli.main(["extract", src, "2", os.path.join(d, "o")]) == 2
    assert not os.path.exists(os.path.join(d, "o")) and not _leftovers(d)

def test_malformed_patches_fail_cleanly():
    raw = f.sample(); d = _tmp(); src = os.path.join(d, "a.ttpf"); open(src, "wb").write(raw)
    good = p.make_patch(raw, c.replace_chunk(c.parse(raw), 1, b"hello"))
    def run(patch_text, flags=()):
        pf = os.path.join(d, "p.json"); open(pf, "wb").write(patch_text if isinstance(patch_text, bytes) else patch_text.encode())
        return cli.main(["apply", src, pf, os.path.join(d, "out")] + list(flags))
    mut = lambda **kw: json.dumps({**good, "ops": [{**good["ops"][0], **kw}]})
    cases = [b"\xff\xfe\x00", "[]", "null", '{"format": "ttpf-patch/2"}',
             json.dumps({**good, "ops": "x"}), json.dumps({**good, "ops": [1]}),
             mut(chunk="1"), mut(chunk=-1), mut(chunk=True), mut(chunk=99), mut(old="!!!"), mut(new="@@"),
             mut(old=base64.b64encode(b"zz").decode()), json.dumps({**good, "base_sha256": "0" * 64})]
    for cs in cases:
        assert run(cs) == 2, cs
    assert not os.path.exists(os.path.join(d, "out")) and not _leftovers(d)
    assert open(src, "rb").read() == raw

def test_in_place_failure_leaves_original_and_no_temp_files():
    raw = f.sample(); d = _tmp(); src = os.path.join(d, "a.ttpf"); open(src, "wb").write(raw)
    good = p.make_patch(raw, c.replace_chunk(c.parse(raw), 1, b"hello"))
    pf = os.path.join(d, "p.json"); open(pf, "w").write(p.dump_patch(good))
    # make the backup path a directory so the backup step fails after the temp file exists
    os.mkdir(src + ".bak")
    assert cli.main(["apply", src, pf, "x", "--in-place"]) == 2
    assert open(src, "rb").read() == raw and not _leftovers(d)
    os.rmdir(src + ".bak")
    assert cli.main(["apply", src, pf, "x", "--in-place"]) == 0
    assert open(src + ".bak", "rb").read() == raw and open(src, "rb").read() != raw

def test_write_to_unwritable_destination_leaves_nothing():
    d = _tmp(); raw = f.sample(); src = os.path.join(d, "a.ttpf"); open(src, "wb").write(raw)
    os.mkdir(os.path.join(d, "isdir"))
    assert cli.main(["replace", src, "1", src, os.path.join(d, "isdir")]) == 2
    assert cli.main(["replace", src, "1", src, os.path.join(d, "nodir", "x")]) == 2
    assert not _leftovers(d) and open(src, "rb").read() == raw

def test_every_command_survives_mutated_input_without_a_traceback():
    base = f.sample(); rng = random.Random(77); d = _tmp(); src = os.path.join(d, "a.ttpf"); pay = os.path.join(d, "pay")
    open(pay, "wb").write(b"payload")
    ok_codes = {0, 1, 2, 3}
    for n in range(400):
        b = bytearray(base)
        for _ in range(rng.randint(1, 8)):
            b[rng.randrange(len(b))] = rng.choice((0, 0xFF, rng.randrange(256)))
        if rng.random() < 0.2: b = b[:rng.randrange(len(b))]
        if rng.random() < 0.1: b += bytes(rng.randrange(256) for _ in range(rng.randrange(600)))
        open(src, "wb").write(b)
        for args in (["info", src], ["verify", src], ["extract", src, "1", os.path.join(d, "x")],
                     ["replace", src, "1", pay, os.path.join(d, "r")], ["merge", src, src, src, os.path.join(d, "m")]):
            assert cli.main(args) in ok_codes
        t = None
        try: t = c.parse(bytes(b))
        except c.ParseError: pass
        if t is not None:
            try: out = c.replace_chunk(t, rng.randrange(1, len(t.chunks)) if len(t.chunks) > 1 else 0, b"abc")
            except c.ParseError: continue
            t2 = c.parse(out)   # an accepted rewrite must itself parse
            assert len(t2.chunks) == len(t.chunks)
    assert not _leftovers(d)

def test_accepted_rewrite_changes_only_the_target_chunk():
    base = f.sample(); rng = random.Random(5); checked = 0
    for _ in range(600):
        b = bytearray(base)
        for _ in range(rng.randint(1, 4)): b[rng.randrange(len(b))] = rng.randrange(256)
        try: t = c.parse(bytes(b)); i = rng.randrange(1, len(t.chunks)) if len(t.chunks) > 1 else 0; out = c.replace_chunk(t, i, b"zzz")
        except c.ParseError: continue
        t2 = c.parse(out); checked += 1
        for j in range(len(t.chunks)):
            if j != i: assert c.chunk_payload(t2, j) == c.chunk_payload(t, j)
        assert out[len(out) - (len(t.raw) - t.chunks[-1].file_end):] == t.raw[t.chunks[-1].file_end:]
    assert checked > 50

def test_corpus_reports_unreadable_and_hostile_files_as_classes():
    d = _tmp()
    open(os.path.join(d, "a.ttpf"), "wb").write(b"RDS5" + b"\xff" * 40)
    open(os.path.join(d, "b.ttpf"), "wb").write(f.sample() + b"tail")
    open(os.path.join(d, "c.ttpf"), "wb").write(f.sample())
    r = corpus.run(d)
    assert r["files"] == 3 and r["ok"] == 1 and sum(r["classes"].values()) == 2
