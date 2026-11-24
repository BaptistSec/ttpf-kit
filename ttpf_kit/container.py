"""Parse and write RDS5/ETPF containers. Layout from SentinelInteractive/0x52504639
docs/ttpf-rds5-etpf.md (MIT, third-party notes, unverified by us)."""
import struct
from dataclasses import dataclass

CODECS = {0: "RAW", 1: "BC1", 2: "BC2", 3: "BC3", 4: "BC4", 5: "BC5", 6: "BC6H", 7: "BC7", 8: "ZLIB"}

@dataclass
class Chunk:
    file_end: int      # byte offset
    virt_end: int
    next_codec: int

@dataclass
class Descriptor:
    width: int
    height: int
    fmt: int
    dxgi: int
    mips: int
    page: int
    u3: int

@dataclass
class Ttpf:
    flags1: int
    flags2: int
    chunks: list
    etpf_a: int
    etpf_c: int
    descriptors: list
    raw: bytes

def _decode_entry(lo, hi):
    return Chunk((lo & 0x03FFFFFF) * 0x100,
                 (hi & 0xFFFFF) * 0x4000 + ((lo >> 30) & 3) * 0x1000,
                 (lo >> 26) & 0xF)

def _encode_entry(c):
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
        u0, u1, u2, u3 = struct.unpack_from("<IIII", data, off + 0x10 + 16 * i)
        ds.append(Descriptor((u0 & 0x3FFF) + 1, ((u0 >> 14) & 0x3FFF) + 1, u1 & 7,
                             (u1 >> 3) & 0x7F, u1 >> 24, u2 & 0xFFFFF, u3))
    return Ttpf(f1, f2, chunks, a, c, ds, data)

def _enc_desc(d):
    u0 = (d.width - 1) | ((d.height - 1) << 14)
    u1 = d.fmt | (d.dxgi << 3) | (d.mips << 24)
    return struct.pack("<IIII", u0, u1, d.page, d.u3)

def build_etpf(t: Ttpf) -> bytes:
    return b"ETPF" + struct.pack("<III", t.etpf_a, len(t.descriptors), t.etpf_c) + \
        b"".join(_enc_desc(d) for d in t.descriptors)


def chunk_spans(t: Ttpf):
    """(start, end) file byte range for every chunk."""
    start = ((t.raw.find(b"ETPF") ) // 0x100) * 0x100  # header pages end == ETPF start
    out = []
    for c in t.chunks:
        out.append((start, c.file_end))
        start = c.file_end
    return out

def chunk_codec(t: Ttpf, i: int) -> int:
    """Codec of chunk i (chunk 0 is the ETPF block). Stored on entry i-1."""
    return 0 if i == 0 else t.chunks[i - 1].next_codec

def chunk_payload(t: Ttpf, i: int) -> bytes:
    s, e = chunk_spans(t)[i]
    return t.raw[s:e]

def replace_chunk(t: Ttpf, i: int, payload: bytes) -> bytes:
    """Rebuild the file with chunk i replaced. Later chunk ends shift; virtual ends, codecs and
    every other byte are kept. Payload is padded to 0x100."""
    spans = chunk_spans(t)
    hp_end = spans[0][0]
    pad = lambda b: b.ljust(-(-len(b) // 0x100) * 0x100, b"\0")
    body, entries, pos = b"", [], hp_end
    for j, (s, e) in enumerate(spans):
        blob = pad(payload) if j == i else t.raw[s:e]
        pos += len(blob)
        body += blob
        entries.append(Chunk(pos, t.chunks[j].virt_end, t.chunks[j].next_codec))
    head = bytearray(t.raw[:hp_end])
    for j, e in enumerate(entries):
        head[0x18 + 8 * j:0x20 + 8 * j] = _encode_entry(e)
    return bytes(head) + body + t.raw[spans[-1][1]:]

def verify(t: Ttpf) -> list:
    """Return a list of problems (empty means structurally sane)."""
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
        if chunk_codec(t, i) == 8 and i < len(spans) and spans[i][1] <= len(raw):
            try: zlib.decompressobj().decompress(chunk_payload(t, i))
            except zlib.error as ex: errs.append(f"chunk {i}: bad zlib ({ex})")
    for k, d in enumerate(t.descriptors):
        if d.mips < 1: errs.append(f"descriptor {k}: zero mips")
    return errs
