"""RDS5 header, chunk table and ETPF descriptors. Layout: see ttpf-spec, which marks what the community sources agree on."""
import struct
from dataclasses import dataclass

CODECS = {0: "RAW", 1: "BC1", 2: "BC2", 3: "BC3", 4: "BC4", 5: "BC5", 6: "BC6H", 7: "BC7", 8: "ZLIB"}

@dataclass
class Chunk:
    file_end: int      # byte offset
    virt_end: int
    next_codec: int
    lo: int = 0        # raw 8-byte entry words, kept so unknown bits survive a rewrite
    hi: int = 0

@dataclass
class Descriptor:
    width: int
    height: int
    dxgi: int
    mip_field: int     # u0 bits 28..31 (ttpf-viewer reading)
    tile_mode: int     # u1 bits 24..27
    array_size: int    # u1 bits 10..19, plus one
    page: int          # u2 bits 0..20, times 0x1000 is the unpacked-stream offset
    raw: tuple = (0, 0, 0, 0)

@dataclass
class Ttpf:
    flags1: int
    flags2: int
    chunks: list
    etpf_a: int
    etpf_c: int
    descriptors: list
    raw: bytes
    header_pages: int = 1

def _decode_entry(lo, hi):
    return Chunk((lo & 0x03FFFFFF) * 0x100,
                 (hi & 0xFFFFF) * 0x4000 + ((lo >> 30) & 3) * 0x1000,
                 (lo >> 26) & 0xF, lo, hi)

def _encode_entry(c):
    if c.lo or c.hi:   # parsed entry: change only the file end, keep every other bit
        return struct.pack("<II", (c.lo & ~0x03FFFFFF) | (c.file_end // 0x100), c.hi)
    pages, rem = divmod(c.virt_end, 0x4000)
    q = rem // 0x1000
    lo = (c.file_end // 0x100) | (c.next_codec << 26) | (q << 30)
    return struct.pack("<II", lo, pages)

def parse(data: bytes) -> Ttpf:
    if data[:4] != b"RDS5":
        raise ValueError("not RDS5")
    n, f1, f2, hp = struct.unpack_from("<IIII", data, 4)
    chunks = [_decode_entry(*struct.unpack_from("<II", data, 0x18 + 8 * i)) for i in range(n)]
    off = hp * 0x100
    if data[off:off + 4] != b"ETPF":
        raise ValueError("ETPF block not found")
    a, b, c = struct.unpack_from("<III", data, off + 4)
    ds = []
    for i in range(b):
        w = struct.unpack_from("<IIII", data, off + 0x10 + 16 * i)
        u0, u1, u2, _ = w
        ds.append(Descriptor((u0 & 0x3FFF) + 1, ((u0 >> 14) & 0x3FFF) + 1, (u1 & 0x3FF) >> 3,
                             u0 >> 28, (u1 >> 24) & 0xF, ((u1 >> 10) & 0x3FF) + 1, u2 & 0x1FFFFF, w))
    return Ttpf(f1, f2, chunks, a, c, ds, data, hp)

def _enc_desc(d):
    if any(d.raw):
        return struct.pack("<IIII", *d.raw)
    u0 = (d.width - 1) | ((d.height - 1) << 14) | (d.mip_field << 28)
    u1 = (d.dxgi << 3) | ((d.array_size - 1) << 10) | (d.tile_mode << 24)
    return struct.pack("<IIII", u0, u1, d.page, 0)

def build_etpf(t: Ttpf) -> bytes:
    return b"ETPF" + struct.pack("<III", t.etpf_a, len(t.descriptors), t.etpf_c) + \
        b"".join(_enc_desc(d) for d in t.descriptors)


def chunk_spans(t: Ttpf):
    start = t.header_pages * 0x100  # the ETPF block starts here
    out = []
    for c in t.chunks:
        out.append((start, c.file_end))
        start = c.file_end
    return out

def chunk_codec(t: Ttpf, i: int) -> int:
    # the codec of chunk i lives in table entry i-1; chunk 0 is the ETPF block
    return 0 if i == 0 else t.chunks[i - 1].next_codec

def chunk_payload(t: Ttpf, i: int) -> bytes:
    s, e = chunk_spans(t)[i]
    return t.raw[s:e]

def replace_chunk(t: Ttpf, i: int, payload: bytes) -> bytes:
    """Replace chunk i. Later file offsets shift; every other byte, including unknown bits, is kept."""
    spans = chunk_spans(t)
    hp_end = spans[0][0]
    pad = lambda b: b.ljust(-(-len(b) // 0x100) * 0x100, b"\0")
    body, entries, pos = b"", [], hp_end
    for j, (s, e) in enumerate(spans):
        blob = pad(payload) if j == i else t.raw[s:e]
        pos += len(blob)
        body += blob
        entries.append(Chunk(pos, t.chunks[j].virt_end, t.chunks[j].next_codec, t.chunks[j].lo, t.chunks[j].hi))
    head = bytearray(t.raw[:hp_end])
    for j, e in enumerate(entries):
        head[0x18 + 8 * j:0x20 + 8 * j] = _encode_entry(e)
    return bytes(head) + body + t.raw[spans[-1][1]:]

def verify(t: Ttpf) -> list:
    import zlib
    errs, raw = [], t.raw
    spans = chunk_spans(t)
    if spans[0][0] % 0x100:
        errs.append("header not 0x100 aligned")
    prev_e, prev_v = spans[0][0], 0
    for i, ((s, e), c) in enumerate(zip(spans, t.chunks)):
        if e < s: errs.append(f"chunk {i}: end before start")
        if e > len(raw): errs.append(f"chunk {i}: ends past file ({e} > {len(raw)})")
        if c.virt_end < prev_v: errs.append(f"chunk {i}: virtual end goes backwards")
        if c.next_codec > 8: errs.append(f"chunk {i}: unknown next codec {c.next_codec}")
        prev_v = c.virt_end
    for i in range(1, len(t.chunks)):
        s_, e_ = spans[i]
        if e_ > len(raw) or e_ < s_:
            continue
        want = t.chunks[i].virt_end - t.chunks[i - 1].virt_end     # unpacked size of this chunk
        if want < 0:
            continue
        codec = chunk_codec(t, i)
        if codec == 8:
            d = zlib.decompressobj()
            try:
                out = d.decompress(raw[s_:e_], want + 1)           # cap output: no zip bombs
            except zlib.error as ex:
                errs.append(f"chunk {i}: bad zlib ({ex})"); continue
            if not d.eof: errs.append(f"chunk {i}: zlib stream is incomplete or longer than the {want} bytes the chunk table allows")
            elif len(out) != want: errs.append(f"chunk {i}: zlib gives {len(out)} bytes, chunk table says {want}")
        elif codec == 0 and (e_ - s_) != want:
            errs.append(f"chunk {i}: raw chunk is {e_ - s_} bytes in the file but {want} unpacked")
        # codecs 1..7 (BCPack) are opaque here: not checked
    if t.chunks and t.descriptors:
        top = t.chunks[-1].virt_end
        for k, d in enumerate(t.descriptors):
            if d.page * 0x1000 >= top:
                errs.append(f"descriptor {k}: starts at {d.page * 0x1000:#x}, past the end of the unpacked data ({top:#x})")
    for k, d in enumerate(t.descriptors):
        if d.width < 1 or d.height < 1: errs.append(f"descriptor {k}: bad size")
    return errs
