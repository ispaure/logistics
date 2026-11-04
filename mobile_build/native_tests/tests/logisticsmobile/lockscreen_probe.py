"""Real resume form, rotation and software-keyboard checks on disposable devices."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.testing.waiting import wait_until
from mobile.app import LogisticsMobile
from services.session_auth import ResumePassword
from .fixtures import capture_window
from .rotation_checks import rotate

BUNDLE = 'io.github.ispaure.logisticsnotebookqa'
PASSWORD = 'synthetic-lock-password'
POSES = ('portrait', 'landscape-left', 'landscape-right', 'portrait')


class LockScreenProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'lockscreen-workspace'
        super().startup()

    def on_running(self):
        if not getattr(self, '_lock_probe', None):
            self._lock_probe = self.loop.create_task(self.exercise())

    @property
    def apple(self):
        return type(self._impl).__module__.startswith('toga_iOS.')

    def rect(self, widget):
        native = widget._impl.native
        if self.apple:
            window = self.main_window._impl.native
            rect = native.convertRect(native.bounds, toView=window)
            return dict(x=float(rect.origin.x), y=float(rect.origin.y),
                        width=float(rect.size.width), height=float(rect.size.height))
        from java import jarray, jint
        position = jarray(jint)(2)
        native.getLocationOnScreen(position)
        density = float(native.getResources().getDisplayMetrics().density)
        return dict(x=float(position[0]) / density, y=float(position[1]) / density,
                    width=float(native.getWidth()) / density, height=float(native.getHeight()) / density)

    def keyboard(self):
        field = self.screen_privacy.lock_password.field._impl.native
        if self.apple:
            window = self.main_window._impl.native
            frame = self.native_host.adapter.keyboard_frame
            if frame is None:
                return dict(visible=False)
            rect = window.convertRect(frame, fromCoordinateSpace=window.screen.coordinateSpace)
            return dict(visible=float(rect.size.height) > 100 and float(rect.origin.y) < float(window.bounds.size.height) - 1,
                        focused=bool(field.isFirstResponder),
                        top=float(rect.origin.y), height=float(rect.size.height))
        from java import jclass
        insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(
            self._impl.native.getWindow().getDecorView())
        ime = jclass('androidx.core.view.WindowInsetsCompat$Type').ime()
        density = float(field.getResources().getDisplayMetrics().density)
        height = float(insets.getInsets(ime).bottom) / density if insets else 0
        from android.graphics import Rect
        visible = Rect()
        self._impl.native.getWindow().getDecorView().getWindowVisibleDisplayFrame(visible)
        return dict(visible=bool(insets and insets.isVisible(ime)), height=height,
                    top=float(visible.bottom) / density)

    async def rotate_lock(self, pose):
        if self.apple:
            await rotate(self, pose)
            return
        from commonUtils.testing.rotation import NativeRotation, ORIENTATIONS
        from commonUtils.testing.settings import ROTATION_TIMEOUT
        activity = self._impl.native
        NativeRotation(self.main_window, activity=activity).request(pose)
        configuration = ORIENTATIONS[pose][3]
        expected_rotation = {'portrait': 0, 'landscape-left': 1, 'landscape-right': 3}[pose]
        def acknowledged():
            # The ordinary navigation root is detached while locked, so Toga's
            # cached window.size is not the active Activity display geometry.
            decor = activity.getWindow().getDecorView()
            return (int(activity.getResources().getConfiguration().orientation) == configuration
                    and int(activity.getDisplay().getRotation()) == expected_rotation
                    and (decor.getWidth() > decor.getHeight()) == (configuration == 2))
        await wait_until(acknowledged, timeout=ROTATION_TIMEOUT,
                         message='Lock Activity did not rotate: ' + pose)
        await asyncio.sleep(.5)

    async def open_keyboard(self):
        field = self.screen_privacy.lock_password.field._impl.native
        for _ in range(60):
            if self.apple:
                field.becomeFirstResponder()
            else:
                from android.content import Context
                from java import jclass
                field.requestFocus()
                controller = jclass('androidx.core.view.WindowCompat').getInsetsController(
                    self._impl.native.getWindow(), field)
                controller.show(jclass('androidx.core.view.WindowInsetsCompat$Type').ime())
                field.getContext().getSystemService(Context.INPUT_METHOD_SERVICE).showSoftInput(field, 0)
            await asyncio.sleep(.1)
            if self.keyboard()['visible']:
                return
        raise AssertionError('Native software keyboard did not open')

    async def type_password(self, value):
        field = self.screen_privacy.lock_password.field._impl.native
        self.screen_privacy.lock_password.value = ''
        if self.apple:
            field.insertText(value)
        else:
            from android.view.inputmethod import EditorInfo
            connection = field.onCreateInputConnection(EditorInfo())
            assert connection is not None and connection.commitText(value, 1)
        await wait_until(lambda: self.screen_privacy.lock_password.value == value,
                         message='Native password typing did not reach the form')

    async def dismiss_keyboard(self):
        if self.apple:
            self.main_window._impl.native.endEditing(True)
        else:
            from java import jclass
            field = self.screen_privacy.lock_password.field._impl.native
            jclass('androidx.core.view.WindowCompat').getInsetsController(
                self._impl.native.getWindow(), field).hide(
                    jclass('androidx.core.view.WindowInsetsCompat$Type').ime())
            field.clearFocus()
        await asyncio.sleep(.5)

    async def reveal_control(self, control):
        # Use native scrolling, as a user would, without changing form layout.
        native = control._impl.native
        if self.apple:
            scroll = self.screen_privacy.lock_scroll._impl.native
            rect = native.convertRect(native.bounds, toView=scroll)
            scroll.scrollRectToVisible(rect, animated=False)
        else:
            from android.graphics import Rect
            native.requestRectangleOnScreen(Rect(0, 0, native.getWidth(), native.getHeight()), True)
        await asyncio.sleep(.4)
        # Android nests a horizontal viewport inside its vertical ScrollView;
        # rectangle requests can stop at that inner parent. Move the existing
        # vertical scroll position, equivalent to dragging the form, if needed.
        scroll = self.screen_privacy.lock_scroll
        item, viewport = self.rect(control), self.rect(scroll)
        delta = (item['y'] - viewport['y'] if item['y'] < viewport['y'] else
                 max(0, item['y'] + item['height'] - viewport['y'] - viewport['height']))
        if abs(delta) > .5:
            scroll.vertical_position = max(0, min(scroll.max_vertical_position,
                                                 scroll.vertical_position + delta))
            await asyncio.sleep(.4)

    async def capture(self, name):
        # The host also captures the actual screen, including the separate IME.
        # Android enables screenshots only during this synthetic QA handshake.
        if not self.apple:
            self._impl.native.getWindow().clearFlags(0x2000)
        await capture_window(self, Path(self.paths.cache) / ('lock-' + name + '.png'))
        cache = Path(self.paths.cache)
        done = cache / 'lockscreen-capture-done'
        done.unlink(missing_ok=True)
        pending = cache / 'lockscreen-capture.tmp'
        pending.write_text(json.dumps(dict(name=name)))
        pending.replace(cache / 'lockscreen-capture.json')
        try:
            await wait_until(done.exists, timeout=30, message='System screenshot was not collected')
        finally:
            if not self.apple:
                self._impl.native.getWindow().addFlags(0x2000)

    def sample(self, pose, keyboard):
        privacy = self.screen_privacy
        sample = dict(pose=pose, keyboard=keyboard, root=self.rect(privacy.lock_view), card=self.rect(privacy.lock_card),
            viewport=self.rect(privacy.lock_scroll), field=self.rect(privacy.lock_password.field),
            button=self.rect(privacy.lock_button), ime=self.keyboard(),
            scroll=privacy.lock_scroll.vertical_position,
            max_scroll=privacy.lock_scroll.max_vertical_position)
        self.report['samples'].append(sample)
        self.publish()
        card, viewport = sample['card'], sample['root']
        assert card['width'] > 200 and viewport['height'] > 80, sample
        assert card['x'] >= viewport['x'] + 10, sample
        assert card['x'] + card['width'] <= viewport['x'] + viewport['width'] - 10, sample
        assert card['y'] >= viewport['y'] + 10, sample
        assert card['y'] + card['height'] <= viewport['y'] + viewport['height'] - 10, sample
        if sample['ime']['visible']:
            assert card['y'] + card['height'] <= sample['ime']['top'] - 10, sample
        assert self.main_window.content is privacy.lock_view
        return sample

    def publish(self):
        target = Path(self.paths.cache) / 'lockscreen-result.json'
        pending = target.with_suffix('.tmp')
        pending.write_text(json.dumps(self.report, indent=2))
        pending.replace(target)

    async def exercise(self):
        self.report = dict(success=False, samples=[], phase='starting')
        privacy = self.screen_privacy
        release = None
        try:
            await asyncio.sleep(1)
            self.gate = ResumePassword(PASSWORD, credential_name='Personal notebook credential with a long name.zip')
            release = self.protection.register(self, lambda: (self.gate,))
            self.gate.lock()
            privacy.refresh()
            await wait_until(lambda: self.main_window.content is privacy.lock_view)
            original = privacy.saved_content
            for ordinal, pose in enumerate(POSES):
                await self.dismiss_keyboard()
                (Path(self.paths.cache) / 'creation-orientation').write_text(pose)
                await self.rotate_lock(pose)
                privacy.lock_scroll.vertical_position = 0
                await asyncio.sleep(.5)
                self.sample(pose, False)
                await self.capture(f'{ordinal}-{pose}')
                privacy.lock_password.value = 'rotation-keeps-this'
                await self.open_keyboard()
                await self.type_password('rotation-keeps-this')
                await asyncio.sleep(.4)
                assert privacy.lock_password.value == 'rotation-keeps-this'
                sample = self.sample(pose, True)
                assert sample['ime']['visible'], sample
                await self.reveal_control(privacy.lock_password.field)
                sample = self.sample(pose, True)
                assert sample['field']['y'] + sample['field']['height'] <= sample['ime']['top'] + 2, sample
                await self.capture(f'{ordinal}-{pose}-keyboard')
                # Rotate with the keyboard open, preserving the same field/value.
                next_pose = 'landscape-left' if pose == 'portrait' else 'portrait'
                (Path(self.paths.cache) / 'creation-orientation').write_text(next_pose)
                await self.rotate_lock(next_pose)
                await asyncio.sleep(.4)
                assert privacy.lock_password.value == 'rotation-keeps-this'
                assert self.keyboard()['visible'], 'Rotation dismissed the keyboard'
                self.sample(next_pose, True)
                await self.capture(f'rotation-{ordinal}-{next_pose}-keyboard')
            await self.dismiss_keyboard()
            privacy.lock_password.value = 'wrong-password'
            await privacy.unlock()
            assert self.gate.locked and self.main_window.content is privacy.lock_view
            await self.open_keyboard()
            privacy.lock_password.value = PASSWORD
            await self.reveal_control(privacy.lock_button)
            sample = self.sample('final', True)
            assert sample['button']['y'] >= sample['viewport']['y'] - 2, sample
            assert sample['button']['height'] >= 44, sample
            assert sample['button']['y'] + sample['button']['height'] <= sample['ime']['top'] + 2, sample
            await self.capture('unlock-keyboard')
            # Dispatch through the actual native button instead of calling unlock.
            if self.apple:
                privacy.lock_button._impl.native.sendActionsForControlEvents(1 << 6)
            else:
                privacy.lock_button._impl.native.performClick()
            await wait_until(lambda: not self.gate.locked, timeout=15)
            assert self.main_window.content is original
            assert privacy.android_lock_layout is None
            assert privacy.lock_password.value == ''
            await wait_until(lambda: not self.keyboard()['visible'], timeout=10,
                             message='Unlock left the software keyboard open')
            self.report.update(success=True, phase='complete', wrong_password_rejected=True,
                               native_button_unlock=True, navigation_restored=True)
        except Exception:
            self.report.update(phase='failed', error=traceback.format_exc())
            traceback.print_exc()
        finally:
            if release is not None:
                release()
            self.publish()
            print('LOCKSCREEN_RESULT=' + json.dumps(self.report), flush=True)


def main():
    return LockScreenProbe('Lock screen QA', BUNDLE)
