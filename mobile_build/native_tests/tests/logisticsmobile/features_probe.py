"""Native mobile switches, persisted choices and disabled-document admission."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

import toga
from mobile.app import LogisticsMobile
from mobile.preferences import Preferences
from mobile.document_choices import available_choices
from services.mobile_features import FEATURES, BY_NAME, enabled
from services.documents.mobile_notebooks import open_notebook

BUNDLE = 'io.github.ispaure.logisticsfeaturesqa'


def widgets(view):
    yield view
    if isinstance(view, toga.ScrollContainer):
        if view.content is not None:
            yield from widgets(view.content)
    else:
        for child in view.children:
            yield from widgets(child)


class FeaturesProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('features-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not hasattr(self, 'features_check'):
            self.features_check = self.loop.create_task(self.check_features())

    async def wait_refresh(self, old):
        for _ in range(100):
            if self.settings_navigation is not old:
                await asyncio.sleep(.1)
                return
            await asyncio.sleep(.1)
        raise AssertionError('Feature settings did not refresh.')

    async def check_features(self):
        report = dict(success=False, cases=[], backend=type(self._impl).__module__)
        try:
            # Finish the app's initial local credential restore before testing
            # the user-facing refusal to interrupt an active storage operation.
            for _ in range(100):
                if not self.cloud_busy:
                    break
                await asyncio.sleep(.1)
            assert all(self.feature_enabled(feature.name) for feature in FEATURES)
            self.show_settings()
            self.settings_navigation.choose('Features')
            report['cases'].append('all-current-features-default-on')
            for feature in FEATURES:
                if feature.name == 'rclone':
                    self.show_view(toga.Box(), destination='files', route='remote-browser', title='Remote files')
                    self.show_settings()
                    self.settings_navigation.choose('Features')
                nav = self.settings_navigation
                control = nav.sections['Features'].feature_switches[feature.name]
                assert control.value
                control.value = False
                await self.wait_refresh(nav)
                assert not self.feature_enabled(feature.name), (feature.name, self.settings_status.text)
                assert not enabled(Preferences(self.preferences.path.parent), feature.name)
                if feature.name == 'rclone':
                    assert not self.routes.screens['files'], 'Disabled remote browser remained on the native stack'
            assert not available_choices(self)
            assert not await open_notebook(self, name='Blocked notebook')
            assert not getattr(self, '_notebook_views', {})
            report['cases'].append('native-switches-save-and-disabled-notebook-does-not-publish')
            assert not any(self.feature_enabled(name) for name in BY_NAME)
            self.show_settings()
            self.settings_navigation.choose('Help')
            button = next(widget for widget in widgets(self.settings_navigation.sections['Help'])
                if isinstance(widget, toga.Button) and widget.text == 'Mobile documentation')
            button.on_press()
            owner = self.documentation
            assert owner.title.text == 'Logistics on mobile', owner.title.text
            first = owner.path
            owner.follow_link(owner.web, 'settings/settings.md')
            assert owner.title.text == 'Mobile settings', owner.title.text
            owner.show_page_search()
            owner.search.value = 'Features'
            owner.mode.value = 'Page text'
            owner.filter()
            assert owner.rows.children
            assert owner.back() and owner.path == first
            assert not any(self.feature_enabled(name) for name in BY_NAME)
            self.routes.back()
            report['cases'].append('settings-markdown-guide-links-search-and-history-with-all-features-off')
            self.show_settings()
            self.settings_navigation.choose('Features')
            nav = self.settings_navigation
            button = next(widget for widget in widgets(nav.sections['Features'])
                if isinstance(widget, toga.Button) and widget.text == 'Enable all features')
            button.on_press()
            await self.wait_refresh(nav)
            assert all(self.feature_enabled(feature.name) for feature in FEATURES)
            assert 'rmdoc' in dict(available_choices(self)).values()
            report['cases'].append('enable-all-restores-every-feature')
            # Native notebook tests can opt in explicitly through this same API.
            self.set_feature_enabled('notebooks', True, refresh=False)
            assert all(enabled(Preferences(self.preferences.path.parent), feature.name) for feature in FEATURES)
            await asyncio.sleep(.3)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'features-result.json').write_text(json.dumps(report, indent=2))


def main():
    return FeaturesProbe('Features QA', BUNDLE)
