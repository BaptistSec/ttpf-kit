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
