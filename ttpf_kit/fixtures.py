"""Synthetic clean-room fixtures: made-up payloads, no game data."""
import struct, zlib
from .container import _encode_entry, Chunk, Descriptor, Ttpf, build_etpf

def make(descs, payloads, codecs):
    """descs: list[Descriptor]; payloads: list[bytes] (chunk 1..n); codecs: codec of each payload."""
    t = Ttpf(0, 0, [], 634, 0x4290, descs, b"")
    etpf = build_etpf(t)
    n = len(payloads) + 1
    hp = -(-(0x18 + 8 * n) // 0x100)
    pos = hp * 0x100
    blobs = [etpf] + payloads
    entries = []
    for i, b in enumerate(blobs):
        pos += -(-len(b) // 0x100) * 0x100
        nxt = codecs[i] if i < len(codecs) else 0
        entries.append(Chunk(pos, (i + 1) * 0x4000, nxt))
    head = b"RDS5" + struct.pack("<IIII", n, 0, 0, hp) + b"\0" * 0
    head = head.ljust(0x18, b"\0") + b"".join(_encode_entry(e) for e in entries)
    out = head.ljust(hp * 0x100, b"\0")
    for b in blobs:
        out += b.ljust(-(-len(b) // 0x100) * 0x100, b"\0")
    return out

def zpad(data, size=0x4000):
    """zlib stream that unpacks to exactly `size` bytes (the unpacked size the chunk table records)."""
    return zlib.compress(data.ljust(size, b"\0"))

def sample():
    bc7 = bytes(range(16)) * 4  # dummy 4 blocks
    z = zpad(bc7)
    d = [Descriptor(8, 8, 98, 0, 0, 1, 1), Descriptor(16, 16, 71, 1, 1, 1, 2)]
    return make(d, [bc7, z], [7, 8])
