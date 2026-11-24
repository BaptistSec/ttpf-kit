import sys, os
sys.path.insert(0, "tests"); sys.path.insert(0, ".")
n = 0
for m in ("test_roundtrip", "test_ops", "test_fuzz", "test_manifest"):
    t = __import__(m)
    for k in sorted(dir(t)):
        if k.startswith("test_"): getattr(t, k)(); n += 1; print("ok", k)
print(n, "passed")
