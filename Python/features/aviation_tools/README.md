# Aviation Tools

The former `ft` / Flight Tools project is now a Logistics feature with its own
**Aviation Tools** tab. Developed by Marc-André Voyer.
See the [user guide](user_docs/index.md) and [UI architecture](../UI_ARCHITECTURE.md).

`register()` contributes a lazy page factory through the normal feature registry.
No second QApplication, event loop, launcher, dependency environment or copy of
commonUtils is required. Settings → Features controls the tab with the standard
session-only feature lifecycle; disabling and enabling retains the page's inputs.

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

The former Python installation troubleshooting PDF is retained in `legacy_docs/`
for reference. Standalone launcher/config/environment files and the old fixed-size
UI are superseded by Logistics. The duplicate commonUtils tree is superseded by
the existing shared submodule; it is not merged into that submodule.

## Validation

`Python/tests/test_aviation_tools.py` covers feature discovery/tab retention,
every migrated calculator, popup lifetime/input retention, input error recovery, reference outputs, all datasets
and loading from an unrelated working directory.
