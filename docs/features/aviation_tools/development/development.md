# Aviation Tools

Aviation Tools calculates distances, headings and aircraft performance on
desktop. It incorporates the former `ft` / Flight Tools project, developed by
Marc-André Voyer.

## Try a distance display change

1. Open desktop Logistics and enable **Aviation Tools** in **Settings → Features**
   if needed. Open **Aviation Tools → Distance**. Use origin latitude and
   longitude `0, 0` and destination latitude and longitude `0, 1`. Select
   **Calculate** and expect `Distance: 60.04 NM`.
2. In `Python/features/aviation_tools/ui/page.py`, change the format in
   `distance()` from `.2f` to `.3f`. Relaunch and repeat the calculation.
   Expect `Distance: 60.040 NM`. Keep the full-precision calculation in
   `mathUtils/flightUtils.py`.
3. In `Python/tests/integrations/test_aviation_tools.py`, extend
   `test_invalid_inputs_report_errors_and_allow_retry`. After its invalid inputs,
   enter those four synthetic coordinates and assert the complete new result
   string. Keep the separate numeric reference assertion for `60.04046` NM.

From the repository root with the desktop environment set up, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_aviation_tools.py
```

Expect seven passing tests, including recovery after invalid input and the
numeric distance reference. See the [desktop guide](../user/user.md) for the
other calculator controls.

## Migrated functionality

- Distance, true and magnetic course, wind correction, true and magnetic heading,
  and ground speed use `mathUtils/flightUtils.py`. Wind uses the original vector
  approximation. Input validation rejects out-of-range coordinates, non-finite
  numbers and invalid magnetic directions. Native units appear on each form.
- The true-to-indicated airspeed approximation (KTAS → KIAS) supports 2,000 ft.
  `plane/planeAirspeedCalibration.py` converts indicated to calibrated airspeed
  (KIAS → KCAS) by interpolating between flaps-matched points. The UI uses flaps
  up and reports speeds outside the chart as errors.
- `plane/planeCruisePerformance.py` picks the closest altitude, then uses
  `mathUtils/weatherUtils.py` to adjust the sea-level temperature by 2 °C per
  1,000 ft at that altitude. It picks the closest reference temperature and
  RPM from the chart's value lists and looks for one row at the resulting
  combination. A missing combination displays an error. This lookup uses
  historical chart values without interpolation.

## Source ownership and platform boundary

`Python/features/aviation_tools/__init__.py` registers the desktop page with a
factory that imports it on demand. `ui/page.py` owns the tool definitions and
`Calculator.run()` handles conversion, result display and recoverable errors.
Each calculator opens in a modeless window, so several can stay open at once.
Closing a tool or disabling and re-enabling the feature preserves inputs while
the same page instance lives.

**Aircraft / Airports** opens the read-only `DatasetBrowser` in
`ui/dataset_browser.py`. Import it from that module. The old
`features.aviation_tools.ui.page.DatasetBrowser` import returns the same class
with a `FutureWarning`. `resources.DATA_DIR` is package-relative.
`location/locationUtils.py` resolves airport codes case-insensitively, and
`plane/planeUtils.py` selects supplied aircraft and models. Both read the
bundled historical CSV data through commonUtils. Unknown airport and aircraft
codes raise `ValueError`. The feature ships without a data refresh service.

The page uses PySide6 and runs in the desktop application. The mobile source
allowlist in `mobile_build/tools.py` omits this feature. See
[mobile availability](../user_mobile/user_mobile.md) and the shared
[feature conventions](../../../development/features.md).

## Validation

The worked check covers desktop registration and page retention, calculator
windows, error recovery, numeric references and every bundled dataset from a
different working directory. Run
`python3 dev.py test desktop --exact-file Python/tests/aviation_tools/test_aviation_tools_boundaries.py`
for coordinate bounds, zero distance and magnetic course wrapping. Those
fixtures verify the implemented formulas and bundled data access. Operational
validation of the historical data and approximations is outside their scope.
