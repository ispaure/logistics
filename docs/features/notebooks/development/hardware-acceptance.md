# Notebook hardware acceptance

See the [implementation status](development.md#current-implementation-and-acceptance-boundary). Use disposable synthetic notebooks. From the configured desktop checkout:

```sh
PYTHONPATH=Python:. .venv/bin/python Python/tests/notebooks/notebook_acceptance_probe.py --output test-results/rmdoc-handoff
```

Use `acceptance.rmdoc` for legacy page order and `modern.rmdoc` for reordered/copied pages and tombstones. Record hashes, source and payload identity, model, firmware and refresh settings.

## Boox physical input and capture-to-export

1. Create a notebook in the isolated QA app. Draw with the physical stylus at light, medium and firm pressure. Check pressure, resting palm, finger gestures, zoom/rotation, erase, select/move, Undo/Redo and resume.
2. Add a page and layer, reorder and copy pages. Export through the native picker and hash the copy. Cancel a second export and verify writing resumes.
3. Check stock lined paper and a custom Move form. Change one page's paper and visibility. Verify insertion inherits paper with empty ink, Save/reopen and Undo/Redo. Export the form and verify fixed artwork stays separate from selectable ink. Retain the editable original.
4. Draw and immediately Save or close, including Keep editing. Verify the last saved stroke survives reopening and a retired canvas cannot edit its replacement.
5. For visible latency use an external camera and record frame rate and method.

## Apple Pencil delivery

1. On a supported iPad with a pressure-capable Pencil, open a blank RMDOC in the
   authorized QA build. Use the automatic pressure setting and draw slow,
   light and firm strokes with Medium Ballpoint. Save and check the native
   points for distinct pressures and widths.
   Medium Fineliner is the constant-width control at 3.5 page units on blank paper.
2. With finger drawing enabled, rest a palm during a Pencil stroke. On hardware
   that supports hover, try a finger gesture while the Pencil hovers over the
   canvas. Expect no unwanted stroke, pan or page change. Lift the pen and palm,
   then confirm that ordinary touch works again.
3. Tap 20 separate dots in rapid succession on a fresh page, then immediately
   Save. Close and reopen. Require 20 distinct dots, including the final one.
   Repeat after reopening the canvas to exercise its new input binding.

Record iPad/Pencil model, OS, app build and exact source/payload identity. Keep
the saved archive hash, per-page stroke counts, pressure/width ranges, and a
short external video that lets a reviewer count contacts and see any palm or
hover effects. Save the video and archives under ignored test results. For
Pencils without pressure sensing, record a separate constant-pressure run.

## reMarkable native ink editing

Enable the USB web interface, open `http://10.11.99.1` on the connected computer and import the synthetic archives and Boox export. Check [supported transfer routes](https://support.remarkable.com/articles/Knowledge/importing-and-exporting-files).

On the tablet verify order, geometry, layers and tool appearance. Select, move and erase native ink on multiple pages, including reordered/copied pages. Add a tablet stroke, re-export and inspect it in desktop and mobile Logistics. Record successful actions, incompatibilities and archive hashes.

## Cleanup

Save evidence under ignored test results. Remove the disposable notebooks and temporary apps. Verify that `io.github.ispaure.logisticsmobile` is the only Logistics package left on Boox and preserve its data. Report any remaining test packages if cleanup fails.
