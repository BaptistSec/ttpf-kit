# Manifest format (`asset-manifest/1`)

A manifest is deterministic JSON (sorted keys, forward-slash relative paths) describing every recognised file under a folder. It holds hashes and small descriptor records only, never file contents.

```json
{
 "format": "asset-manifest/1",
 "files": {
  "textures/a.ttpf": {
   "kind": "ttpf", "sha256": "...", "size": 1024,
   "parts": ["<sha256 of chunk 0>", "..."],
   "meta": [[width, height, dxgi, tile_mode, array_size, start_page]],
   "problems": 0
  },
  "broken.ttpf": {"kind": "ttpf", "sha256": "...", "size": 18, "unparsed": "reason"}
 }
}
```

- `sha256`, `size`: always present.
- `kind`: which handler recognised the file.
- `parts`: ordered hashes of the file's sub-units. `compare` reports which indexes changed.
- `meta`: ordered small records. `compare` reports which indexes changed.
- `unparsed`: the handler failed; the file is still compared by whole-file hash.

`ttpf-manifest/1` files from v0.3 still load.

## Adding a format

Register an extension in `ttpf_kit.manifest.HANDLERS` with a function that takes the file bytes and returns `{"parts": [...], "meta": [...]}` or raises on malformed input. The same `manifest` and `compare` commands then cover it. A sibling tool (for example a PSIN or archive-index reader) can emit the same shape, so builds containing several formats compare in one pass.
