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

For Apple Pencil delivery, use an actual iPad/Pencil for pressure, hover and palm checks.

## reMarkable native ink editing

Enable the USB web interface, open `http://10.11.99.1` on the connected computer and import the synthetic archives and Boox export. Check [supported transfer routes](https://support.remarkable.com/articles/Knowledge/importing-and-exporting-files).

On the tablet verify order, geometry, layers and tool appearance. Select, move and erase native ink on multiple pages, including reordered/copied pages. Add a tablet stroke, re-export and inspect it in desktop and mobile Logistics. Record successful actions, incompatibilities and archive hashes.

## Cleanup

Save evidence under ignored test results. Remove the disposable notebooks and temporary apps. Verify that `io.github.ispaure.logisticsmobile` is the only Logistics package left on Boox and preserve its data. Report any remaining test packages if cleanup fails.
