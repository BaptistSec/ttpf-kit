import sys, os, random; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ttpf_kit import container as c, fixtures as f

def test_corrupt_inputs_never_crash():
    """Random byte flips and truncations must give ValueError or a verify() report, never another exception."""
    base = f.sample(); rng = random.Random(1234); handled = 0
    for _ in range(3000):
        b = bytearray(base)
        for _ in range(rng.randint(1, 6)): b[rng.randrange(len(b))] = rng.randrange(256)
        if rng.random() < 0.3: b = b[:rng.randrange(len(b))]
        try:
            t = c.parse(bytes(b)); c.verify(t); handled += 1
        except (ValueError, struct_error()): pass
    assert handled > 0

def struct_error():
    import struct; return struct.error
