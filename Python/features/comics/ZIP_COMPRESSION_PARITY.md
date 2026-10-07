# Before/after ZIP compression comparison

Validated October 7, 2026, on macOS using the project's Python 3.12.2 environment.
The pristine baseline was Logistics `43e777cafe8c5bd45fece1538ba32ee75ca2db91`
and its recorded commonUtils commit `70117045020ee9a8f78c9e6ba3be47a9c7cd2ca6`.
Both were exported into a separate temporary directory. The baseline code was not
modified or adapted to provide password support.

No existing CBZ was present in the repository. Tests generated valid four-page CBZ
comic files containing a color PNG, grayscale JPEG, WebP and animated GIF, plus
ComicInfo.xml, a removable notes.txt, .DS_Store and __MACOSX sidecars. Each input was
copied independently so complete compression runs could not affect each other.

Four layouts were tested with both default retention/animation preservation and
forced compressed-image retention without animation preservation. Each combination
ran the pristine plain compressor, the current plain compressor and the current
AES-256 compressor: **24 successful full compression runs**.

| Input page layout | Final page location in all three versions |
| --- | --- |
| Pages at archive root | Root |
| `Book/` wrapper | Root |
| `Book/Pages/` double wrapper | Root |
| `Chapter 1/` and `Chapter 2/` | Original chapter folders |

For every combination, manifests matched at all five checkpoints:

1. Explicit extraction using each version's ZIP helper.
2. Extraction performed inside the complete comic compression run.
3. After comic sanitization and wrapper flattening.
4. The staged result directory immediately before archive creation.
5. The final archive's decrypted entries.

Manifests include exact relative entry names, directories, byte lengths and SHA-256
hashes. This checks page bytes, placement, retention, ComicInfo.xml and
CompressionLog.txt, not just whether an archive can be opened. All comparisons
matched exactly. Only the compression log's clock was frozen to make timestamps
comparable; source filenames and options were identical. Archive comments matched.
All current encrypted output file entries used AES-256, and plain outputs remained
plain. ZIP container hashes, headers and modification timestamps are not expected
to match and were not used to assert parity.

A separate pristine-baseline encrypted run confirmed two distinct behaviors:
its ZIP helper successfully extracted the same AES-protected comic when explicitly
given the password, into exactly the same layout as plain extraction. Its complete
comic compressor did not supply a password, so compression failed and left the
original encrypted CBZ unchanged. The old compressor therefore cannot serve as a
successful encrypted full-run baseline without changing its code.

This establishes before/after behavior on macOS with generated fixtures. It does
not claim that real Windows/Linux machines or external RAR extractors were tested.
The current plain/AES extraction shares one filesystem-layout implementation;
RAR/CBR uses a separate external-extractor flow.

The comparison is now reproducible through
[`compare_comic_zip_versions.py`](../../tests/compare_comic_zip_versions.py), and
runs on each CI platform. See [platform checks](../../tests/PLATFORM_CHECKS.md) for
local commands, prerequisites, artifacts and coverage boundaries.
