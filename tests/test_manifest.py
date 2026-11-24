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
    assert "unparsed" in m1["files"]["junk.ttpf"] and "chunks" in m1["files"]["a.ttpf"]

def test_compare_reports_chunk_level_change():
    r = mf.compare(mf.build(_tree(0)), mf.build(_tree(1)))
    assert r["added"] == ["new.ttpf"] and r["removed"] == []
    assert list(r["changed"]) == ["a.ttpf"] and r["changed"]["a.ttpf"]["chunks_changed"] == [2]
    assert sorted(r["unchanged"]) == ["junk.ttpf", "sub/b.ttpf"]

def test_manifest_cli_roundtrip_and_exit_codes():
    d0, d1, o = _tree(0), _tree(1), tempfile.mkdtemp()
    j = lambda n: os.path.join(o, n)
    assert cli.main(["manifest", d0, j("m0")]) == 0 and cli.main(["manifest", d1, j("m1")]) == 0
    assert cli.main(["compare", j("m0"), j("m0")]) == 0
    assert cli.main(["compare", j("m0"), j("m1")]) == 1
    assert cli.main(["compare", j("m0"), j("missing")]) == 2
    assert cli.main(["manifest", j("nope"), j("x")]) == 2
