"""Isolated native snow smoke test, using synthetic content only."""
import asyncio
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace
import traceback
from unittest.mock import patch

import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from logisticsmobile.snow import SeasonalSnow


class SnowProbe(toga.App):
    def startup(self):
        self.preferences = SimpleNamespace(values={'seasonal_snow': 'true', 'android_eink': 'false'})
        self.count = 0
        self.status = toga.Label('Snow is on. Tap the button through the flakes.')
        self.button = toga.Button('Tap through snow', on_press=self.tapped, style=Pack(height=60))
        self.main_window = toga.MainWindow(title='Snow QA')
        self.main_window.content = toga.Box(children=[self.status, self.button],
            style=Pack(direction=COLUMN, margin=32))
        self.main_window.show()
        self.check_now()

    def tapped(self, widget, **kwargs):
        self.count += 1
        self.status.text = f'Touch passed through: {self.count}'

    def on_running(self):
        self.loop.create_task(self.check())

    async def check(self):
        await asyncio.sleep(1)
        self.check_now()

    def check_now(self):
        with patch('services.seasonal.date') as calendar:
            calendar.today.return_value = date(2026, 12, 15)
            self.check_in_season()

    def check_in_season(self):
        result = {'success': False}
        try:
            previous = getattr(self, 'seasonal_snow', None)
            if previous is not None:
                previous.dispose()
            self.seasonal_snow = SeasonalSnow(self)
            snow = self.seasonal_snow
            snow.refresh()
            assert snow.view is not None, 'No native snow attached'
            ios = type(self._impl).__module__.startswith('toga_iOS.')
            if ios:
                assert not snow.view.isUserInteractionEnabled()
                assert len(snow.view.layer.sublayers) == 28
                for layer in snow.view.layer.sublayers:
                    assert layer.animationForKey('snowfall') is not None
            else:
                assert not snow.view.isClickable()
                assert not snow.view.isFocusable()
            result['native_overlay_attached'] = True
            self.preferences.values['android_eink'] = 'true'
            snow.refresh()
            assert snow.view is None
            result['contrast_removes_overlay'] = True
            self.preferences.values['android_eink'] = 'false'
            snow.refresh()
            assert snow.view is not None
            self.preferences.values['seasonal_snow'] = 'false'
            snow.refresh()
            assert snow.view is None
            result['switch_removes_overlay'] = True
            self.preferences.values['seasonal_snow'] = 'true'
            snow.refresh()
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'snow-result.json').write_text(json.dumps(result, indent=2))
        print('SNOW_RESULT=' + json.dumps(result), flush=True)


def main():
    return SnowProbe('Snow QA', 'io.github.ispaure.logisticssnowqa')
