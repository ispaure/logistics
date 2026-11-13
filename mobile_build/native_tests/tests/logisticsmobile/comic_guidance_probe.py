"""Bounded native comic guidance acceptance using disposable synthetic comics."""
import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import traceback
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
        """Wait for the published native canvas and its layout to stop changing."""
        from commonUtils.ui.native.draw_ready import wait_for_draw
        deadline, previous, stable_since = self.loop.time() + 12, None, None
        while self.loop.time() < deadline:
            private = hasattr(owner, 'crypt_reader')
            busy = owner.cloud_busy if private else owner.book_busy
            content = owner.crypt_content if private else owner.book_content
            canvas = comic_canvas(content)
            navigation = (getattr(owner.crypt_reader, 'comic_navigation', None) if private
                          else getattr(owner, 'comic_navigation', None))
            signature = None
            if not busy and canvas is not None and not getattr(navigation, 'layout_reload', False):
                bounds = tuple(round(value, 2) for value in self.frame(canvas._impl.native))
                if bounds[2] > 1 and bounds[3] > 1:
                    signature = id(canvas), id(canvas.image), bounds
            if signature is not None and signature == previous:
                if self.loop.time() - stable_since >= .16:
                    # This acknowledges a draw without mistaking an offscreen
                    # view or a zero-sized layout for a finished publication.
                    assert await wait_for_draw(content), 'Published comic container did not draw'
                    if canvas is comic_canvas(content) and not (owner.cloud_busy if private else owner.book_busy):
                        return
                    previous, stable_since = None, None
            else:
                previous, stable_since = signature, self.loop.time()
            await asyncio.sleep(.04)
        raise AssertionError('Comic operation or native layout did not settle')

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

    def cue_detached(self, root):
        if self.android:
            return root.getParent() is None
        from commonUtils.ui.native.keyboard import native_value
        return native_value(root.superview) is None

    def canvas_png(self, owner, *, maximum=None):
        """Encode only the native comic bitmap, never the window overlay."""
        canvas = self.canvas(owner)
        native = (canvas._impl.native.getDrawable().getBitmap() if self.android
                  else canvas._impl.picture.image)
        return self.native_image_png(native, maximum=maximum)

    def native_image_png(self, native, *, maximum=None):
        """Use the same encoder for the reader and an external native image sink."""
        if self.android:
            from java import jclass
            bitmap = native
            width, height = int(bitmap.getWidth()), int(bitmap.getHeight())
            output = jclass('java.io.ByteArrayOutputStream')()
            scaled = bitmap
            try:
                if maximum is not None and max(width, height) > maximum:
                    factor = maximum / max(width, height)
                    scaled = jclass('android.graphics.Bitmap').createScaledBitmap(
                        bitmap, max(1, round(width * factor)), max(1, round(height * factor)), True)
                assert scaled.compress(jclass('android.graphics.Bitmap$CompressFormat').PNG, 100, output)
                return bytes(int(value) & 255 for value in output.toByteArray())
            finally:
                output.close()
                if scaled != bitmap:
                    scaled.recycle()
        from rubicon.objc import Block, CGRect, CGSize, ObjCClass, objc_id
        from toga_iOS.images import nsdata_to_bytes
        from toga_iOS.libs import UIGraphicsImageRenderer
        width, height = float(native.size.width * native.scale), float(native.size.height * native.scale)
        factor = min(1, maximum / max(width, height)) if maximum is not None else 1
        size = CGSize(max(1, round(width * factor)), max(1, round(height * factor)))
        format = ObjCClass('UIGraphicsImageRendererFormat').defaultFormat()
        format.scale = 1
        renderer = UIGraphicsImageRenderer.alloc().initWithSize(size, format=format)
        def draw(context):
            native.drawInRect(CGRect((0, 0), (size.width, size.height)))
        return nsdata_to_bytes(renderer.PNGDataWithActions(Block(draw, None, objc_id)))

    def save_canvas(self, owner, name, report, *, expected=None, expected_colors=None):
        data = self.canvas_png(owner)
        assert data.startswith(b'\x89PNG'), 'Native comic export was not a PNG'
        if expected is not None:
            assert data == expected, 'Guidance changed the exported native comic pixels'
        root = Path(self.paths.cache)
        (root / (name + '.png')).write_bytes(data)
        thumbnail = self.canvas_png(owner, maximum=128)
        (root / (name + '-thumbnail.png')).write_bytes(thumbnail)
        record = dict(name=name, sha256=sha256(data).hexdigest(),
                      thumbnail_sha256=sha256(thumbnail).hexdigest(),
                      screenshot=name + '.png')
        if expected_colors is not None:
            # Pixel interpretation is independent evidence for review; logical
            # half/page assertions remain separate from the bitmap exports.
            record['expected_colors'] = expected_colors
            record['pixel_review_required'] = True
        report.setdefault('images', []).append(record)
        return data

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
                image = self.canvas_png(owner)
                thumbnail = self.canvas_png(owner, maximum=128)
                await self.swipe(owner, direction, rtl=rtl)
                await self.settled(owner)
                available = previous if direction < 0 else following
                feedback = self.guidance(owner, rtl=rtl, direction=direction, available=available)
                self.assert_pass_through(owner, feedback.native)
                name = f'comic-guidance-bitmap-{"rtl" if rtl else "ltr"}-{int(previous)}{int(following)}-{direction}'
                self.save_canvas(owner, name, report, expected=image)
                assert self.canvas_png(owner, maximum=128) == thumbnail, 'Guidance changed the native thumbnail'
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
                await self.close_owner(current)
                if current is not owner:
                    await self.close_owner(owner)
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
            def actual_dark():
                if self.android:
                    return int(self._impl.native.getResources().getConfiguration().uiMode) & 0x30 == 0x20
                return int(self.main_window._impl.native.traitCollection.userInterfaceStyle) == 2
            await self.until(lambda: actual_dark() == dark, 'Native appearance did not change')
            self.refresh_native_theme()
            await self.settled(owner)
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
                    await self.settled(owner)
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

    async def driver_action(self, action, points=None):
        root = Path(self.paths.cache)
        done = root / 'comic-guidance-done'
        done.unlink(missing_ok=True)
        request = dict(action=action)
        if points is not None:
            request['points'] = points
        (root / 'comic-guidance-request.json').write_text(json.dumps(request))
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
        assert self.cue_detached(root), 'Expired cue remains in its native window'
        report['lifecycle'].append('expiry')
        feedback = await show()
        image = self.canvas_png(owner)
        await self.swipe(owner, 1, rtl=True, rapid=True)
        await self.settled(owner)
        assert self.canvas_png(owner) != image
        assert not feedback.message and feedback.native is None and feedback.timer is None
        nav = owner.crypt_reader.comic_navigation
        assert nav.page == 1, ('Rapid gesture skipped a page', nav.page)
        report['lifecycle'].append('page-and-rapid-gesture')
        feedback = await show()
        self.show_settings()
        await asyncio.sleep(.1)
        assert feedback.native is None and feedback.timer is None
        resumed = owner.resume_crypt()
        if resumed is not None:
            await asyncio.wait_for(asyncio.shield(resumed), timeout=12)
        await self.settled(owner)
        report['lifecycle'].append('navigation')
        await show()
        await asyncio.sleep(.35)
        await self.tap_controls(owner)
        report['lifecycle'].append('tap-through-cue')
        feedback = await show()
        cue_root, cue_deadline = feedback.native.root, feedback.deadline
        counts = dict(interrupted=0, concealed=0, revealed=0)
        cleanup = []
        privacy = self.screen_privacy
        interrupt, conceal, reveal = privacy.interrupt, privacy.conceal, privacy.reveal
        def observe_cleanup(callback, name):
            counts[name] += 1
            live = feedback.native is not None and self.loop.time() < cue_deadline
            result = callback()
            cleanup.append(dict(callback=name, live_before=live, before_deadline=self.loop.time() < cue_deadline,
                cleared=feedback.native is None and feedback.timer is None and not feedback.message,
                detached=self.cue_detached(cue_root)))
            return result
        def interrupted():
            return observe_cleanup(interrupt, 'interrupted')
        def concealed():
            return observe_cleanup(conceal, 'concealed')
        def revealed():
            counts['revealed'] += 1
            return reveal()
        privacy.interrupt, privacy.conceal, privacy.reveal = interrupted, concealed, revealed
        try:
            await self.driver_action('background')
            await self.until(lambda: counts['concealed'] and counts['revealed'], 'Native lifecycle callbacks missing')
            assert any(row['live_before'] and row['before_deadline'] and row['cleared'] and row['detached']
                       for row in cleanup), ('Background did not clear a live cue before expiry', cleanup)
            assert feedback.native is None and feedback.timer is None and not feedback.message
            assert self.private_sessions.active is owner
        finally:
            privacy.interrupt, privacy.conceal, privacy.reveal = interrupt, conceal, reveal
        report['lifecycle'].append(dict(background_resume=counts, callback_cleanup=cleanup))
        # iOS uses the separate reduced-motion scope after the driver changes
        # its real system preference; the main matrix must stay motion-enabled.
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
            report['static'].append(dict(native_os_policy='requires separate reduced-motion scope'))
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
            await self.close_owner(current)
            await self.close_owner(owner)
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
        prefix = 'comic-guidance-layout-' + ('rtl' if rtl else 'ltr')
        self.save_canvas(owner, prefix + '-half-0', report,
                         expected_colors={'center': 'blue' if rtl else 'red'})
        await self.swipe(owner, 1, rtl=rtl)
        await self.settled(owner)
        assert nav.page == 4 and nav.half == 1
        self.save_canvas(owner, prefix + '-half-1', report,
                         expected_colors={'center': 'red' if rtl else 'blue'})
        await self.swipe(owner, 1, rtl=rtl)
        self.guidance(owner, rtl=rtl, direction=1, available=False)
        assert nav.page == 4 and nav.half == 1
        self.preferences.values.update(comic_layout='double', comic_split_wide='false')
        await owner.move_book_page(0)
        await self.settled(owner)
        assert nav.visible == (0, 1), nav.visible
        self.save_canvas(owner, prefix + '-spread-0', report,
                         expected_colors={'left': 'blue' if rtl else 'red', 'right': 'red' if rtl else 'blue'})
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
            restore = getattr(self, 'cloud_startup_task', None)
            if restore is not None:
                await asyncio.wait_for(asyncio.shield(restore), timeout=30)
            await self.until(lambda: not self.cloud_busy, 'Startup provider restore stayed busy', 30)
            self.preferences.values.update(comic_layout='single', comic_split_wide='false', android_eink='false')
            scope_file = root / 'comic-guidance-scope'
            scope = (scope_file.read_text().strip() if scope_file.is_file()
                     else os.environ.get('LOGISTICS_COMIC_GUIDANCE_SCOPE', 'matrix'))
            extra = {'windows': scene_guidance_check, 'fold': fold_guidance_check,
                     'reduced-motion': reduced_motion_check, 'lifecycle': lifecycle_guidance_check,
                     'library': library_guidance_check, 'readers': reader_switch_check}
            if scope in extra:
                report['scope'] = scope
                await extra[scope](self, report)
                report['success'] = True
                return
            assert scope == 'matrix', 'Unknown comic guidance scope: ' + scope
            if (os.environ.get('LOGISTICS_COMIC_GUIDANCE_BASIC') == '1'
                    or (root / 'comic-guidance-basic').is_file()):
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
            report['image_scope'] = ('Native comic PNG and thumbnail bytes unchanged while guidance is visible; '
                                     'source archive unchanged. External output connection is not exercised here.')
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


async def lifecycle_guidance_check(app, report):
    """Retest lifecycle policy with one RTL provider reader, without the matrix."""
    folder = app.private_root / 'Guidance lifecycle'
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'Fixture.cbz'
    expand_comic(source)
    with ZipFile(source, 'a') as archive:
        archive.writestr('ComicInfo.xml', '<ComicInfo><Manga>YesAndRightToLeft</Manga></ComicInfo>')
    provider = FixtureProvider(folder / 'Provider', source.read_bytes())
    copies = SimpleNamespace(root=provider.root, provider=provider, encrypted=False, open=provider.open)
    owner = await app.provider_owner(provider, copies)
    await app.lifecycle_checks(owner, report)


async def library_guidance_check(app, report):
    """Complete imported neighbors and rendered layouts without the provider matrix."""
    for rtl in (False, True):
        folder = app.private_root / 'Guidance library' / ('RTL' if rtl else 'LTR')
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / 'Fixture.cbz'
        expand_comic(source)
        with ZipFile(source, 'a') as archive:
            archive.writestr('ComicInfo.xml', '<ComicInfo><Manga>'
                + ('YesAndRightToLeft' if rtl else 'No') + '</Manga></ComicInfo>')
        before = sha256(source.read_bytes()).hexdigest()
        await app.library_checks(source, rtl, report)
        assert sha256(source.read_bytes()).hexdigest() == before, 'Guidance modified the source archive'
        await external_image_check(app, report, rtl=rtl)
        app.record_progress(report, 'library-and-layouts')


async def external_image_check(app, report, *, rtl):
    """Real forwarding into an injected native image sink, without a new display."""
    owner, source = await ordinary_comic_fixture(app, 'external-' + str(rtl), rtl=rtl)
    output = app.scene_manager.external_comics
    original = output.source, output.ios, output.android, output.ios_status
    window = picture = None
    injected = False
    try:
        assert output.allowed_host(app), 'Real external-output policy denied this ordinary reader'
        assert output.current_video(app) is None and output.ios_video is None
        if app.android:
            from java import jclass
            picture = jclass('android.widget.ImageView')(app._impl.native)
            class ImageSink:
                def isShowing(self):
                    return True
                def setImage(self, drawable):
                    # Match ComicDisplay's private drawable bounds/callbacks,
                    # while sharing only the already-decoded native bitmap.
                    state = drawable.getConstantState() if drawable is not None else None
                    picture.setImageDrawable(None if state is None else
                        state.newDrawable(app._impl.native.getResources()).mutate())
            output.android = ImageSink()
            def forwarded():
                drawable = picture.getDrawable()
                assert drawable is not None, 'External refresh forwarded no drawable'
                return app.native_image_png(drawable.getBitmap())
        else:
            from rubicon.objc import ObjCClass
            primary = app.main_window._impl.native
            picture = ObjCClass('UIImageView').alloc().init()
            window = ObjCClass('UIWindow').alloc().initWithFrame(primary.bounds)
            # A hidden window in the EXISTING app scene is a native sink only.
            # No external scene, screen, connection or hardware is fabricated.
            window.windowScene = primary.windowScene
            window.setHidden(True)
            output.ios = {'comic-guidance-sink': (primary.windowScene, window, picture)}
            output.ios_status = None
            injected = True
            def forwarded():
                assert picture.image is not None, 'External refresh forwarded no UIImage'
                return app.native_image_png(picture.image)
        output.select(app)
        # Sharing changes the real reading layout. Finish that publication
        # before comparing source/output; keep the access checks fully active.
        await app.position(owner, -1)
        await app.settled(owner)
        output.refresh()
        before = forwarded()
        assert before == app.canvas_png(owner), 'External output differs from its native source'
        await app.swipe(owner, -1, rtl=rtl)
        await app.settled(owner)
        feedback = app.guidance(owner, rtl=rtl, direction=-1, available=False)
        assert feedback.native is not None and output.allowed_host(app)
        output.refresh()
        during = forwarded()
        assert during == before == app.canvas_png(owner), 'Guidance contaminated the external image'
        name = 'comic-guidance-external-' + ('rtl' if rtl else 'ltr')
        (Path(app.paths.cache) / (name + '-before.png')).write_bytes(before)
        (Path(app.paths.cache) / (name + '-during.png')).write_bytes(during)
        report.setdefault('external_images', []).append(dict(rtl=rtl,
            sink='injected native ImageView' if app.android else 'injected native UIImageView',
            physical_display=False, actual_policy_allowed=True, native_refresh=True,
            before_sha256=sha256(before).hexdigest(), during_sha256=sha256(during).hexdigest(),
            screenshots=[name + '-before.png', name + '-during.png']))
    finally:
        try:
            if not app.android:
                if injected:
                    output.clear_ios_status()
                if picture is not None:
                    picture.image = None
                if window is not None:
                    window.setHidden(True)
                    window.windowScene = None
            elif picture is not None:
                picture.setImageDrawable(None)
        finally:
            output.source, output.ios, output.android, output.ios_status = original
            try:
                # Let the real owner undo the temporary sharing-layout state too.
                output.refresh()
            finally:
                await app.close_owner(owner)


async def ordinary_comic_fixture(app, name, *, rtl=False, neighbors=False):
    """Use the actual local import route; ordinary sessions permit iPad scenes."""
    folder = app.private_root / 'Guidance extras' / name
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / '02.cbz'
    expand_comic(source)
    with ZipFile(source, 'a') as archive:
        archive.writestr('ComicInfo.xml', '<ComicInfo><Manga>'
            + ('YesAndRightToLeft' if rtl else 'No') + '</Manga></ComicInfo>')
    if neighbors:
        for sibling in ('01.cbz', '03.cbz'):
            (folder / sibling).write_bytes(source.read_bytes())
    store = app.reader_manager().catalog.library_store
    record = await asyncio.to_thread(store.import_book, LocalDocuments(), source)
    assert await app.open_book(record['id'])
    owner = app.readers.active
    await app.settled(owner)
    assert not owner.session.private_access, 'Extra check requires an ordinary reader'
    await owner.comic_controller().refresh_comic_neighbors()
    return owner, source


async def reduced_motion_check(app, report):
    """The driver sets the real OS preference before launching this scope."""
    assert app.preferences.values['android_eink'] == 'false'
    assert comic_guidance.reduced_motion(app), 'Native OS reduced-motion query is false'
    folder = Path(app.paths.cache)
    for rtl in (False, True):
        owner, source = await ordinary_comic_fixture(app, 'static-' + str(rtl), rtl=rtl)
        try:
            await app.position(owner, -1)
            await app.swipe(owner, -1, rtl=rtl)
            feedback = app.guidance(owner, rtl=rtl, direction=-1, available=False)
            presenter = feedback.native
            app.assert_pass_through(owner, presenter)
            assert not presenter.motion_enabled
            first = float(presenter.hand_position())
            await asyncio.sleep(.35)
            assert feedback.native is presenter and float(presenter.hand_position()) == first
            assert comic_guidance.reduced_motion(app), 'OS preference changed during the static check'
            name = 'comic-guidance-os-static-' + ('rtl' if rtl else 'ltr') + '.png'
            await capture_window(app, folder / name)
            report['static'].append(dict(rtl=rtl, native_os_policy=True, motion_enabled=False,
                x=first, reading=feedback.reading_text, screenshot=name))
            root = presenter.root
            await app.close_owner(owner)
            assert feedback.native is None and feedback.timer is None and app.cue_detached(root)
        finally:
            await app.close_owner(owner)


async def reader_switch_check(app, report):
    """Switch retained ordinary readers while each owns an unexpired cue."""
    first, _ = await ordinary_comic_fixture(app, 'switch-ltr')
    second, _ = await ordinary_comic_fixture(app, 'switch-rtl', rtl=True)
    assert first is not second
    assert await app.open_book(first.session.resource)
    for outgoing, incoming, rtl in ((first, second, False), (second, first, True)):
        assert app.readers.active is outgoing
        await app.position(outgoing, -1)
        await app.swipe(outgoing, -1, rtl=rtl)
        feedback = app.guidance(outgoing, rtl=rtl, direction=-1, available=False)
        root, deadline = feedback.native.root, feedback.deadline
        assert await app.open_book(incoming.session.resource)
        assert app.readers.active is incoming and app.visible_reader() == incoming.session.id
        assert app.loop.time() < deadline, 'Retained-reader switch completed only after cue expiry'
        assert feedback.native is None and feedback.timer is None and app.cue_detached(root)
        assert not feedback.message and feedback.owner is None and not feedback.armed
        await app.settled(incoming)
        report['lifecycle'].append(dict(reader_switch=True, outgoing_rtl=rtl,
            cleared_before_expiry=True, outgoing=outgoing.session.id, incoming=incoming.session.id))
    await app.swipe(first, 1, rtl=False)
    assert first.book_record['position'] == 1
    report['lifecycle'].append(dict(returned_reader_page=1))
    await app.close_owner(second)
    await app.close_owner(first)


async def scene_guidance_check(app, report):
    """One real iPad scene switch while a settled ordinary reader owns a cue."""
    assert not app.android and app.scene_manager.supported, 'Scene scope requires a supported iPad'
    from rubicon.objc import ObjCClass
    manager = app.scene_manager
    application = ObjCClass('UIApplication').sharedApplication
    owner, source = await ordinary_comic_fixture(app, 'scene')
    child, failed = None, False
    try:
        # Pay startup cost before arming; otherwise the 2.5s expiry could make a
        # slow scene creation look like successful focus-loss cleanup.
        assert manager.new_window(), manager.error
        await app.until(lambda: any(host is not app and getattr(host, 'scene_active', False)
                        and not getattr(host, '_startup_in_progress', False)
                        for host in manager.owners.hosts.values()), 'Second native scene did not settle', 20)
        child = next(host for host in manager.owners.hosts.values() if host is not app)
        assert child.native_scene != app.native_scene
        application.requestSceneSessionActivation(app.native_scene.session,
            userActivity=None, options=None, errorHandler=None)
        await app.until(lambda: app.scene_active and not child.scene_active,
                        'Primary scene did not regain focus')
        assert await app.open_book(owner.session.resource)
        owner = app.readers.active
        await app.position(owner, -1)
        await app.swipe(owner, -1, rtl=False)
        feedback = app.guidance(owner, rtl=False, direction=-1, available=False)
        root, deadline = feedback.native.root, feedback.deadline
        application.requestSceneSessionActivation(child.native_scene.session,
            userActivity=None, options=None, errorHandler=None)
        await app.until(lambda: child.scene_active and not app.scene_active,
                        'Second native scene did not take focus', timeout=2)
        assert app.loop.time() < deadline, 'Scene switch completed only after normal cue expiry'
        assert feedback.native is None and feedback.timer is None and app.cue_detached(root), \
            'A live cue survived its owning scene losing focus'
        other = getattr(child, '_comic_boundary_feedback', None)
        assert other is None or (other.native is None and other.timer is None)
        report['lifecycle'].append(dict(native_scene_switch=True, cleared_before_expiry=True,
            primary=app.window_id, child=child.window_id))
        application.requestSceneSessionActivation(app.native_scene.session,
            userActivity=None, options=None, errorHandler=None)
        await app.until(lambda: app.scene_active and not child.scene_active,
                        'Primary scene did not return')
        assert feedback.native is None and feedback.timer is None
        folder = Path(app.paths.cache)
        await capture_window(app, folder / 'comic-guidance-scene-return.png')
    except BaseException:
        failed = True
        raise
    finally:
        try:
            # The simulator can retain inactive scenes: close the child through
            # the same active-window path as the existing native lifecycle test.
            child = child or next((host for host in manager.owners.hosts.values() if host is not app), None)
            if child is not None and child.active_host:
                application.requestSceneSessionActivation(child.native_scene.session,
                    userActivity=None, options=None, errorHandler=None)
                await app.until(lambda: child.scene_active, 'Child scene did not reactivate for cleanup')
                assert manager.close_window(child), manager.error
                await app.until(lambda: len(manager.owners.hosts) == 1, 'Child scene did not disconnect')
            application.requestSceneSessionActivation(app.native_scene.session,
                userActivity=None, options=None, errorHandler=None)
            await app.until(lambda: app.scene_active, 'Primary scene did not return after cleanup')
            report['scene_cleanup'] = True
        except Exception:
            report['scene_cleanup'] = False
            report['scene_cleanup_error'] = traceback.format_exc()
            if not failed:
                raise


async def fold_guidance_check(app, report):
    """Two orientations on a real partial Duo pose supplied by the driver."""
    assert not app.android, 'Fold scope requires the supported UIKit reserved-region path'
    from dataclasses import asdict
    from rubicon.objc import CGRect
    from mobile.fold_layout import division
    owner, source = await ordinary_comic_fixture(app, 'fold', neighbors=True)
    folder = Path(app.paths.cache)
    report['folds'] = []
    for orientation in ('portrait', 'landscape-left'):
        await rotate(app, orientation, settle=.2)
        await app.position(owner, -1)
        await owner.comic_controller().refresh_comic_neighbors()
        content = owner.book_content
        fold = division(owner, content)
        assert fold is not None, 'UIKit did not publish an active division for ' + orientation
        native = content._impl.native
        rect = native.convertRect(CGRect((fold.x, fold.y), (fold.width, fold.height)),
                                  toView=app.main_window._impl.native)
        crease = tuple(map(float, (rect.origin.x, rect.origin.y, rect.size.width, rect.size.height)))
        await app.swipe(owner, -1, rtl=False)
        feedback = app.guidance(owner, rtl=False, direction=-1, available=True)
        await app.settled(owner)
        presenter = feedback.native
        assert presenter is not None
        report['fold_geometry'] = dict(orientation=orientation, division=asdict(fold), crease=crease,
            content=list(app.frame(content._impl.native)), canvas=list(app.frame(app.canvas(owner)._impl.native)),
            cue=list(presenter.geometry))
        app.record_progress(report, 'fold-hit-test')
        app.assert_pass_through(owner, presenter)
        x, y, width, height = tuple(map(float, presenter.geometry))
        if fold.vertical:
            assert x + width <= crease[0] + 2, (presenter.geometry, crease)
        else:
            assert y + height <= crease[1] + 2, (presenter.geometry, crease)
        for view in (presenter.hand, presenter.reading, presenter.volume):
            vx, vy, vw, vh = app.frame(view)
            assert vx >= x - 2 and vy >= y - 2 and vx + vw <= x + width + 2 and vy + vh <= y + height + 2
        name = 'comic-guidance-fold-' + orientation + '.png'
        await capture_window(app, folder / name)
        report['folds'].append(dict(orientation=orientation, division=asdict(fold), crease=crease,
            geometry=list(presenter.geometry), native_pose=pose_snapshot(app), screenshot=name))
        row = report['folds'][-1]
        if len(report['folds']) == 1:
            # The simulator's first HID connection can exceed the whole cue
            # lifetime. Warm it without a cue before measuring pass-through.
            comic_feedback.clear(app)
            cx, cy, cw, ch = app.frame(app.canvas(owner)._impl.native)
            immersive = owner.reader_immersive
            await app.driver_action('native-tap', points=[cx + cw / 2, cy + ch / 2])
            await app.until(lambda: owner.reader_immersive != immersive, 'Native touch warmup failed')
            report['native_touch_warmup'] = True
        # Fresh cues keep tool latency from silently replacing a pass-through
        # check with an ordinary tap/swipe after the hint has expired.
        await app.position(owner, -1)
        await app.swipe(owner, -1, rtl=False)
        feedback = app.guidance(owner, rtl=False, direction=-1, available=True)
        presenter, deadline = feedback.native, feedback.deadline
        hx, hy, hw, hh = app.frame(presenter.hand)
        hx += presenter.hand_position() - float(presenter.hand.frame.origin.x)
        tap = [hx + hw / 2, hy + hh / 2]
        immersive = owner.reader_immersive
        canvas, events = app.canvas(owner), []
        toggle = canvas.on_toggle
        def tapped(*args):
            events.append(dict(live=feedback.native is presenter, before_expiry=app.loop.time() < deadline))
            return toggle(*args)
        canvas.on_toggle = tapped
        try:
            await app.driver_action('native-tap', points=tap)
            await app.until(lambda: owner.reader_immersive != immersive, 'Native tap did not reach the folded reader')
        finally:
            canvas.on_toggle = toggle
        assert events and all(event['live'] and event['before_expiry'] for event in events), events
        row['native_tap'] = dict(points=tap, controls_toggled=True, callback_events=events,
            acknowledgment_before_expiry=app.loop.time() < deadline)
        await app.position(owner, -1)
        await app.swipe(owner, -1, rtl=False)
        feedback = app.guidance(owner, rtl=False, direction=-1, available=True)
        root, deadline = feedback.native.root, feedback.deadline
        x, y, width, height = app.frame(app.canvas(owner)._impl.native)
        # Stay on the actual canvas inside one usable fold region; a physical
        # gesture through the system's reserved crease is not a reader touch.
        gx, gy, gw, gh = feedback.native.geometry
        right, bottom = min(x + width, gx + gw), min(y + height, gy + gh)
        x, y = max(x, gx), max(y, gy)
        width, height = right - x, bottom - y
        assert width > 48 and height > 48, 'Fold left no usable native gesture surface'
        swipe = [x + .75 * width, y + .5 * height, x + .25 * width, y + .5 * height]
        canvas, events = app.canvas(owner), []
        turn = canvas.on_page
        def turned(direction):
            events.append(dict(live=feedback.native is not None, before_expiry=app.loop.time() < deadline,
                               direction=direction))
            return turn(direction)
        canvas.on_page = turned
        try:
            await app.driver_action('native-swipe', points=swipe)
            await app.until(lambda: owner.book_record['position'] == 1, 'Native swipe did not open page 1')
        finally:
            canvas.on_page = turn
        assert events and all(event['live'] and event['before_expiry'] for event in events), events
        assert feedback.native is None and feedback.timer is None and app.cue_detached(root)
        row['native_swipe'] = dict(points=swipe, page_opened=1, cue_cleared=True, callback_events=events,
            acknowledgment_before_expiry=app.loop.time() < deadline)
        app.record_progress(report, 'fold')
    assert {row['division']['height'] > row['division']['width'] for row in report['folds']} == {False, True}, \
        'The two real orientations did not exercise both fold axes'


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
