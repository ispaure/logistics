"""Native folded chat, keyboard, retained draft and loopback streaming checks."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from unittest.mock import patch

from mobile.app import LogisticsMobile
from . import start_native_check
from .web_checks import wait_for_text


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'chat-laptop-fixtures'
        super().startup()

    def on_running(self):
        start_native_check(self, self.check)

    async def check(self, app):
        report = dict(success=False, scope='Real UIKit keyboard and WebKit with injected horizontal hinge', samples=[])
        try:
            from mobile.chat_fixture import fixture_server
            self.show_chat()
            for _ in range(100):
                if self.chat_current is not None:
                    break
                await asyncio.sleep(.05)
            owner = self.chat_controller()
            workspace = self.chat_workspace._impl.native
            seam = float(workspace.bounds.size.height) * .48
            gap = 20
            def geometry(controller):
                return float(workspace.bounds.size.height), seam, gap
            def frame(widget):
                native = widget._impl.native
                rect = native.convertRect(native.bounds, toView=workspace)
                return [float(rect.origin.y), float(rect.origin.y + rect.size.height)]
            def sample(name):
                from features.lm.mobile.laptop import visible_height
                data = dict(visible=visible_height(owner, float(workspace.bounds.size.height)), name=name, workspace=float(workspace.bounds.size.height),
                    transcript=frame(self.chat_transcript_card), composer=frame(self.chat_composer),
                    prompt=frame(self.chat_prompt), send=frame(self.chat_send), keyboard=self.native_host.adapter.keyboard_inset)
                report['samples'].append(data)
                assert data['composer'][1] <= data['visible'] + 1, data
                assert data['send'][1] <= data['composer'][1] + 1, data
                assert data['transcript'][1] <= data['composer'][0] + 1, data
                assert data['composer'][1] <= seam + 1 or data['composer'][0] >= seam + gap - 1, data
                return data
            with fixture_server() as (url, started, release, requests):
                self.chat_url.value = url
                self.chat_model.value = 'fixture-model'
                self.save_chat_configuration()
                from .rotation_checks import rotate
                for orientation in ('portrait', 'landscape-left', 'landscape-right', 'portrait'):
                    await rotate(self, orientation, settle=.4)
                    self.show_chat_messages()
                    self.chat_prompt._impl.native.becomeFirstResponder()
                    await asyncio.sleep(.7)
                    self.chat_prompt._impl.native.insertText(' typing')
                    await asyncio.sleep(.2)
                    window = self.main_window._impl.native
                    keyboard = window.convertRect(self.native_host.adapter.keyboard_frame,
                        fromCoordinateSpace=window.screen.coordinateSpace)
                    native = self.chat_composer._impl.native
                    rect = native.convertRect(native.bounds, toView=window)
                    bottom = float(rect.origin.y + rect.size.height)
                    assert bottom <= float(keyboard.origin.y) + 1, (orientation, bottom, keyboard)
                    assert self.chat_prompt._impl.native.isFirstResponder(), orientation
                    report['samples'].append(dict(name='regular-' + orientation,
                        composer_bottom=bottom, keyboard_top=float(keyboard.origin.y)))
                    self.main_window._impl.native.endEditing(True)
                    await asyncio.sleep(.4)
                seam = float(workspace.bounds.size.height) * .48
                with patch('features.lm.mobile.laptop.chat_region', side_effect=geometry):
                    self.render_chat_workspace()
                    await asyncio.sleep(.4)
                    self.chat_prompt.value = 'Draft survives folding'
                    sample('laptop')
                    self.toggle_chat_conversations()
                    await asyncio.sleep(.2)
                    assert self.chat_sidebar.parent is owner.laptop.deck
                    assert self.chat_transcript_card.parent is self.chat_workspace
                    self.toggle_chat_conversations()
                    assert self.chat_prompt.value == 'Draft survives folding'
                    self.chat_prompt._impl.native.becomeFirstResponder()
                    await asyncio.sleep(.8)
                    self.render_chat_workspace()
                    self.chat_prompt._impl.native.insertText(' and typing')
                    await asyncio.sleep(.3)
                    assert sample('keyboard')['keyboard'] > 100
                    self.main_window._impl.native.endEditing(True)
                    await asyncio.sleep(.5)
                    self.render_chat_workspace()
                    assert self.chat_prompt.value.endswith(' and typing')
                    sample('keyboard-dismissed')
                    await self.send_chat()
                    await wait_for_text(self.chat_transcript, 'Native fixture reply')
                    assert self.chat_current['messages'][-1]['status'] == 'complete'
                    self.chat_prompt.value = 'Next draft retained'
                    report['streamed_reply'] = True
                self.render_chat_workspace()
                await asyncio.sleep(.2)
                assert self.chat_composer.parent is self.chat_messages
                assert self.chat_prompt.value == 'Next draft retained'
                with patch('features.lm.mobile.laptop.chat_region', side_effect=geometry):
                    self.render_chat_workspace()
                    await asyncio.sleep(.3)
                    sample('final-laptop')
                    self.toggle_chat_conversations()
                    await asyncio.sleep(.2)
                    listing = self.chat_conversation_list
                    assert listing.data[0].folder
                    listing.tree_actions.toggle(listing.data[0])
                    await asyncio.sleep(.2)
                    assert not listing.data[0].tree_expanded
                    listing.tree_actions.toggle(listing.data[0])
                    await asyncio.sleep(.2)
                    assert listing.data[1].key == self.chat_current['id']
                    self.toggle_chat_conversations()
                    from .fixtures import capture_window
                    await capture_window(self, Path(self.paths.cache) / 'chat-laptop.png')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'chat-laptop-result.json').write_text(json.dumps(report, indent=2))


def main():
    return Probe('Chat laptop QA', 'io.github.ispaure.logisticsstorageqa')
