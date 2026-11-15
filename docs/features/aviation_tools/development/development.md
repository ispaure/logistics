# Aviation Tools

The desktop feature presents flight calculations and supplied reference data.
Its UI parses inputs and displays results; the calculation modules own the
numerical behavior and data limits.

Aviation Tools incorporates the former `ft` / Flight Tools project by Marc-André Voyer.

## Follow a distance calculation

Open **Aviation Tools → Distance** and enter origin `0, 0` and destination
`0, 1`. `Python/features/aviation_tools/ui/page.py:distance` formats the result
from the navigation calculation. The focused fixtures check the numerical
reference (about 60.04046 NM), invalid input and retry without needing a service:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_aviation_tools.py
```

`mathUtils/flightUtils.py` owns navigation and wind math. The KIAS chart interpolates flaps-up data and rejects out-of-chart speeds. KTAS → KIAS supports 2,000 ft. The cruise chart selects the closest altitude, adjusts temperature by 2 °C per 1,000 ft, then looks up the closest chart temperature and RPM. Missing combinations fail. These are historical data and approximations.

Import `DatasetBrowser` from `ui.dataset_browser`. Its old `ui.page` import warns and still resolves. CSV resources use package-relative paths. See the [desktop controls](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).
