"""Bounded native comic guidance acceptance using disposable synthetic comics."""
import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import traceback
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from commonUtils.runtime.resources.documents import LocalDocuments
from commonUtils.testing.stages import TestStage
from mobile.app import LogisticsMobile
from mobile import comic_feedback, comic_guidance
from mobile.external_display import comic_canvas
from services.documents.readers import PrivateReader
from . import start_native_check
from .fixtures import capture_window
from .page_motion_checks import expand_comic
from .rotation_checks import rotate, pose_snapshot

TEST_STAGE = TestStage.REGRESSION
RESULT = 'comic-guidance-result.json'


class FixtureProvider:
    """A same-folder listing whose delay/failure/removal is controlled by the test."""
    private = False

    def __init__(self, root, data):
        self.root, self.data = root, data
        self.available = {'01.cbz', '02.cbz', '03.cbz'}
        self.failure = False
        self.gate = None

    def list(self, folder=''):
        if self.gate is not None:
            assert self.gate.wait(10), 'Synthetic neighbor listing was not released'
        if self.failure:
            raise OSError('Synthetic neighbor listing failure')
        return [dict(path='Comics/' + name, name=name, directory=False)
                for name in sorted(self.available)] + [
                    dict(path='Other/00.cbz', name='00.cbz', directory=False)]

    def open(self, key, **kwargs):
        if key.rsplit('/', 1)[-1] not in self.available:
            raise FileNotFoundError('Synthetic neighbor disappeared')
        reader = PrivateReader(key, self.data)
        reader.key = key
        return reader


class ComicGuidanceProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('comic-guidance-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    @property
    def android(self):
        return type(self._impl).__module__.startswith('toga_android.')

    async def until(self, predicate, message, timeout=12):
        deadline = self.loop.time() + timeout
        while not predicate():
            assert self.loop.time() < deadline, message
            await asyncio.sleep(.04)

    async def settled(self, owner):
        await self.until(lambda: not (owner.cloud_busy if hasattr(owner, 'crypt_reader')
                                     else owner.book_busy), 'Comic operation stayed busy')
        await asyncio.sleep(.06)

    async def close_owner(self, owner):
        await self.until(lambda: owner.session.id not in owner.workspace.sessions
                         or owner.manager.close(owner.session.id), 'Synthetic reader did not close')

    def record_progress(self, report, phase):
        report['phase'] = phase
        (Path(self.paths.cache) / 'comic-guidance-progress.json').write_text(json.dumps(report, indent=2))

    def canvas(self, owner):
        content = owner.crypt_content if hasattr(owner, 'crypt_reader') else owner.book_content
        result = comic_canvas(content)
        assert result is not None, 'Visible comic canvas is missing'
        return result

    def frame(self, native):
        if not self.android:
            rect = native.convertRect(native.bounds, toView=self.main_window._impl.native)
            return tuple(map(float, (rect.origin.x, rect.origin.y, rect.size.width, rect.size.height)))
        from java import jarray, jint
        xy, origin = jarray(jint)(2), jarray(jint)(2)
        native.getLocationOnScreen(xy)
        self._impl.native.getWindow().getDecorView().getLocationOnScreen(origin)
        scale = float(self.main_window.content._impl.scale_in(1))
        return ((xy[0] - origin[0]) / scale, (xy[1] - origin[1]) / scale,
                native.getWidth() / scale, native.getHeight() / scale)

    def assert_pass_through(self, owner, presenter):
        if self.android:
            assert not presenter.root.isClickable() and not presenter.root.isFocusable()
            return  # The next swipe is dispatched through the real window hierarchy.
        from rubicon.objc import CGPoint
        from commonUtils.ui.native.keyboard import native_value
        native = self.canvas(owner)._impl.native
        for view in (presenter.hand, presenter.reading, presenter.volume):
            if view is None:
                continue
            x, y, width, height = self.frame(view)
            hit = self.main_window._impl.native.hitTest(CGPoint(x + width / 2, y + height / 2), withEvent=None)
            while hit is not None and hit != native:
                hit = native_value(hit.superview)
            assert hit == native, 'Comic cue intercepts the reader touch surface'

    async def swipe(self, owner, direction, *, rtl, rapid=False):
        await self.settled(owner)
        canvas = self.canvas(owner)
        movement = direction * (1 if rtl else -1)
        before = getattr(owner, '_comic_swipe_task', None)
        if self.android:
            from java import jclass
            event_type = jclass('android.view.MotionEvent')
            decor = self._impl.native.getWindow().getDecorView()
            scale = float(canvas._impl.scale_in(1))
            x, y, width, height = self.frame(canvas._impl.native)
            start, end = x + width * (.25 if movement > 0 else .75), x + width * (.75 if movement > 0 else .25)
            now = jclass('android.os.SystemClock').uptimeMillis()
            for index in range(6):
                action = event_type.ACTION_DOWN if index == 0 else event_type.ACTION_UP if index == 5 else event_type.ACTION_MOVE
                event = event_type.obtain(now, now + index * 45, action,
                    (start + (end - start) * index / 5) * scale, (y + height / 2) * scale, 0)
                try:
                    decor.dispatchTouchEvent(event)
                finally:
                    event.recycle()
                if index < 5:
                    await asyncio.sleep(.012)
            if rapid:
                # Both final callbacks reach the same event-loop turn, as when
                # native recognizers report rapid consecutive gestures.
                for action, offset, point in ((event_type.ACTION_DOWN, 250, start),
                                               (event_type.ACTION_UP, 450, end)):
                    event = event_type.obtain(now + 250, now + offset, action,
                        point * scale, (y + height / 2) * scale, 0)
                    try:
                        decor.dispatchTouchEvent(event)
                    finally:
                        event.recycle()
        else:
            native = canvas._impl.native
            gesture = next(item for item in canvas._impl.swipes
                           if int(item.direction) == (1 if movement > 0 else 2))
            assert native.gestureRecognizerShouldBegin(gesture)
            native.pageSwipe(gesture)
            if rapid:
                native.pageSwipe(gesture)
        await self.until(lambda: getattr(owner, '_comic_swipe_task', None) is not before,
                         'Native comic swipe did not reach the reader')
        await owner._comic_swipe_task

    async def position(self, owner, direction):
        comic_feedback.clear(self)
        if hasattr(owner, 'crypt_reader'):
            await owner.move_private_page(0 if direction < 0 else len(owner.crypt_reader.labels) - 1)
        else:
            await owner.move_book_page(0 if direction < 0 else len(owner.book_reader.pages) - 1)
        await self.settled(owner)

    async def provider_owner(self, provider, copies):
        assert await self.open_crypt(copies=copies, key='Comics/02.cbz'), self.cloud_status.value
        owner = self.private_sessions.active
        await self.settled(owner)
        await owner.refresh_provider_comic_neighbors()
        return owner

    def guidance(self, owner, *, rtl, direction, available):
        feedback = self._comic_boundary_feedback
        assert feedback.owner() is owner
        expected = 'left to right' if rtl else 'right to left'
        assert expected in feedback.reading_text, feedback.reading_text
        assert feedback.movement == (1 if rtl else -1)
        assert bool(feedback.volume_text) == available, feedback.volume_text
        if available:
            physical = expected if direction > 0 else ('right to left' if rtl else 'left to right')
            assert physical in feedback.volume_text and 'again' in feedback.volume_text
            assert ('previous' if direction < 0 else 'next') in feedback.volume_text.lower()
            assert feedback.armed
        else:
            assert not feedback.armed
        assert feedback.native is not None
        assert (feedback.native.volume is not None) == available
        for label, text in ((feedback.native.reading, feedback.reading_text),
                            (feedback.native.volume, feedback.volume_text)):
            if label is None:
                continue
            actual = str(label.getText()) if self.android else str(label.text)
            accessible = str(label.getContentDescription()) if self.android else str(label.accessibilityLabel)
            assert actual == accessible == text, (actual, accessible, text)
        return feedback

    async def provider_matrix(self, rtl, provider, copies, report):
        for previous, following in ((False, False), (True, False), (False, True), (True, True)):
            for direction in (-1, 1):
                provider.available = {'02.cbz'} | ({'01.cbz'} if previous else set()) | ({'03.cbz'} if following else set())
                owner = await self.provider_owner(provider, copies)
                await self.position(owner, direction)
                image = self.canvas(owner).image
                await self.swipe(owner, direction, rtl=rtl)
                available = previous if direction < 0 else following
                feedback = self.guidance(owner, rtl=rtl, direction=direction, available=available)
                self.assert_pass_through(owner, feedback.native)
                assert self.canvas(owner).image is image, 'Guidance changed the exported comic image'
                await self.swipe(owner, direction, rtl=rtl)
                current = self.private_sessions.active
                if available:
                    expected = 'Comics/01.cbz' if direction < 0 else 'Comics/03.cbz'
                    assert current is not owner and current.crypt_reader.key == expected
                else:
                    assert current is owner and current.crypt_reader.key == 'Comics/02.cbz'
                report['neighbors'].append(dict(rtl=rtl, direction=direction,
                    previous=previous, following=following, opened=current.crypt_reader.key))
                self.record_progress(report, 'provider-matrix')
        provider.available = {'01.cbz', '02.cbz', '03.cbz'}
        owner = await self.provider_owner(provider, copies)
        for failure in ('pending', 'failed'):
            await self.position(owner, -1)
            provider.failure = failure == 'failed'
            provider.gate = Event() if failure == 'pending' else None
            task = asyncio.create_task(owner.refresh_provider_comic_neighbors())
            try:
                await asyncio.sleep(.06)
                assert owner.comic_header.available == (False, False)
                await self.swipe(owner, -1, rtl=rtl)
                self.guidance(owner, rtl=rtl, direction=-1, available=False)
            finally:
                if provider.gate is not None:
                    provider.gate.set()
                await task
                provider.gate = None
                provider.failure = False
            report['availability'].append(dict(rtl=rtl, state=failure, volume_hint=False))
        for direction in (-1, 1):
            provider.available = {'01.cbz', '02.cbz', '03.cbz'}
            await owner.refresh_provider_comic_neighbors()
            await self.position(owner, direction)
            await self.swipe(owner, direction, rtl=rtl)
            self.guidance(owner, rtl=rtl, direction=direction, available=True)
            provider.available.remove('01.cbz' if direction < 0 else '03.cbz')
            await self.swipe(owner, direction, rtl=rtl)
            assert self.private_sessions.active is owner
            feedback = self._comic_boundary_feedback
            assert 'no longer available' in feedback.message.lower(), feedback.message
            assert not feedback.volume_text and not feedback.armed
            report['availability'].append(dict(rtl=rtl, state='disappeared', direction=direction, retained=True))
        provider.available = {'01.cbz', '02.cbz', '03.cbz'}
        await owner.refresh_provider_comic_neighbors()
        return owner

    async def visual_checks(self, owner, rtl, report):
        for dark in (False, True):
            if self.android:
                self._impl.native.getSystemService('uimode').setApplicationNightMode(2 if dark else 1)
            else:
                self.main_window._impl.native.overrideUserInterfaceStyle = 2 if dark else 1
            await asyncio.sleep(.4)
            self.refresh_native_theme()
            for orientation in ('portrait', 'landscape-left'):
                if self.android:
                    (Path(self.paths.cache) / 'creation-orientation').write_text(orientation)
                await rotate(self, orientation, settle=.2)
                for immersive in (False, True):
                    if owner.crypt_immersive != immersive:
                        owner.toggle_private_reading_mode()
                    await self.position(owner, -1)
                    await owner.refresh_provider_comic_neighbors()
                    await self.swipe(owner, -1, rtl=rtl)
                    feedback = self.guidance(owner, rtl=rtl, direction=-1, available=True)
                    await asyncio.sleep(.06)
                    presenter = feedback.native
                    self.assert_pass_through(owner, presenter)
                    region = tuple(map(float, presenter.geometry))
                    for view in (presenter.reading, presenter.volume):
                        x, y, width, height = self.frame(view)
                        assert x >= region[0] - 2 and y >= region[1] - 2, (region, (x, y, width, height))
                        assert x + width <= region[0] + region[2] + 2 and y + height <= region[1] + region[3] + 2
                    name = f'comic-guidance-{"rtl" if rtl else "ltr"}-{"dark" if dark else "light"}-{orientation}-{"full" if immersive else "normal"}.png'
                    await capture_window(self, Path(self.paths.cache) / name)
                    report['visuals'].append(dict(rtl=rtl, dark=dark, orientation=orientation,
                        fullscreen=immersive, geometry=region, screenshot=name))
                    self.record_progress(report, 'visuals')
        if self.android:
            (Path(self.paths.cache) / 'creation-orientation').write_text('portrait')
        await rotate(self, 'portrait', settle=.2)
        await self.position(owner, -1)
        await self.swipe(owner, -1, rtl=rtl)
        feedback = self._comic_boundary_feedback
        presenter = feedback.native
        assert presenter.motion_enabled, 'Default native animation is disabled'
        await asyncio.sleep(.10)
        first = float(presenter.hand_position())
        prefix = 'comic-guidance-' + ('rtl' if rtl else 'ltr')
        await capture_window(self, Path(self.paths.cache) / (prefix + '-frame-start.png'))
        await asyncio.sleep(.25)
        last = float(presenter.hand_position())
        await capture_window(self, Path(self.paths.cache) / (prefix + '-frame-end.png'))
        assert (last - first) * (1 if rtl else -1) > 5, (rtl, first, last)
        report['motion'].append(dict(rtl=rtl, first_x=first, last_x=last, expected=1 if rtl else -1))
        return owner

    async def driver_action(self, action):
        root = Path(self.paths.cache)
        done = root / 'comic-guidance-done'
        done.unlink(missing_ok=True)
        (root / 'comic-guidance-request.json').write_text(json.dumps(dict(action=action)))
        await self.until(done.exists, 'Native driver did not acknowledge ' + action, timeout=20)
        done.unlink()

    async def tap_controls(self, owner):
        canvas = self.canvas(owner)
        previous = owner.crypt_immersive
        presenter = self._comic_boundary_feedback.native
        self.assert_pass_through(owner, presenter)
        if self.android:
            from java import jclass
            event_type = jclass('android.view.MotionEvent')
            x, y, width, height = self.frame(presenter.hand)
            scale = float(canvas._impl.scale_in(1))
            now = jclass('android.os.SystemClock').uptimeMillis()
            decor = self._impl.native.getWindow().getDecorView()
            for action, offset in ((event_type.ACTION_DOWN, 0), (event_type.ACTION_UP, 60)):
                event = event_type.obtain(now, now + offset, action,
                    (x + width / 2) * scale, (y + height / 2) * scale, 0)
                try:
                    decor.dispatchTouchEvent(event)
                finally:
                    event.recycle()
        else:
            canvas._impl.native.toggleControls(None)
        await self.until(lambda: owner.crypt_immersive != previous, 'Guidance blocked a native reader tap')

    async def lifecycle_checks(self, owner, report):
        async def show():
            await self.position(owner, -1)
            await owner.refresh_provider_comic_neighbors()
            await self.swipe(owner, -1, rtl=True)
            return self._comic_boundary_feedback
        feedback = await show()
        root = feedback.native.root
        await asyncio.sleep(comic_feedback.HINT_SECONDS + .1)
        assert feedback.native is None and feedback.timer is None and feedback.owner is None
        assert root.getParent() is None if self.android else root.superview is None
        report['lifecycle'].append('expiry')
        feedback = await show()
        image = self.canvas(owner).image
        await self.swipe(owner, 1, rtl=True, rapid=True)
        assert self.canvas(owner).image is not image
        assert not feedback.message and feedback.native is None and feedback.timer is None
        nav = owner.crypt_reader.comic_navigation
        assert nav.page == 1, ('Rapid gesture skipped a page', nav.page)
        report['lifecycle'].append('page-and-rapid-gesture')
        feedback = await show()
        self.show_settings()
        await asyncio.sleep(.1)
        assert feedback.native is None and feedback.timer is None
        owner.resume_crypt()
        await self.settled(owner)
        report['lifecycle'].append('navigation')
        await show()
        await asyncio.sleep(.35)
        await self.tap_controls(owner)
        report['lifecycle'].append('tap-through-cue')
        feedback = await show()
        counts = dict(concealed=0, revealed=0)
        privacy = self.screen_privacy
        conceal, reveal = privacy.conceal, privacy.reveal
        def concealed():
            counts['concealed'] += 1
            return conceal()
        def revealed():
            counts['revealed'] += 1
            return reveal()
        privacy.conceal, privacy.reveal = concealed, revealed
        try:
            await self.driver_action('background')
            await self.until(lambda: counts['concealed'] and counts['revealed'], 'Native lifecycle callbacks missing')
            assert feedback.native is None and feedback.timer is None and not feedback.message
            assert self.private_sessions.active is owner
        finally:
            privacy.conceal, privacy.reveal = conceal, reveal
        report['lifecycle'].append(dict(background_resume=counts))
        # Android uses the actual OS duration scale; the Apple renderer is tested
        # through its system-policy seam, explicitly distinguished in the report.
        if self.android:
            await self.driver_action('reduce-motion-on')
            feedback = await show()
            assert not feedback.native.motion_enabled
            first = feedback.native.hand_position()
            await asyncio.sleep(.3)
            assert feedback.native.hand_position() == first
            await capture_window(self, Path(self.paths.cache) / 'comic-guidance-reduced-motion.png')
            await self.driver_action('reduce-motion-off')
            report['static'].append('android-os-duration-scale')
        else:
            with patch.object(comic_guidance, 'reduced_motion', return_value=True):
                feedback = await show()
                assert not feedback.native.motion_enabled
                x = feedback.native.hand_position()
                await asyncio.sleep(.3)
                assert feedback.native.hand_position() == x
                await capture_window(self, Path(self.paths.cache) / 'comic-guidance-reduced-motion.png')
            report['static'].append('ios-system-policy-injected-native-renderer')
        self.preferences.values['android_eink'] = 'true'
        try:
            feedback = await show()
            assert not feedback.native.motion_enabled
            first = feedback.native.hand_position()
            await asyncio.sleep(.3)
            assert feedback.native.hand_position() == first
            await capture_window(self, Path(self.paths.cache) / 'comic-guidance-eink.png')
            report['static'].append('eink-preference; physical quality unverified')
        finally:
            self.preferences.values['android_eink'] = 'false'
        feedback = await show()
        await self.close_owner(owner)
        await asyncio.sleep(.1)
        assert feedback.native is None and feedback.timer is None and not feedback.message
        report['lifecycle'].append('close')

    async def library_checks(self, source, rtl, report):
        folder = source.parent / 'Library'
        folder.mkdir(exist_ok=True)
        for name in ('01.cbz', '02.cbz', '03.cbz'):
            (folder / name).write_bytes(source.read_bytes())
        store = self.reader_manager().catalog.library_store
        record = await asyncio.to_thread(store.import_book, LocalDocuments(), folder / '02.cbz')
        for direction in (-1, 1):
            assert await self.open_book(record['id'])
            owner = self.readers.active
            await self.settled(owner)
            await owner.comic_controller().refresh_comic_neighbors()
            await self.position(owner, direction)
            await self.swipe(owner, direction, rtl=rtl)
            self.guidance(owner, rtl=rtl, direction=direction, available=True)
            await self.swipe(owner, direction, rtl=rtl)
            current = self.private_sessions.active
            expected = '01.cbz' if direction < 0 else '03.cbz'
            assert current.crypt_reader.key == expected, current.crypt_reader.key
            report['library'].append(dict(rtl=rtl, direction=direction, opened=expected))
        solo = source.parent / 'Solo'
        solo.mkdir(exist_ok=True)
        path = solo / 'Wide.cbz'
        path.write_bytes(source.read_bytes())
        record = await asyncio.to_thread(store.import_book, LocalDocuments(), path)
        assert await self.open_book(record['id'])
        owner = self.readers.active
        self.preferences.values['comic_split_wide'] = 'true'
        await owner.move_book_page(4)
        await self.settled(owner)
        nav = owner.comic_navigation
        assert nav.split and nav.half == 0
        await self.swipe(owner, 1, rtl=rtl)
        assert nav.page == 4 and nav.half == 1
        await self.swipe(owner, 1, rtl=rtl)
        self.guidance(owner, rtl=rtl, direction=1, available=False)
        assert nav.page == 4 and nav.half == 1
        self.preferences.values.update(comic_layout='double', comic_split_wide='false')
        await owner.move_book_page(0)
        await self.settled(owner)
        assert nav.visible == (0, 1), nav.visible
        await self.swipe(owner, 1, rtl=rtl)
        assert nav.visible == (2, 3), nav.visible
        await self.swipe(owner, 1, rtl=rtl)
        assert nav.visible == (4,), nav.visible
        await self.swipe(owner, 1, rtl=rtl)
        self.guidance(owner, rtl=rtl, direction=1, available=False)
        report['layouts'].append(dict(rtl=rtl, split_halves=[0, 1], paired_spreads=[[0, 1], [2, 3], [4]]))
        await self.close_owner(owner)
        self.preferences.values.update(comic_layout='single', comic_split_wide='false')

    async def probe(self):
        root = Path(self.paths.cache)
        report = dict(success=False, platform='android' if self.android else 'ios',
            neighbors=[], availability=[], motion=[], visuals=[], lifecycle=[], static=[], library=[], layouts=[])
        try:
            self.record_progress(report, 'startup')
            await self.until(lambda: not getattr(self, '_startup_in_progress', False), 'Startup did not settle', 30)
            self.preferences.values.update(comic_layout='single', comic_split_wide='false', android_eink='false')
            if os.environ.get('LOGISTICS_COMIC_GUIDANCE_BASIC') == '1':
                await local_overlay_check(self, report)
                report['success'] = True
                return
            for rtl in (False, True):
                folder = self.private_root / ('RTL' if rtl else 'LTR')
                folder.mkdir(parents=True, exist_ok=True)
                source = folder / 'Fixture.cbz'
                expand_comic(source)
                with ZipFile(source, 'a') as archive:
                    archive.writestr('ComicInfo.xml', '<ComicInfo><Manga>' + ('YesAndRightToLeft' if rtl else 'No') + '</Manga></ComicInfo>')
                original = sha256(source.read_bytes()).hexdigest()
                provider = FixtureProvider(folder / 'Provider', source.read_bytes())
                copies = SimpleNamespace(root=provider.root, provider=provider, encrypted=False, open=provider.open)
                owner = await self.provider_matrix(rtl, provider, copies, report)
                owner = await self.visual_checks(owner, rtl, report)
                if rtl:
                    self.record_progress(report, 'lifecycle')
                    await self.lifecycle_checks(owner, report)
                else:
                    await self.close_owner(owner)
                self.record_progress(report, 'library-and-layouts')
                await self.library_checks(source, rtl, report)
                assert sha256(source.read_bytes()).hexdigest() == original, 'Guidance modified the archive'
            report['fold_environment'] = pose_snapshot(self)
            report['image_scope'] = 'Native canvas image identity and source bytes unchanged; external renderer reads this canvas'
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
            try:
                await capture_window(self, root / 'comic-guidance-failure.png')
            except Exception:
                pass
        finally:
            comic_feedback.clear(self)
            try:
                for name in ('private_sessions', 'readers'):
                    manager = getattr(self, name, None)
                    if manager is None:
                        continue
                    for owner in list(manager.controllers.values()):
                        if owner.session is not None:
                            await self.close_owner(owner)
                report['reader_cleanup'] = True
            except Exception:
                report['reader_cleanup'] = False
                report['cleanup_error'] = traceback.format_exc()
                report['success'] = False
            report['phase'] = 'complete' if report['success'] else 'failed'
            (root / RESULT).write_text(json.dumps(report, indent=2))


async def local_overlay_check(app, report):
    """Minimum renderer proof using the established local native comic fixture."""
    from mobile.comic_layout_check import fixture_reader
    report['scope'] = 'local-overlay-only'
    report['missing_acceptance'] = ['provider and imported volume opening matrix',
        'pending/failed/disappeared provider availability', 'theme/orientation/fullscreen matrix',
        'reduced-motion OS setting', 'background/resume', 'window switches', 'fold layouts',
        'external-display output', 'physical e-ink quality']
    cache = Path(app.paths.cache)
    for rtl in (False, True):
        folder = app.private_root / ('basic-rtl' if rtl else 'basic-ltr')
        folder.mkdir(parents=True, exist_ok=True)
        owner = await fixture_reader(app, folder, pages=4, right_to_left=rtl)
        source = folder / 'layout-fixture.cbz'
        for name in ('00.cbz', 'zz.cbz'):
            (folder / name).write_bytes(source.read_bytes())
        await owner.comic_controller().refresh_comic_neighbors()
        await app.settled(owner)
        await app.swipe(owner, -1, rtl=rtl)
        feedback = app.guidance(owner, rtl=rtl, direction=-1, available=True)
        presenter = feedback.native
        app.assert_pass_through(owner, presenter)
        assert presenter.motion_enabled
        await asyncio.sleep(.10)
        start = presenter.hand_position()
        prefix = 'comic-guidance-' + ('rtl' if rtl else 'ltr')
        await capture_window(app, cache / (prefix + '-frame-start.png'))
        await asyncio.sleep(.25)
        end = presenter.hand_position()
        await capture_window(app, cache / (prefix + '-frame-end.png'))
        assert (end - start) * (1 if rtl else -1) > 5, (start, end, rtl)
        report['motion'].append(dict(rtl=rtl, first_x=start, last_x=end))
        await app.swipe(owner, 1, rtl=rtl)
        assert owner.book_record['position'] == 1
        assert feedback.native is None and feedback.timer is None
        await owner.move_book_page(3)
        await app.swipe(owner, 1, rtl=rtl)
        app.guidance(owner, rtl=rtl, direction=1, available=True)
        for name in ('00.cbz', 'zz.cbz'):
            (folder / name).unlink()
        await owner.comic_controller().refresh_comic_neighbors()
        await app.swipe(owner, 1, rtl=rtl)
        feedback = app.guidance(owner, rtl=rtl, direction=1, available=False)
        await asyncio.sleep(comic_feedback.HINT_SECONDS + .1)
        assert feedback.native is None and feedback.timer is None
        report['availability'].append(dict(rtl=rtl, previous_and_next_offered=True,
                                           missing_neighbor_omitted=True, page_opened=1))
        report['lifecycle'].append(dict(rtl=rtl, page_change=True, expiry=True))
        await app.close_owner(owner)
        app.record_progress(report, 'local-overlay')


def main():
    return ComicGuidanceProbe('Comic Guidance QA', 'io.github.ispaure.logisticscomicqa')
