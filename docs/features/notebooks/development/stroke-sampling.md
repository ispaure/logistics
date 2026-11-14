# Saved stroke sampling

`Python/features/notebooks/sampling.py` reduces new strokes after calibrated width calculation and pen-up. It retains original rows and protects endpoints, dots, turns, tiny loops, extrema and meaningful stationary changes, including after float32 or pressure-byte rounding. Calligraphy retains all points. Unencodable input or lost arc-length precision retains the full sequence.

Position error caps at 0.125 page units, raw and byte-rounded pressure at 1/255, and diameter at 0.0625. Check pressure and diameter at both ordered arc length and nearest retained-segment projection. Existing ink and movement bypass reduction. Partial erasure can introduce new endpoints.

The [calibration worksheet](brush-calibration.md#measured-widths-and-colors) has 29,237 points and 148 adjacent stationary pairs with changing width or pressure. v6 points lack timestamps. A copy-only reduction retained 28,776 points within bounds. Ordinary import/save preserved all twelve scene streams. Use `measure_sampling.py` for aggregate checks on copies.

From the configured checkout root:

```sh
python3 dev.py test desktop --exact-file Python/tests/notebooks/test_stroke_sampling.py
```

Expect both reconstruction parameterizations, stationary dynamics and codec-rounding checks to pass.
