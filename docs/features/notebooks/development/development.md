# Develop the notebook editor

The notebook editor opens, creates and saves editable RMDOC archives on
desktop, Android and iOS. The drawing surface collects pen or pointer input.
The Python editor applies the resulting commands to notebook pages, and
storage publishes the archive while preserving supported native ink and
unmodified data. For controls, see the [desktop guide](../user/user.md) and
[mobile guide](../user_mobile/user_mobile.md).

## Follow a stroke from drawing to save

On desktop choose **Logistics → New / Open Document… → Notebook (.rmdoc) →
New**. In **First page template**, choose Blank, then **Create notebook**.
Draw a short Medium Fineliner stroke, save the disposable RMDOC and reopen it
with **Open…** in that chooser.

Start with `assets/drawing.js` when tracing the canvas preview. For the saved
stroke, follow the action through `Editor.apply` to the native width and
thickness calculations in `brushes.py` and the scene writer in `ink.py`.
The [brush calibration walkthrough](brush-calibration.md) explains how to
change and compare those values. The portable tests check constant Fineliner
widths and verify that thickness is written once and survives reopening.

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_brush_calibration.py
```

## Find the owner of a change

| Change | Owner under `Python/features/notebooks/` |
| --- | --- |
| Creation and controls | Desktop `ui/setup.py`, `ui/workspace.py`. Mobile `mobile/setup.py`, `mobile/panel.py`, `mobile/native_tools.py`. |
| Archive layout, commands and recovery | `notebook.py`, `editor.py:Editor.apply`, `storage.py:NotebookDocument`, `recovery.py:Repository`. Check `test_notebooks.py` and `test_notebook_protocol.py`. |
| Brush pressure, texture and color | `brushes.py` and `assets/drawing.js`. See [calibration](brush-calibration.md) and the [Canvas probe](brush-calibration.md#canvas-probe). |
| Pen delivery and zoom | [Viewport and pen input](viewport-input.md). |
| New stroke points or lasso | [Saved stroke sampling](stroke-sampling.md) and [stroke selection](stroke-selection.md). |
| Tablet retrieval and qualification | [SSH transfers](ssh-transfers.md). |

## Format, templates and export

`notebook.py` validates bounded ZIPs and one document root. Preserve opaque members, legacy page lists and modern `cPages` tombstones. `ink.py` preserves original v6 frames and object order. Unsupported objects, unsafe native highlights and visible typed text require preservation-only. Standard geometry is 1404 × 1872 with native X centered at zero. Imported widths already encode dynamics.

The vendored **rmscene 0.8.0** codec is MIT-licensed, Copyright (c) 2023 Rick Lupton. Logistics carries a type namespace fix and measured Highlighter IDs 14–16. Its `packaging` dependency supports Briefcase. [Upstream](https://github.com/ricklupton/rmscene) · [Vendored license](../../../../Python/features/notebooks/_vendor/rmscene/LICENSE.py)

`templates.py` supplies the original artwork and base paper geometry for creation and change previews. Mobile creation rasterizes the shared vector background through the platform PDF renderer. The canvas picker clips the same SVG used on the page. The picker saves paper size separately from the ink scene. Older stock pages without a fixed size retain adaptive framing. Stock presets keep native ruled references. Inserted pages inherit paper without ink. Save retains editable templates. `remarkable_export.py` writes vector PDF backgrounds for custom artwork or hidden rules, keeping scene bytes. It refuses unavailable visible artwork. reMarkable Desktop 3.28.1 discarded named custom assets and retained vector backgrounds and editable ink in the sampled two-page copy. Check `test_remarkable_export.py`.

## Editing and recovery

`protocol.py` validates commands. Recovery retains an immutable base, content-addressed pages and a revisioned manifest. Private drafts stay in memory. Canceling the first Save keeps new drafts open. Discard of a recovered source-backed draft checks revision and resets to exact saved bytes. Failed discard retains the draft. An unverified checkpoint retains the in-memory edit and marks recovery unconfirmed. Save As can rescue an unavailable source. See [document storage](../../../development/architecture/document-storage.md) and `test_recovery_sharing.py`.

Fence pending canvas edits before save, page changes and close. Replacement canvases get fresh bridge identities. Boox uses vendor preview for eligible Ballpoint and Fineliner input with shared Canvas fallback. The preview can hold a burst of strokes while each stroke enters the ordered save queue at pen-up. After 120 ms idle, the app hands off the rendered page and rearms the SDK after frame submission. PDF-backed pages keep their ink separate from embedded PDF backgrounds. Create annotation copies without overwriting. Capture owns a separate image clipboard. `Editor.page_links` maps PDF targets through redirects and `assets/links.js` routes finger taps and desktop modifier-clicks. See `test_notebook_images.py`, `test_pdf_annotation.py` and mobile `test_notebook_pdf_prewarm.py`.

## Current implementation and acceptance boundary

- Portable tests cover creation, ink, export and recovery. Open checks include Linux/Windows stress latency, the macOS native save picker and current mobile template and command-fence payloads.
- Use [hardware acceptance](hardware-acceptance.md) for physical Boox/Pencil input and reMarkable editing. The [3.29.1.0 direct-write trial](ssh-transfers.md#evidence-and-exact-device-work-needed) remains halted. The browser stays read-only.
- [Read-only corpus validation](corpus-validation.md) covers inventory, editor observations and width calibration. The authorized software run is recorded separately from [physical input and tablet round trips](hardware-acceptance.md).
