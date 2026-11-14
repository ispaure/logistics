# Aviation Tools

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

The former `ft` / Flight Tools project is now a Logistics feature with its own
**Aviation Tools** tab. Developed by Marc-André Voyer.
See the [user guide](../user/user.md) and [UI architecture](../../../development/features.md).

`register()` contributes a lazy page factory through the normal feature registry.
No second QApplication, event loop, launcher, dependency environment or copy of
commonUtils is required. Settings → Features controls the tab with the standard
saved feature lifecycle; disabling and enabling retains the page's inputs.

## Migrated functionality

- Coordinate distance and true/magnetic course.
- Wind correction angle, true/magnetic heading and ground-speed estimates.
- KTAS → KIAS (the original 2,000 ft approximation).
- KIAS → KCAS (linear interpolation, flaps up).
- Cruise performance (nearest chart values).
- All aircraft, airport, airspeed calibration and cruise performance CSV files,
  browsable in the page instead of printed only to the console.

The `mathUtils`, `plane` and `location` modules retain the original backend APIs
and formulas, with package-scoped imports. `resources.DATA_DIR` resolves data from
the feature directory regardless of the current working directory. CSV imports
use Logistics' shared CSVFile API. Invalid magnetic direction, unknown aircraft,
unknown airport and unsupported weather/chart methods raise recoverable errors
instead of exiting the application. The tab presents buttons that open modeless, feature-owned tool windows. Windows
are created on demand and retained by the page, preserving inputs when closed
and reopened. The layout-based forms display input errors and support copying
results. Aircraft / Airports opens its own read-only reference window.

This migration preserves the original calculation limitations. In particular,
the wind tools use the original vector approximation rather than an exact solved
wind triangle, KTAS conversion only supports 2,000 ft, and cruise performance uses
nearest values rather than interpolation. The supplied data is historical and
is not refreshed from external sources. Weight and balance, navigation charts,
flight plans, a pilot logbook and PDF export were listed as ideas in the old README
but had no implementation to migrate.

## Source ownership and platform boundary

- `Python/features/aviation_tools/__init__.py` registers the lazy desktop page.
- `ui/page.py` owns the seven calculator forms, result and error presentation,
  and the retained modeless tool windows. **Aircraft / Airports** opens the
  read-only `DatasetBrowser` in `ui/dataset_browser.py`.
- `mathUtils/flightUtils.py` owns coordinate validation, course normalization,
  distance, wind and airspeed formulas; `weatherUtils.py` owns the temperature helpers.
- `plane/planeUtils.py` selects registrations/models from the bundled directories.
  `planeAirspeedCalibration.py` interpolates between flaps-matched chart points;
  values outside the chart return no result and the UI presents an error.
- `plane/planeCruisePerformance.py` chooses the nearest altitude, temperature and
  RPM independently, then looks for a row with that combination. It first applies
  the stored 2 °C per 1,000 ft lapse helper to the sea-level temperature at the
  selected altitude. A missing combination returns no result and is reported by
  the UI; it does not interpolate or synthesize a row.
- `location/locationUtils.py` loads airport CSV rows and resolves codes without
  case sensitivity. `resources.py` owns the package-relative data path.

There is no mobile adapter or `mobile_sources.json` in this feature. It is absent
from `mobile_build/tools.py`'s mobile source-owner list. Its PySide6 desktop page
is not a mobile destination; see [mobile availability](../user_mobile/user_mobile.md).
Retained dialog state lasts only as long as the desktop page instance.

## Validation

`Python/tests/integrations/test_aviation_tools.py` covers feature discovery/tab retention,
every migrated calculator, popup lifetime/input retention, input error recovery, reference outputs, all datasets
and loading from an unrelated working directory.

These test files describe executable regression scope; their presence is not
evidence of current device or release acceptance. The documentation audit used
source/test inspection and static checks only, with no Qt or device run.
