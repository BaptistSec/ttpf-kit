import sys, os, tempfile, zlib; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ttpf_kit import container as c, fixtures as f, manifest as mf, cli

def _tree(variant):
    d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "sub"))
    base = f.sample(); t = c.parse(base)
    open(os.path.join(d, "a.ttpf"), "wb").write(base if variant == 0 else c.replace_chunk(t, 2, f.zpad(b"v2")))
    open(os.path.join(d, "sub", "b.ttpf"), "wb").write(base)
    open(os.path.join(d, "junk.ttpf"), "wb").write(b"not a texture file")
    open(os.path.join(d, "notes.txt"), "wb").write(b"ignored")
    if variant == 1: open(os.path.join(d, "new.ttpf"), "wb").write(base)
    return d

def test_manifest_deterministic_and_relative_keys():
    d = _tree(0)
    m1, m2 = mf.build(d), mf.build(d)
    assert mf.dumps(m1) == mf.dumps(m2)
    assert sorted(m1["files"]) == ["a.ttpf", "junk.ttpf", "sub/b.ttpf"]
    assert "unparsed" in m1["files"]["junk.ttpf"] and "parts" in m1["files"]["a.ttpf"] and m1["files"]["a.ttpf"]["kind"] == "ttpf"

def test_compare_reports_chunk_level_change():
    r = mf.compare(mf.build(_tree(0)), mf.build(_tree(1)))
    assert r["added"] == ["new.ttpf"] and r["removed"] == []
    assert list(r["changed"]) == ["a.ttpf"] and r["changed"]["a.ttpf"]["parts_changed"] == [2]
    assert sorted(r["unchanged"]) == ["junk.ttpf", "sub/b.ttpf"]

def test_manifest_cli_roundtrip_and_exit_codes():
    d0, d1, o = _tree(0), _tree(1), tempfile.mkdtemp()
    j = lambda n: os.path.join(o, n)
    assert cli.main(["manifest", d0, j("m0")]) == 0 and cli.main(["manifest", d1, j("m1")]) == 0
    assert cli.main(["compare", j("m0"), j("m0")]) == 0
    assert cli.main(["compare", j("m0"), j("m1")]) == 1
    assert cli.main(["compare", j("m0"), j("missing")]) == 2
    assert cli.main(["manifest", j("nope"), j("x")]) == 2

def test_legacy_manifest_loads_and_new_handlers_plug_in():
    import json
    legacy = {"format": "ttpf-manifest/1", "files": {"a.ttpf": {"sha256": "x", "size": 1, "chunks": ["h1"], "textures": [[1, 1, 2, 0, 1, 3]]}}}
    m = mf.loads(json.dumps(legacy))
    assert m["files"]["a.ttpf"]["parts"] == ["h1"] and m["files"]["a.ttpf"]["kind"] == "ttpf"
    # a second format registered through HANDLERS shows up and compares with the same machinery
    mf.HANDLERS[".demo"] = ("demo", lambda b: {"parts": [mf._sha(b[i:i + 4]) for i in range(0, len(b), 4)], "meta": []})
    try:
        d = tempfile.mkdtemp(); open(os.path.join(d, "x.demo"), "wb").write(b"aaaabbbbcccc")
        e = tempfile.mkdtemp(); open(os.path.join(e, "x.demo"), "wb").write(b"aaaaBBBBcccc")
        r = mf.compare(mf.build(d), mf.build(e))
        assert r["changed"]["x.demo"]["parts_changed"] == [1]
    finally:
        del mf.HANDLERS[".demo"]
