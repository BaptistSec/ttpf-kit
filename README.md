# ttpf-kit

Tools for working with the `.ttpf` texture databases that ship with GTA VI: check that a file is sound, compare two game builds, and make patches that can be applied, merged and undone safely.

It does not decode textures, and it does not touch the encrypted archives. There are good viewers for that already. This is for the other side of modding: knowing what changed between builds, and shipping a change without damaging the file.

You need Python 3.9 or newer. There is nothing to install:

    python -m ttpf_kit verify textures.ttpf

`verify` checks the chunk table, that compressed chunks unpack to the size the table implies, and that every texture starts inside the data. It prints each problem and exits with 1 if there are any.

## Comparing two builds

Point `manifest` at a folder and it records a hash for every `.ttpf` inside, including a hash per chunk. The manifest holds no game data, so two people can compare builds by swapping small JSON files.

    python -m ttpf_kit manifest build1/ build1.json
    python -m ttpf_kit manifest build2/ build2.json
    python -m ttpf_kit compare build1.json build2.json

    added 0  removed 0  changed 1  unchanged 0
    ~ ui.ttpf  1 part(s): [2]

That output is from the synthetic test files. On a real build `compare` lists every changed file and the chunk numbers that differ. The format is described in [docs/MANIFEST.md](docs/MANIFEST.md).

## Patching

`diff` writes a patch containing the old and new bytes of each changed chunk, with hashes. The same two files always give a byte-identical patch.

    python -m ttpf_kit diff original.ttpf edited.ttpf fix.json
    python -m ttpf_kit apply original.ttpf fix.json patched.ttpf

`apply` refuses a patch that was made for a different file, checks the result, and writes it through a temporary file so a failure never leaves a half-written texture database. Add `--in-place` to overwrite the input (the old version is kept as `.bak`) or `--reverse` to undo a patch.

If two people edited the same original, `merge` combines the edits:

    python -m ttpf_kit merge original.ttpf mine.ttpf theirs.ttpf merged.ttpf

Edits to different chunks merge. If both changed the same chunk differently it stops with exit code 3 and names the chunk.

## Checking a folder of samples

`corpus` runs every check over a folder and prints only counts and failure classes, no file names, so the summary is safe to paste. It also tallies how several unconfirmed fields behave across your files (see [ttpf-spec](https://github.com/BaptistSec/ttpf-spec) for which ones). Add `--names` for a local list of the files behind each failure.

    python -m ttpf_kit corpus samples/

## Status

The file layout comes from two community sources that disagree on a few fields, and so far the tool has only been run on synthetic files. It passes its tests on Linux and on Windows Python under Wine, not on native Windows yet. Expect `verify` to be wrong in places until it has met real files; `apply` only refuses problems a patch itself introduces, so it will not block a file that `verify` already complains about.

Compressed BCPack chunks are carried as opaque bytes. They can be replaced whole but not decoded or re-encoded. Fields nobody has explained are kept as raw words and written back unchanged.

`info`, `extract` and `replace` do what their names say. Run the tests with `python run_tests.py`.

MIT licence. No game files are included, and you should not add any to this repository.
