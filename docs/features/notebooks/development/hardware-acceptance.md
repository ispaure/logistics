# Notebook hardware acceptance

## Prepare disposable notebooks

Run the focused acceptance generator from the repository root with the project
interpreter and `PYTHONPATH=Python:.`:

```sh
.venv/bin/python Python/tests/notebooks/notebook_acceptance_probe.py \
  --output test-results/rmdoc-handoff
```

The two generated `.rmdoc` archives contain synthetic writing only: 36 pages,
two layers, all nine supported tools, three widths and varying pressure.
`acceptance.rmdoc` uses legacy page ordering. `modern.rmdoc` uses `cPages` after
reordering, copying and deleting pages, retaining a deleted-page record.
The generator also tests failed writes, cancellation and process interruption;
its reports and archives belong under ignored test results, outside this wiki.
Retain the archive hashes and exact source identity with the hardware results.
Never substitute generated pressure values for a physical pen measurement.

## Boox physical input and capture-to-export

Use the existing authorized isolated QA setup, with synthetic writing. Record the
Boox model, Android/firmware version, source identity and refresh configuration.
Create a notebook through New document and write with the actual stylus at light,
medium and firm pressure. Check the recorded pressure values, resting-palm and
finger behavior, zoom/pan/rotation geometry, whole-stroke erase, select/move,
undo/redo, save/reopen and background/resume. Add a second page and layer, reorder
pages, copy a page, and export through the installed app's destination picker.
Cancel one export and verify writing still works. Keep the exported archive's hash.

If measuring pen-to-visible-pixel latency, use an external camera and state the
frame rate and measurement method. Software event/animation callback times do not
measure the digitizer or visible E Ink refresh. Compare tools and pressure without
claiming exact reMarkable brush or firmware parity.

## reMarkable native ink editing

Record the actual model and firmware. The manufacturer's
[transfer instructions](https://support.remarkable.com/articles/Knowledge/importing-and-exporting-files)
list `.rmdoc` for USB transfer; companion-app PDF/EPUB import is a separate route.
Verify the supported route again when testing. With the tablet connected by USB,
enable its USB web interface in Settings, open `http://10.11.99.1` on the connected
computer, and import only these disposable archives and the Boox-drawn export.

On the tablet, inspect page order, geometry, layer visibility, tool appearance,
width and pressure variation. Select a generated stroke as ink, move it and erase
it. Repeat on more than one page, and check the reordered/copied modern pages.
Add a tablet-native stroke, export the notebook again, and inspect the result in
Logistics on desktop and mobile. Record exactly which actions succeeded, the
source/export hashes and any incompatibilities. A rendered page or successful
independent library readback alone does not prove native ink editability.

## Finish and clean up

Keep concise observations and raw evidence under ignored test results. Remove
temporary QA apps after saving evidence. On Boox, verify that the only remaining
Logistics package is `io.github.ispaure.logisticsmobile`; preserve that app and its
data. Remove only the disposable notebooks created for this check. Leave the
briefs open if physical input, capture-to-export or reMarkable editing lacks
passing evidence. Physical Apple Pencil behavior likewise requires an actual
iPad/Pencil; simulator pressure events establish only the software path.
