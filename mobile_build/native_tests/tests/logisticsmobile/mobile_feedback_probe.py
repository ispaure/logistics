"""Native acceptance for feedback 18–20 using isolated Notes and Settings data."""
import asyncio
import faulthandler
import json
from pathlib import Path
import sys
from threading import Event
import time
import traceback

import toga
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from mobile.app import LogisticsMobile
from mobile.obsidian import open_vault
from . import enable_native_fault_log
from .fixtures import capture_window
from .rotation_checks import rotate

TEST_STAGE = TestStage.REGRESSION


def descendants(widget):
    yield widget
    for child in widget.children:
        yield from descendants(child)


def button(root, title):
    return next(w for w in descendants(root) if isinstance(w, toga.Button)
                and w.text.replace('\n', ' ') == title)


def tap(widget):
    if type(widget._impl).__module__.startswith('toga_android.'):
        assert widget._impl.native.performClick()
    else:
        widget._impl.native.sendActionsForControlEvents(1 << 6)


def frame(widget):
    native = widget._impl.native
    if type(widget._impl).__module__.startswith('toga_android.'):
        from java import jarray, jint
        xy = jarray(jint)(2)
        native.getLocationOnScreen(xy)
        scale = widget._impl.scale_in(1)
        return [float(xy[0]) / scale, float(xy[1]) / scale,
                native.getWidth() / scale, native.getHeight() / scale]
    rect = native.convertRect(native.bounds, toView=None)
    return [float(rect.origin.x), float(rect.origin.y), float(rect.size.width), float(rect.size.height)]


async def until(predicate, message, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, message
        await asyncio.sleep(.05)


class FeedbackProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'feedback-fixture'
        super().startup()

    def on_running(self):
        self._feedback_fault_log = enable_native_fault_log(self.paths.cache)
        faulthandler.dump_traceback_later(30, repeat=True, file=self._feedback_fault_log)
        self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache)
        android = type(self._impl).__module__.startswith('toga_android.')
        report = dict(success=False, platform='android' if android else 'ios', runtime_platform=sys.platform, items={})
        owner = None
        release = Event()
        try:
            root = output / 'Feedback Library'
            (root / '.obsidian').mkdir(parents=True, exist_ok=True)
            (root / 'Folder').mkdir(exist_ok=True)
            (root / 'Home.md').write_text('# Home\n\nFeedback fixture.')
            (root / 'Folder/Note.md').write_text('# Nested note')
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            report['items']['18'] = []
            for orientation in ('portrait', 'landscape-left'):
                try:
                    await rotate(self, orientation, settle=.5)
                except AssertionError:
                    if android:
                        activity = self._impl.native
                        report['rotation_failure'] = dict(orientation=orientation,
                            requested=int(activity.getRequestedOrientation()),
                            configuration=int(activity.getResources().getConfiguration().orientation),
                            window=[self.main_window.size.width, self.main_window.size.height],
                            native=frame(owner.tree))
                    raise
                owner.sidebar.show_sidebar()
                await asyncio.sleep(.4)
                assert not any(hasattr(owner, name) for name in
                               ('panel_footer', 'panel_identity', 'panel_metadata', 'panel_menu', 'root_drop_button'))
                assert owner.tree.children[1:3] == [owner.panel_actions, owner.panel_body]
                commands = [child for child in owner.panel_actions.children if isinstance(child, toga.Button)]
                assert [w.accessible_name for w in commands] == ['New document', 'New folder', 'Collapse all folders']
                pane, first, last = frame(owner.tree), frame(commands[0]), frame(commands[-1])
                tabs, row, body = frame(owner.panel_tabs['Files']), frame(owner.panel_actions), frame(owner.panel_body)
                assert all(r[2] > 0 and r[3] > 0 for r in (pane, first, last, tabs, row, body)), (pane, first, last, tabs, row, body)
                assert abs((first[0] + last[0] + last[2]) / 2 - (pane[0] + pane[2] / 2)) <= 2, (pane, first, last)
                assert tabs[1] + tabs[3] <= row[1] + 2 and row[1] + row[3] <= body[1] + 2, (tabs, row, body)
                await owner.toggle_folder('Folder')
                tap(commands[-1])
                await asyncio.sleep(.2)
                assert owner.expanded == {owner.root}, owner.expanded
                await capture_window(self, output / f'feedback-notes-{orientation}.png')
                tap(owner.panel_tabs['Search'])
                await asyncio.sleep(.2)
                assert owner.panel_tab == 'Search' and owner.panel_actions.parent is owner.tree
                tap(owner.panel_tabs['Calendar'])
                await until(lambda: owner.calendar_task is not None and owner.calendar_task.done(), 'Calendar did not load')
                assert owner.panel_tab == 'Calendar' and owner.panel_actions.parent is owner.tree
                tap(owner.panel_tabs['Files'])
                report['items']['18'].append(dict(orientation=orientation, pane=pane, commands=[first, last]))
            owner.dispose()
            owner = None
            await rotate(self, 'portrait', settle=.5)
            self.show_settings()
            nav = self.settings_navigation
            tap(nav.buttons['Help'])
            await asyncio.sleep(.3)
            def check_title(view, *, category_in_detail=False):
                from mobile.settings.titles import bar_shows_title, title_slot
                content, (_, label) = title_slot(view)
                in_bar = False
                if not android and not category_in_detail:
                    adapter = self.native_host.adapter
                    navigation = adapter.navigation_for('settings')
                    in_bar = bar_shows_title(navigation, adapter.content_controller('settings'),
                                             label._settings_page_title)
                assert (label.parent is content) != in_bar, label._settings_page_title
                if in_bar:
                    assert label not in content.children
                return in_bar

            help_view = nav.options['Help']
            help_page = nav.sections['Help']
            report['settings_titles'] = {'help_portrait': check_title(help_view, category_in_detail=nav.wide)}
            entries = [w for w in descendants(help_page) if isinstance(w, toga.Button)]
            assert entries[0].text == 'Mobile documentation', [w.text for w in entries]
            await capture_window(self, output / 'feedback-help.png')
            if android:
                assert not any('Developer' in w.text for w in entries)
                more = button(help_page, 'More +')
                tap(more)
                await asyncio.sleep(.3)
                developer = button(help_page, 'Android Developer Settings…')
                assert frame(developer)[2] > 0 and frame(developer)[3] > 0
                await capture_window(self, output / 'feedback-more.png')
                tap(more)
                assert not any('Developer' in w.text for w in descendants(help_page) if isinstance(w, toga.Button))
            else:
                assert not any('More' in w.text or 'Developer' in w.text for w in entries)
            report['items']['20'] = dict(documentation_first=True, developer_hidden_by_default=True)
            from mobile.settings import categories
            original = categories.build_information
            entered = Event()
            def delayed(version):
                entered.set()
                assert release.wait(20), 'Probe failed to release build lookup'
                return original(version)
            categories.build_information = delayed
            try:
                started = time.monotonic()
                tap(button(help_page, 'About'))
                await until(entered.is_set, 'About build lookup did not start')
                assert time.monotonic() - started < 2, 'About blocked presentation'
                assert self.routes.screens['settings'][-1][0] == 'settings-about'
                assert 'Loading build information' in self.build_version_label.text
                await capture_window(self, output / 'feedback-about-loading.png')
                self.routes.back()
                assert help_view.parent is (nav.detail if nav.wide else self.routes.body('settings'))
                release.set()
                await asyncio.wait_for(self.build_information_task, 15)
            finally:
                release.set()
                categories.build_information = original
            tap(button(help_page, 'About'))
            await asyncio.sleep(.3)
            about = nav.sections['About']
            labels = list(descendants(about))
            license_button = button(about, 'Open-source licenses')
            assert labels.index(self.build_version_label) < labels.index(license_button)
            platform_label = 'Platform: Android' if android else 'Platform: iOS / iPadOS'
            assert platform_label in self.build_version_label.text and 'Source:' in self.build_version_label.text, self.build_version_label.text
            report['settings_titles']['about_portrait'] = check_title(nav.options['About'])
            await capture_window(self, output / 'feedback-about-ready.png')
            license_started = time.monotonic()
            tap(license_button)
            assert time.monotonic() - license_started < 10, 'License controls blocked presentation'
            await until(lambda: self.routes.screens['settings'][-1][0] == 'open-source-licenses', 'Licenses did not open')
            license_view = self.routes.screens['settings'][-1][1]
            await until(lambda: frame(license_view)[2] > 0 and frame(license_view)[3] > 0,
                        'License page did not acquire native bounds')
            await asyncio.sleep(.3)
            report['settings_titles']['licenses_portrait'] = check_title(license_view.children[-1])
            await capture_window(self, output / 'feedback-licenses.png')
            await rotate(self, 'landscape-left', settle=.5)
            report['settings_titles']['licenses_landscape'] = check_title(license_view.children[-1])
            await capture_window(self, output / 'feedback-licenses-landscape.png')
            self.routes.back()
            assert self.routes.screens['settings'][-1][0] == 'settings-about'
            await asyncio.sleep(.3)
            report['settings_titles']['about_after_back'] = check_title(nav.options['About'])
            self.routes.back()
            await asyncio.sleep(.3)
            report['settings_titles']['help_after_back'] = check_title(help_view, category_in_detail=nav.wide)
            assert help_view.parent is (nav.detail if nav.wide else self.routes.body('settings'))
            report['items']['19'] = dict(immediate_feedback=True, back_while_loading=True,
                build_before_licenses=True, installed_build=self.build_version_label.text, license_back=True,
                license_open_seconds=time.monotonic() - license_started)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        finally:
            release.set()
            if owner is not None:
                owner.dispose()
            (output / 'mobile-feedback-result.json').write_text(json.dumps(report, indent=2))
            faulthandler.cancel_dump_traceback_later()
            self._feedback_fault_log.close()


def main():
    return FeedbackProbe('Mobile Feedback QA', 'io.github.ispaure.logisticsstorageqa')
