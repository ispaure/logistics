# Saved stroke sampling

Newly drawn strokes retain a subset of their original samples before saving.
The goal is to remove redundant input without imposing a fixed sampling rate,
forcing every stroke to the same point count, or replacing handwriting with a
smoothed curve. Opening or saving existing ink does not run this reduction.

## Reference and scope

The completed Paper Pro worksheet contains 1,585 active strokes and 29,237
points. Spacing varies widely; long straight segments can have few points,
while handwriting and changing pressure need more. There are 148 adjacent
same-position pairs with different pressure or width, so distance-only removal
would discard meaningful information. The worksheet's requested slow/fast groups
are spatial task labels, rather than measured elapsed-time records.

The local v6 codec stores X/Y, speed, direction, width and pressure in each
14-byte point before archive compression. It has no per-point clock. These
samples cannot establish the tablet's sampling frequency or firmware selection
algorithm. Logistics does not manufacture firmware speed/direction values from
spacing, or reinterpret those fields on existing strokes.

## New-stroke reduction

`sampling.py` operates after `stroke_points` has calculated calibrated widths.
It retains original rows in their original order and never invents control
points. Endpoints, dots, sharp turns, reversals, tiny loops, pressure/width
extrema and the ends of extrema plateaus are protected. Meaningful stationary
changes remain protected when coordinates are equal either before or after
native float32 encoding. Raw pressure and the native pressure byte are both
checked, including rounding-boundary cases.

The maximum approximation errors, in editor page coordinates before the usual
native coordinate encoding, are:

| Channel | Bound |
| --- | ---: |
| Euclidean position | 0.125 native page units |
| Raw pressure | 1/255 |
| Native byte-rounded pressure | 1/255 |
| Already calculated diameter | 0.0625 native page units |

Pressure and width are bounded both at the original ordered arc-length fraction
and at the nearest position on the retained segment. Native float32 coordinate
precision still applies when writing the file; it is independent of reduction.

The streaming corridor and conservative projection certificate use linear work
and storage, without recursive subdivision or rescanning long stroke histories.
Unencodable positions or lost arc-length precision retain the full input. The
caller supplies validated coordinates and already calibrated widths. Calligraphy retains
all points because its reconstructed nib also depends on neighboring directions.
Reduction runs after contact, rather than changing the live sample stream or
Boox's direct pen preview.

## Existing ink and editing

Unchanged imported native scenes keep their original bytes and point attributes.
Movement does not trigger sampling reduction. Explicit edits such as partial
erasing can create new boundary points under the existing editor rules; this
feature does not promise that every opaque native line attribute survives such
an edit. Save/reopen, recovery and undo/redo must preserve the resulting point
sequence rather than repeatedly reducing it.

## Verification

The independent sampling tests reconstruct omitted samples and check both
parameterizations, codec rounding, stationary dynamics, extrema, tiny loops and
all brush profiles. Negative controls cover discarded dynamics and incorrect
projection handling. Native fixtures separately check imported frames,
translation, partial erasing, recovery and unsupported future objects.
Workflow tests exercise the actual editor, native codec and portable exporter;
point-count or raw-byte reductions are distinguished from compressed ZIP size.

The November 4, 2026 copy-only worksheet audit retained 28,776 of 29,237 points
(461 removed, 1.58%) within all independent reconstruction bounds. All twelve
original scene roundtrips remained byte-identical. This is an audit of the
reducer on copied native rows; the application does not simplify imported ink.
The focused sampler, native preservation, editor workflow and staged-payload
checks passed 34 tests and 88 subtests. The isolated payload check imports only
staged modules and renders editor HTML, including the palm/viewport dependencies;
it does not certify native SDK integration or physical pen behavior.

`measure_sampling.py` emits aggregate worksheet statistics and can evaluate a
candidate on copies without modifying the input archive. Keep private source
files and derived evidence under ignored test results. This is an original
application reduction policy, rather than a reproduction of tablet firmware.
