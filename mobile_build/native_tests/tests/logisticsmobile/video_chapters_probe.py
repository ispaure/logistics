"""Verify chapter navigation with generated movies through mobile open_video."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from features.video.mobile.player import open_video
from mobile.screen_privacy import native_value
from .fixtures import capture_window
from .video_probe import VideoProbe, android_player, until

TEST_STAGE = TestStage.REGRESSION


def android_field(native, name):
    field = native.getClass().getDeclaredField(name)
    field.setAccessible(True)
    return field.get(native)


def android_timeline_ticks(slider):
    from java import jclass
    bitmap = jclass('android.graphics.Bitmap')
    image = bitmap.createBitmap(slider.getWidth(), slider.getHeight(), bitmap.Config.ARGB_8888)
    try:
        slider.draw(jclass('android.graphics.Canvas')(image))
        white = jclass('android.graphics.Color').WHITE
        left = slider.getPaddingLeft()
        span = slider.getWidth() - left - slider.getPaddingRight()
        center = slider.getHeight() // 2
        y_range = range(center + 1, image.getHeight())
        return [any(image.getPixel(left + round(start * span / 18000), y) == white for y in y_range)
                for start in (5000, 10000)]
    finally:
        image.recycle()


def open_chapters(native, android):
    if android:
        from java import jclass
        group = jclass('android.view.ViewGroup')
        pending = [android_field(native, 'utilityButtons')]
        while pending:
            view = pending.pop()
            if str(view.getContentDescription()) == 'Chapters':
                assert view.performClick()
                break
            if isinstance(view, group):
                pending.extend(view.getChildAt(i) for i in range(view.getChildCount()))
        else:
            raise AssertionError('Chapters control unavailable')
        return android_field(native, 'chapterDialog')
    native.chapters(None)
    return native.chapterDialog


async def exercise(app):
    report = dict(success=False, cases=[])
    try:
        startup = getattr(app, 'startup_task', None)
        if startup is not None:
            await asyncio.shield(startup)
        android = type(app._impl).__module__.startswith('toga_android.')
        root = Path(__file__).with_name('chapter-fixtures')
        local = Path(app.private_root) / 'Chapter QA'
        local.mkdir()
        for fixture in root.glob('*.mp4'):
            (local / fixture.name).write_bytes(fixture.read_bytes())
        for marked in (True, False):
            name = 'chapter-playback.mp4' if marked else 'chapterless.mp4'
            row = dict(file=name)
            report['cases'].append(row)
            assert await open_video(app, LocalFiles(local), name)
            owner = app.video_player
            adapter = owner.native
            native = adapter.native
            player = android_player(owner) if android else native.player
            clock = lambda: int(adapter.position()[0])
            playing = (lambda: bool(player.isPlaying())) if android else (lambda: bool(native_value(player, 'isPlaying')))
            play_requested = False

            def ready():
                nonlocal play_requested
                if clock() >= 400 and playing():
                    return True
                if (android and not play_requested and app._impl.native.hasWindowFocus()
                        and not playing() and not android_field(native, 'playRequested')):
                    # An automatic Play during cold startup can precede audio focus.
                    play_requested = True
                    adapter.play()
                return False

            try:
                await until(ready, timeout=40)
            except AssertionError:
                row['startup'] = dict(clock_ms=clock(), playing=playing(), allowed=owner.allowed(),
                                      audio=owner.audio_output.permitted(), failure=owner.failure_message)
                if android:
                    row['startup'].update(window_focus=bool(app._impl.native.hasWindowFocus()),
                        play_requested=str(android_field(native, 'playRequested')), retried=play_requested)
                else:
                    row['startup']['native'] = json.loads(str(native.playbackDiagnosticJSON()))
                raise
            adapter.pause()
            await until(lambda: not playing())
            adapter.seek(0)
            await until(lambda: clock() == 0)
            if android:
                slider = android_field(native, 'seek')
                hint = lambda: str(slider.getContentDescription())
                markers = lambda: [int(str(i)) for i in android_field(native, 'chapterStarts').keySet().toArray()]
            else:
                hint = lambda: str(native.seek.accessibilityHint or '')
                markers = lambda: [round(float(value.doubleValue) * 18000) for value in native.seek.chapterFractions]
            if marked:
                await until(lambda: 'Open Chapters' in hint())
                row['markers_ms'] = markers()
                assert all(abs(a - b) <= 50 for a, b in zip(row['markers_ms'], (0, 5000, 10000), strict=True)), row
                await capture_window(app, Path(app.paths.cache) / 'chapter-timeline.png')
            else:
                assert markers() == [] and 'Open Chapters' not in hint()
            if android:
                row['pixel_ticks'] = android_timeline_ticks(slider)
                assert row['pixel_ticks'] == [marked, marked], row
            menu = open_chapters(native, android)
            if not marked:
                if android:
                    chapter_list = menu.getListView()
                    previous = menu.getButton(-3)
                    assert chapter_list is None or chapter_list.getCount() == 0
                    assert previous is None or previous.getVisibility() != 0
                    assert str(menu.getButton(-1).getText()).lower() == 'done'
                    menu.dismiss()
                else:
                    assert 'no embedded chapters' in str(menu.message)
                    menu.dismissViewControllerAnimated(False, completion=None)
                await owner.close()
                continue

            def controls(menu):
                if android:
                    chapter_list = menu.getListView()
                    labels = [str(chapter_list.getAdapter().getItem(i)) for i in range(chapter_list.getCount())]
                    available = [bool(menu.getButton(i).isEnabled()) for i in (-3, -1)]
                else:
                    actions = list(menu.actions)
                    labels = [str(action.title) for action in actions if ' · ' in str(action.title)]
                    available = [bool(native_value(action, 'isEnabled')) for action in actions
                                 if str(action.title) in ('Previous chapter', 'Next chapter')]
                assert [label.split(' · ')[-1] for label in labels] == ['Opening', 'Middle', 'Finale'], labels
                return available, labels

            async def activate(menu, next_chapter):
                if android:
                    assert menu.getButton(-1 if next_chapter else -3).performClick()
                    await until(lambda: android_field(native, 'chapterDialog') is None)
                else:
                    menu.dismissViewControllerAnimated(False, completion=None)
                    native.skipChapter(next_chapter)
                    await until(lambda: native.presentedViewController is None)

            available, row['labels'] = controls(menu)
            assert available == [False, True], available
            await activate(menu, True)
            await until(lambda: abs(clock() - 5000) < 150)
            await asyncio.sleep(.3)
            assert not playing() and abs(clock() - 5000) < 150
            menu = open_chapters(native, android)
            available, _ = controls(menu)
            assert available == [True, True], available
            await activate(menu, False)
            await until(lambda: 0 <= clock() < 150)
            row['paused_jumps'] = [5000, 0]
            adapter.play()
            await until(lambda: playing() and clock() > 400)
            await activate(open_chapters(native, android), True)
            await until(lambda: 5300 <= clock() < 9000 and playing(), timeout=25)
            await activate(open_chapters(native, android), True)
            await until(lambda: 10300 <= clock() < 16000 and playing(), timeout=25)
            row['playing_jumps'] = [5000, 10000]
            menu = open_chapters(native, android)
            available, _ = controls(menu)
            assert available == [True, False], available
            owner.stream_failed('changed')
            dismissed = ((lambda: android_field(native, 'chapterDialog') is None) if android
                         else (lambda: native.presentedViewController is None))
            await until(lambda: not markers() and dismissed())
            row['stale_markers_cleared'] = True
            await owner.close()
        report['success'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        owner = getattr(app, 'video_player', None)
        if owner is not None:
            await owner.close()
        result = Path(app.paths.cache) / 'video-chapters-result.json'
        temp = result.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2))
        temp.replace(result)


class ChapterProbe(VideoProbe):
    def on_running(self):
        if getattr(self, '_video_probe_task', None) is None:
            self._video_probe_task = self.loop.create_task(exercise(self))


def main():
    return ChapterProbe('Video Chapters QA', 'io.github.ispaure.logisticsmobile')
