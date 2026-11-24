import sys, os, tempfile, zlib; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ttpf_kit import container as c, fixtures as f, corpus as cp, cli

def _folder():
    d = tempfile.mkdtemp(); base = f.sample(); t = c.parse(base)
    open(os.path.join(d, "good1.ttpf"), "wb").write(base)
    open(os.path.join(d, "good2.ttpf"), "wb").write(c.replace_chunk(t, 2, f.zpad(b"other")))
    open(os.path.join(d, "bad_size.ttpf"), "wb").write(c.replace_chunk(t, 2, zlib.compress(b"short")))
    open(os.path.join(d, "junk.ttpf"), "wb").write(b"RDS5" + b"\0" * 10)
    return d

def test_corpus_counts_classes_and_no_names():
    r = cp.run(_folder())
    assert r["files"] == 4 and r["ok"] == 2
    text = cp.render(r)
    assert "good1" not in text and "junk" not in text and ".ttpf" not in text      # names stay out of the summary
    assert any(k.startswith("unparsed") for k in r["classes"]) and any(k.startswith("verify: chunk N: zlib gives") for k in r["classes"])
    assert r["tally"]["etpf_A_is_634"] == 3 and r["tally"]["desc_total"] == 6

def test_corpus_names_flag_and_exit_code():
    d = _folder()
    r = cp.run(d, names=True)
    assert any("bad_size.ttpf" in v for vs in r["names"].values() for v in vs)
    assert cli.main(["corpus", d]) == 1
    e = tempfile.mkdtemp(); open(os.path.join(e, "a.ttpf"), "wb").write(f.sample())
    assert cli.main(["corpus", e]) == 0
    assert cli.main(["corpus", os.path.join(e, "nope")]) == 2
