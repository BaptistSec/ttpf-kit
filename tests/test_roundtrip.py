import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ttpf_kit import container as c, fixtures as f

def test_parse_and_rebuild_etpf():
    t = c.parse(f.sample())
    assert len(t.descriptors) == 2 and t.descriptors[0].width == 8 and t.descriptors[1].mip_field == 1
    assert len(t.chunks) == 3
    off = t.raw.find(b"ETPF")
    assert c.build_etpf(t) == t.raw[off:off + 0x10 + 32]
    assert off == t.header_pages * 0x100

def test_chunk_entry_roundtrip():
    for e in [c.Chunk(0x1200, 0x5000, 7), c.Chunk(0x3FFFFFF * 0x100, 0xFFFFF * 0x4000 + 0x3000, 8)]:
        import struct
        lo, hi = struct.unpack("<II", c._encode_entry(e))
        d = c._decode_entry(lo, hi)
        assert (d.file_end, d.virt_end, d.next_codec) == (e.file_end, e.virt_end, e.next_codec)
