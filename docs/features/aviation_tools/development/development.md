# Aviation Tools

Aviation Tools incorporates the former `ft` / Flight Tools project by Marc-André Voyer.

## Try a distance display change

On desktop, open **Aviation Tools → Distance**. Enter origin `0, 0` and destination `0, 1`. Change `.2f` to `.3f` in `Python/features/aviation_tools/ui/page.py:distance`. Extend the invalid-input retry fixture to assert the new display. Run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_aviation_tools.py
```

Expect `Distance: 60.040 NM` and the unchanged numeric reference of 60.04046 NM.

`mathUtils/flightUtils.py` owns navigation and wind math. The KIAS chart interpolates flaps-up data and rejects out-of-chart speeds. KTAS → KIAS supports 2,000 ft. The cruise chart selects the closest altitude, adjusts temperature by 2 °C per 1,000 ft, then looks up the closest chart temperature and RPM. Missing combinations fail. These are historical data and approximations.

Import `DatasetBrowser` from `ui.dataset_browser`. Its old `ui.page` import warns and still resolves. CSV resources use package-relative paths. See the [desktop controls](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).
