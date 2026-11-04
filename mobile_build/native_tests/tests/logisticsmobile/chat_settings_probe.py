"""Native provider form, destination-local navigation and feature-tab projection."""
import asyncio
import json
from pathlib import Path
import traceback
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from commonUtils.runtime.platform import get_os, OS
from mobile.app import LogisticsMobile
from features.lm.mobile.on_device import MODELS, platform_provider
from . import start_native_check
from .fixtures import capture_window
from .rotation_checks import rotate

TEST_STAGE = TestStage.REGRESSION


class ChatSettingsProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'chat-settings-fixtures'
        super().startup()

    def on_running(self):
        start_native_check(self, self.probe)

    async def rotate_probe(self, orientation):
        if get_os() is OS.ANDROID:
            # API 36 tablets may ignore an Activity's orientation request.
            # The disposable-device driver applies this requested physical pose.
            (Path(self.paths.cache) / 'creation-orientation').write_text(orientation)
        await rotate(self, orientation, settle=.4)

    def check_rail_icons(self):
        if get_os() is not OS.ANDROID or self.native_host.adapter.mode != 'rail':
            return
        from android.graphics import Rect
        from com.google.android.material import R as MaterialR
        rail = self.native_host.adapter.rail
        assert rail.getWidth() - rail.getPaddingLeft() - rail.getPaddingRight() >= rail.getItemIconSize()
        for index in range(rail.getMenu().size()):
            item = rail.getMenu().getItem(index)
            if not item.isVisible():
                continue
            view = rail.findViewById(item.getItemId())
            icon = view.findViewById(MaterialR.id.navigation_bar_item_icon_view)
            bounds = Rect(0, 0, icon.getWidth(), icon.getHeight())
            rail.offsetDescendantRectToMyCoords(icon, bounds)
            assert bounds.left >= 0 and bounds.right <= rail.getWidth(), str(bounds)

    async def probe(self, app):
        output = Path(self.paths.cache)
        report = dict(success=False, cases=[], samples=[])
        try:
            self.show_settings()
            self.settings_navigation.choose('LM Chat')
            self.show_chat_configuration(destination='settings')
            owner = self.chat_controller()
            assert self.native_host.state.destination == 'settings'
            assert self.routes.screens['settings'][-1][0] == 'chat-settings'
            self.chat_url.value = 'http://127.0.0.1:1234'
            for orientation in ('portrait', 'landscape-left'):
                await self.rotate_probe(orientation)
                self.resize_workspace()
                await asyncio.sleep(.3)
                self.check_rail_icons()
                assert self.routes.screens['settings'][-1][0] == 'chat-settings'
                await capture_window(self, output / f'chat-settings-{orientation}-server.png')
                owner.chat_manual_toggle.on_press()
                owner.chat_generation_toggle.on_press()
                self.chat_model.value = 'example-model'
                self.chat_context.value = '8192'
                await asyncio.sleep(.2)
                self.chat_config_view.vertical_position = self.chat_config_view.max_vertical_position
                await asyncio.sleep(.2)
                save = owner.chat_config_save._impl.native
                sample = dict(orientation=orientation, context=self.chat_context.value)
                if get_os() is OS.IOS:
                    window = self.main_window._impl.native
                    rect = save.convertRect(save.bounds, toView=window)
                    sample.update(x=float(rect.origin.x), width=float(rect.size.width))
                    assert sample['x'] >= 0 and sample['x'] + sample['width'] <= window.bounds.size.width
                else:
                    from android.graphics import Rect
                    visible = Rect()
                    assert save.getGlobalVisibleRect(visible), 'Save settings is unreachable'
                    sample.update(width=int(save.getWidth()), height=int(save.getHeight()))
                    assert sample['width'] > 0 and sample['height'] > 0
                report['samples'].append(sample)
                await capture_window(self, output / f'chat-settings-{orientation}-limits.png')
                owner.chat_manual_toggle.on_press()
                owner.chat_generation_toggle.on_press()
                local = platform_provider()
                assert local
                self.chat_provider.value = MODELS[local]
                await asyncio.sleep(.2)
                assert owner.chat_server_section not in owner.chat_provider_content.children
                await capture_window(self, output / f'chat-settings-{orientation}-device.png')
                self.chat_provider.value = 'OpenAI-compatible server'
                assert self.chat_model.value == 'example-model'
            with patch('features.lm.mobile.ui.ChatClient') as client:
                self.save_chat_configuration()
                client.assert_not_called()
            assert self.native_host.state.destination == 'settings'
            assert not any(route == 'chat-settings' for route, *_ in self.routes.screens['settings'])
            report['cases'].append('settings-origin-provider-form-rotation-save')
            self.show_chat()
            self.chat_prompt.value = 'Retained draft'
            self.show_chat_configuration()
            owner.chat_config_back.on_press()
            assert self.native_host.state.destination == 'chat'
            assert self.chat_prompt.value == 'Retained draft'
            self.show_settings()
            self.settings_navigation.choose('Features')
            self.set_feature_enabled('lm', False)
            await asyncio.sleep(.3)
            assert not self.navigation.content[3].enabled
            if get_os() is OS.IOS:
                assert len(list(self.native_host.adapter.controller.viewControllers)) == 4
            else:
                for bar in (self.native_host.adapter.bottom, self.native_host.adapter.rail):
                    if bar is not None:
                        assert not bar.getMenu().getItem(3).isVisible()
            await capture_window(self, output / 'chat-settings-hidden.png')
            self.set_feature_enabled('lm', True)
            await asyncio.sleep(.3)
            assert self.navigation.content[3].enabled
            self.show_chat()
            assert self.chat_prompt.value == 'Retained draft'
            report['cases'].append('chat-origin-back-and-feature-hide-restore-retains-draft')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'chat-settings-result.json').write_text(json.dumps(report, indent=2))


def main():
    return ChatSettingsProbe('Chat Settings QA', 'io.github.ispaure.logisticsstorageqa')
