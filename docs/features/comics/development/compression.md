# Comic compression contract

See the [feature overview](development.md) and [desktop guide](../user/user.md).

## Output rules

- Encode WebP at quality 60 color or 35 grayscale, method 6, height cap 2400, with no upscaling. Shared image code handles chroma, orientation and profiles. Encoded Comics pages drop alpha without compositing.
- Keep the WebP strictly below 75% of original bytes or on override. Otherwise retain original bytes and member name. Preserve multiframe originals by default. Explicit preservation conflicts with always-keep. Omitted preservation with always-keep, or explicit false, permits first-frame conversion.
- `sanitization.py` strips sidecars and flattens supported wrappers. Refuse unsupported layouts and names. Repair numeric padding when single-digit names occur (two digits below 90 files, three below 950, five otherwise). Preflight output collisions before encoding.
- Write root `CompressionLog.txt` for batch skipping. Single-file recompression remains available. Archive statistics count image payloads.

### ComicRack compatibility: rebuilding page records

Rebuild `PageCount` and all `Pages` from selected image indices, sizes and dimensions. Page zero becomes FrontCover. Preserve book metadata outside `Pages`. Reject malformed or duplicate page metadata before publication. The maintainer reported ComicRack crashes with stale records after image changes. Metadata-only edits preserve existing page records.

## Replacement boundary

`cbz.py` extracts to a disposable workspace, validates member paths, encodes and stages beside the source. Verify members, CRCs and payloads, preserve permissions and recheck the source before atomic replacement. Failure preserves the original. Encrypted and plain manifests follow the same rules. For comparison, freeze log time and compare decrypted names and payloads.

Cancel after the current comic, including verification and replacement. Report failed and untouched inputs. Batch compression continues after individual failures.

Run the [compression regression](development.md#try-a-compression-threshold-change) for thresholds and manifests. Check dialog handoff and partial failure from the checkout root:

```sh
python3 dev.py test desktop --exact-file Python/tests/comics/test_comic_compression_dialog.py
```
