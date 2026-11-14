# Develop the notebook editor

Notebooks open and save editable reMarkable `.rmdoc` archives on desktop,
Android and iOS. Start at **New / Open Document → Notebook (.rmdoc)** on desktop,
or **New Document → Notebook (.rmdoc)** and **Open Document** on mobile. File
activation also opens an ordinary document tab or session.

## Make a small brush change

Create and save a disposable blank RMDOC, reopen it through the chooser, select
Fineliner and draw a short stroke. For a trial change on desktop, Android and iOS,
change the Medium Fineliner width in `Python/features/notebooks/brushes.py`
(`BRUSHES[17]`) from 3.5 to 3.75 page units. Update the two corresponding
expectations as described in the [brush walkthrough](brush-calibration.md#try-a-brush-change).
After a relaunch, compare a new stroke with the old one, then save and reopen.
The fresh stroke should retain the new width and the old stroke should retain
its stored width. Restore the calibration after the exercise.

From the repository root, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_brush_calibration.py
```

Expect six passing checks for width, pressure, thickness, color and round trips.
For screen appearance or preview parity, edit
`Python/features/notebooks/assets/drawing.js` and run the
[Canvas probe](brush-calibration.md#canvas-probe).

## Find the owner of a change

Paths below are relative to `Python/features/notebooks/` unless stated otherwise.

| Change | Edit point | Focused check or contract |
| --- | --- | --- |
| Desktop open or first-page creation | `__init__.py:register` declares the launcher. `Python/services/documents/ui/notebooks.py` resolves the storage choice and opens `ui/workspace.py`. `ui/setup.py` owns the template dialog. | `Python/tests/notebooks/test_notebook_setup.py` and `test_notebook_desktop.py` in the same folder |
| Mobile creation or reader controls | `mobile/setup.py`, `mobile/panel.py`, `mobile/native_tools.py` and `mobile/surface.py` | `test_notebook_creation_templates.py` in the mobile host suite |
| Archive layout, page commands or recovery | `notebook.py`, `editor.py:Editor.apply`, `storage.py:NotebookDocument` and `recovery.py:Repository` | `test_notebooks.py`, `test_notebook_protocol.py` and `test_recovery_sharing.py` in the desktop suite |
| Brush appearance, pressure or color | `brushes.py` and `assets/drawing.js` | [Brush calibration and rendering](brush-calibration.md) |
| Pen delivery, touch, page framing or zoom | `assets/input.js`, `assets/viewport.js`, `mobile/viewport.py` and the native input adapters | [Viewport and pen input](viewport-input.md) |
| Which samples a new stroke saves | `sampling.py` after width calculation in `ink.py` | [Saved stroke sampling](stroke-sampling.md) |
| Lasso, transform or ink clipboard | `assets/selection.js`, `Editor.apply` and `ink.py` | [Stroke selection](stroke-selection.md) |
| USB/SSH retrieval or tablet write qualification | `remarkable_ssh.py`, `remarkable_store.py` and the `ui/remarkable_*` dialogs | [SSH transfer contracts](ssh-transfers.md) |

## Format and preservation boundary

`notebook.py` reads bounded ZIP members in place and requires exactly one
document root. It rejects traversal, links, special entries, duplicate members,
encrypted ZIP entries and oversized inputs. It supports legacy page lists and
modern `cPages`. Structural edits update ordering and counts, retain modern
tombstones and assign new IDs to copied pages and sidecars. Unknown members
and JSON fields stay opaque.

`ink.py` preserves original v6 frames and uses CRDT order (the sequence described
by object IDs and anchors) for known objects. New ink uses native scene lines;
erasure retains sequence links through tombstones. Writes reuse registered
byte-sized authors and allocate above existing IDs and references. Untouched
frames keep their bytes and edited known lines keep their extra fields.
Unsupported blocks, visible typed text and native highlights or anchoring
that the editor cannot safely update put the page in preservation-only mode.
The editor refuses cross-notebook copies of unsupported objects.

The standard scene is 1404 × 1872 page units with native X centered at zero.
Pressure is normalized to 0–1 in memory and encoded in an 8-bit field.
Imported widths already contain the tablet's dynamics. New widths are
calculated once and rounded to quarter units. See [brush calibration](brush-calibration.md).

The vendored MIT-licensed **rmscene 0.8.0** source and license are under
`_vendor/rmscene`. Logistics carries a type namespace fix and measured
Highlighter IDs 14–16. The declared `packaging` runtime remains portable across
desktop and Briefcase. The upstream package's old `packaging<24` metadata
conflicts with Briefcase's `packaging>=24.2` build requirement.
[rmscene upstream](https://github.com/ricklupton/rmscene) ·
[RMDOC archive schema](https://github.com/go-go-golems/remarquee/blob/main/pkg/rmdoc/content.go)

## Page template model and views

`templates.py` generates Logistics vector artwork for previews, custom
`.template` JSON and PDF export. Stock ruled choices store the native references
`P Lines small`, `P Lines medium` and `P Lines large` for the receiving reader
to render. Previews and custom forms use original Logistics artwork. Selectors
identify those layouts and state that Logistics is unaffiliated with reMarkable.
The native reference names and JSON schema are documented in the
[Paper Pro template catalog](https://github.com/delize/remarkable-daily-journal/blob/main/docs/templates/rmpp.md)
and [native vector schema example](https://github.com/Martes-Delta-Co/Remarkable-Mobile-Prototyping-Templates/blob/main/templates/universal/uxtpl_android_four_col.template).

Template changes mark structure dirty. Inserting a page after the current one
inherits its template, format and visibility, with an empty ink layer.
Unknown imported artwork and sidecars are preserved. If available geometry
doesn't match the imported asset, the editor shows an unavailable-artwork
notice. PDF-backed pages retain their own backgrounds. Test catalog and archive
behavior with `test_template_catalog.py` and `test_notebooks.py`. The
`notebook_template_probe.py` script checks selector actions and pointer mapping
in real Qt WebEngine. Use the desktop interpreter, `PYTHONPATH=Python:.` and
`--output test-results/notebook-templates`.

`remarkable_export.py` writes **Export Copy**. For Logistics templates or
hidden nonblank rules it embeds a vector PDF, marks pages Blank to avoid a
second background, and retains native scene bytes. A copy with unknown visible
artwork is refused rather than published with missing paper. Save, Save As
and recovery retain the editable template model. Reusing an embedded PDF
preserves its bytes. Export uses 72/226 PDF points per native page unit and
extends page boxes to keep recognized ink, including ink on hidden layers.
Pro forms use 1404 × 1872 and Move forms use 821 × 1460 native units. Native
ink beyond the standard horizontal editor frame can remain preserved even
where the canvas cannot edit it.
[Upstream scene geometry reference](https://github.com/ricklupton/rmc/blob/main/src/rmc/exporters/svg.py)

reMarkable Desktop 3.28.1 discarded custom template assets from named-template
exports. Copying with a vector PDF preserved the backgrounds and editable
ink in the two-page desktop case. For the export contracts run:

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_remarkable_export.py
```

## Editing and recovery

The WebView sends commands validated by `protocol.py` to `Editor.apply`.
Desktop and mobile use the same document model, snapshots and ink codec.
Recovery stores an immutable base archive plus content-addressed ink pages
and a revisioned manifest. Ordinary ink updates can write only changed pages.
Unchanged objects and native frames are shared across history to limit memory.
Source writes use revision checks. Private notebooks keep draft changes in
memory. See [shared document storage](../../../development/document-storage.md)
for provider, version and lifetime contracts.

New desktop drafts are unsaved until a destination is chosen. Cancelled first
Save keeps the draft open. Discard on a source-backed recovered notebook resets
the recovery base to the exact saved bytes while checking its observed revision.
An orphaned draft discards only the recovery revision it observed. Failed
discard keeps the draft available. Delete uses the document resource's
revision check and releases the editor only after confirmation.

A rejected checkpoint restores the prior edit when the old manifest is still
visible and the binding can be rolled back safely. When the new manifest is
visible but directory durability is unconfirmed, retain the edit, history and
both generations of objects. An unverified publication or rollback retains the
in-memory draft and marks recovery unconfirmed. Ordinary retirement waits for
confirmed recovery or a successful Save. Save As can rescue a draft whose
original source is unavailable. The binding and recovery files have separate
publication boundaries. Run the focused recovery contract from the repo root:

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_recovery_sharing.py
```

## Mobile editor and rendering

Attach the canvas to its presented native view before publishing HTML.
A replacement canvas gets a fresh bridge identity and command sequence. Fence
pending commands before Save, page navigation or close so a rapid last stroke
survives and a retired view cannot edit its replacement. iOS batches transient
native pen previews per animation frame and flushes on pen-up. Android paints
its native pen path immediately. Boox uses the vendor handwriting overlay for
eligible Ballpoint and Fineliner contacts, with the shared Canvas path for other
tools or unavailable SDK/firmware support. The Java owners are `NotebookInput`,
`BooxInk`, `BooxBallpoint` and `BooxRefresh` under `mobile/android/`.
[Onyx pen SDK](https://github.com/onyx-intl/OnyxAndroidDemo/blob/master/doc/Onyx-Pen-SDK.md) ·
[Onyx partial refresh API](https://github.com/onyx-intl/OnyxAndroidDemo/blob/master/doc/EPD-Screen-Update.md)

Canvas reuses page, draft and mask bitmaps on same-size page changes. Mobile
caps each backing bitmap at 8 megapixels and desktop at 16 megapixels
(about 96 and 192 MiB across three RGBA stores before compositor allocations).
Higher CSS zoom can soften the display while preserving native geometry.
Paintbrush clips filtered draws to ink bounds plus a blur fringe. At pen-up
the renderer composites existing draft bounds. See the
[brush probe](brush-calibration.md#canvas-probe) for live and saved raster checks.

## Native image cutouts and protected PDF backgrounds

The PDF reader's **Duplicate as .rmdoc to annotate** embeds the original PDF
and uses create-only publication, including for encrypted providers. This
prevents overwriting a copy created concurrently. The editor renders the active
PDF background behind transparent ink. Redirects follow page edits, with -1
for a blank insertion. Cross-notebook copying of PDF-backed pages is refused.
EPUB-backed RMDOC is unsupported.

Capture owns an image clipboard separate from Select. Cross-page Copy/Cut
keeps the exact page-space corners. The embedded PDF unlock cache keys by
encrypted contents and invalidates on changed bytes. Explicit password
submission bypasses cached empty-password failure. Mobile prewarms
classification off the UI thread and rechecks credentials and navigation
ownership before mounting. Use `test_notebook_images.py`, `test_pdf_annotation.py`
and mobile `test_notebook_pdf_prewarm.py` for these contracts. The synthetic
AES-256 native image fixture can be checked with
`python -m Python.tests.notebooks.native_image_fixture` using the project interpreter
and `PYTHONPATH=Python:.`. Native capture acceptance requires a fresh managed
suite through both Local and Secret LocalCrypt.

## Internal page links

`Editor.page_links` maps PDF link rectangles and current page redirects.
`assets/links.js` recognizes a completed finger tap on mobile or
Command-click on macOS / Ctrl-click on Windows and Linux. Pens keep drawing
and swipes keep paging. A successful jump offers Undo for three seconds.
`link_gesture_logic.js` exercises the production handler in V8.
`notebook_links_probe.py` covers Qt WebEngine delivery and timer behavior.

## Current implementation and acceptance boundary

| Scope | Current state |
| --- | --- |
| Desktop editor | Portable format and host tests cover creation, editing, export and recovery. Linux latency and Windows normal-renderer stress latency remain open. macOS native save-picker acceptance requires direct interaction. |
| Android and iOS | Managed template checks exercised creation, isolated page changes, inherited paper and save/reopen for their sampled payloads. Bind native template and queued-command fence acceptance to the current payload. |
| Physical input | Actual Pencil pressure/palm behavior, optical Boox latency and reMarkable select/move/erase checks have separate [hardware procedures](hardware-acceptance.md). |
| Tablet transfers | See [SSH transfer qualification](ssh-transfers.md#evidence-and-exact-device-work-needed) for bounded firmware findings, corpus preconditions and outstanding write qualification. |
