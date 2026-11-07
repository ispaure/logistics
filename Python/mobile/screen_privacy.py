"""Native snapshot shielding and supported screen-capture protection.

iOS public APIs cannot prevent still screenshots. Never claim otherwise or
reparent UIKit views into undocumented secure-text-field internals.
"""
import logging

from commonUtils.ui.native.password_input import PasswordInput


def native_value(owner, name):
    """Rubicon exposes custom Objective-C getters as bound methods."""
    value = getattr(owner, name)
    return value() if callable(value) else value


class ScreenPrivacy:
    def __init__(self, app):
        self.app = app
        from threading import get_ident
        self.ui_thread = get_ident()
        self.disposed = False
        self.inactive = False
        self.interrupted = False
        self.captured = False
        self.observers = []
        self.shield = None
        self.lock_view = None
        self.saved_content = None
        self.saved_lock_layout = None
        self.android_lock_layout = None
        self.lock_gates = ()
        self.unlock_busy = False
        self.lock_layout_subscription = None
        self.credential_observers = None
        self.protection_scope = None
        self.activity_listener = self.application = None
        self.trait_registration = self.trait_block = self.trait_window = None
        self.backend = type(app._impl).__module__
        try:
            from .layout_participants import participants
            self.lock_layout_subscription = participants(app).register(
                ('resume-lock', id(self)), self, lambda owner, frame: owner.fit_lock_view(frame.width))
            from .trusted_wifi import WifiResume
            self.wifi_resume = WifiResume()
            from features.rclone.mobile.cloud import CloudClient
            self.credential_observers = CloudClient.credential_state.observers
            self.credential_observers.add(self)
            self.install_native_observers()
            from .protection import for_app
            self.protection_scope = for_app(app)
            self.protection_scope.process.listeners.add(self)
            self.refresh()
        except Exception:
            try:
                self.dispose()
            except Exception:
                logging.getLogger(__name__).error('Could not roll back screen privacy setup.')
            raise

    def install_native_observers(self):
        if self.backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, Block, objc_id
            self.center = ObjCClass('NSNotificationCenter').defaultCenter
            for name, callback in (
                ('UIApplicationWillResignActiveNotification', self.interrupt),
                ('UIApplicationDidEnterBackgroundNotification', self.conceal),
                ('UIApplicationProtectedDataWillBecomeUnavailable', self.conceal),
                ('UIApplicationDidBecomeActiveNotification', self.reveal),
                ('UIScreenCapturedDidChangeNotification', self.refresh),
                ('UIAccessibilityReduceTransparencyStatusDidChangeNotification', self.artwork_accessibility_changed),
            ):
                block = Block(lambda notification, callback=callback: callback(), None, objc_id)
                token = self.center.addObserverForName(name, object=None, queue=None, usingBlock=block)
                self.observers.append((token, block))
            window = self.app.main_window._impl.native
            if window.respondsToSelector('registerForTraitChanges:withHandler:'):
                self.trait_window = window
                self.trait_block = Block(lambda view, previous: self.refresh(), None, objc_id, objc_id)
                self.trait_registration = window.registerForTraitChanges(
                    [ObjCClass('UITraitSceneCaptureState')], withHandler=self.trait_block)
        elif self.backend.startswith('toga_android.'):
            self.install_android_lifecycle()

    def protection_changed(self, active):
        if not self.disposed and not self.app.loop.is_closed():
            from threading import get_ident
            if get_ident() == self.ui_thread:
                self.prepare_native_protection()
            self.app.loop.call_soon_threadsafe(self.refresh)

    def artwork_accessibility_changed(self):
        if self.disposed:
            return
        # No size change is required when accessibility changes. Force the
        # container policy before the ordinary coalesced reader refresh.
        app = self.app
        app.resize_workspace()
        if app.body.children:
            container = app.body.children[0]._impl.container
            if container is not None:
                app.native_host.adapter.layout_content(container)
        from .ios_content_background import sync
        sync(app)

    def install_android_lifecycle(self):
        from android.app import Application
        from java import dynamic_proxy
        privacy = self

        class Listener(dynamic_proxy(Application.ActivityLifecycleCallbacks)):
            def onActivityPaused(self, activity):
                if not privacy.disposed and activity == privacy.app._impl.native:
                    privacy.conceal()

            def onActivityResumed(self, activity):
                if not privacy.disposed and activity == privacy.app._impl.native:
                    privacy.reveal()

            def onActivityConfigurationChanged(self, activity):
                # Chaquopy proxies dispatch this Android default method to
                # Python too, including uiMode changes without recreation.
                if not privacy.disposed and activity == privacy.app._impl.native:
                    privacy.refresh()

            def onActivityCreated(self, activity, state):
                pass

            def onActivityStarted(self, activity):
                pass

            def onActivityStopped(self, activity):
                pass

            def onActivitySaveInstanceState(self, activity, state):
                pass

            def onActivityDestroyed(self, activity):
                pass

        self.application = self.app._impl.native.getApplication()
        self.activity_listener = Listener()
        self.application.registerActivityLifecycleCallbacks(self.activity_listener)

    def credentials_changed(self):
        if not self.disposed and not self.app.loop.is_closed():
            self.app.loop.call_soon_threadsafe(self.retire_stale)

    def retire_stale(self):
        if self.disposed or not self.app.active_host:
            return
        # Cover capture/native snapshots before feature retirement can reenter UI.
        self.refresh()
        from .privacy_effects import retire_stale_content
        retire_stale_content(self.app)
        self.refresh()

    def gates(self):
        from .protection import for_app
        return for_app(self.app).gates()

    def credential_gates(self):
        from .protection import for_app
        return for_app(self.app).process.credentials()

    @property
    def resume_locked(self):
        return any(gate.locked for gate in self.gates())

    def sensitive(self):
        from .protection import for_app
        return for_app(self.app).process.protected()

    def interrupt(self):
        """Lock protected sessions on app switcher and Control Center interruptions."""
        if self.disposed:
            return
        self.interrupted = True
        self.wifi_revision = getattr(self, 'wifi_revision', 0) + 1
        if self.sensitive():
            self.conceal()
        else:
            self.prepare_native_protection()

    def conceal(self):
        if self.disposed:
            return
        self.inactive = True  # Deny reentrant playback before native/UI effects.
        # Native shielding and player callbacks can fail or reenter the loop.
        # Invalidate outstanding authentication before invoking any of them.
        self.wifi_revision = getattr(self, 'wifi_revision', 0) + 1
        self.prepare_native_protection()
        private = getattr(self.app, 'private_sessions', None)
        if private is not None:
            private.flush_visible_progress()
        readers = getattr(self.app, 'readers', None)
        if readers is not None:
            readers.flush_progress()
        if self.sensitive():
            from .privacy_effects import dismiss_floating_panels
            dismiss_floating_panels(self.app)
        output = getattr(self.app, 'audio_output', None)
        if output is not None:
            output.invalidate(pause=False)  # Reject dialogs without stopping permitted background speech.
        notes = getattr(self.app, 'vault_browser', None)
        pause_inline = getattr(notes, 'pause_inline_videos', None)
        if pause_inline is not None:
            pause_inline()
        video = getattr(self.app, 'video_player', None)
        if video is not None:
            video.conceal()
        from .comic_feedback import clear as clear_comic_feedback
        clear_comic_feedback(self.app)
        from .page_animation import cancel_visible_slides
        cancel_visible_slides(self.app)
        from .ios_content_background import clear
        clear(self.app)
        from .browser_ui import sync_browser_population
        sync_browser_population(self.app)
        from features.books.mobile.media_controls import enforce_privacy
        enforce_privacy(self.app)
        if self.lock_view is not None:
            self.lock_password.value = self.lock_confirmation.value = ''
        from .trusted_wifi import WifiResume
        if not hasattr(self, 'wifi_resume'):
            self.wifi_resume = WifiResume()
        gates = self.gates()
        self.wifi_resume.capture(gates, self.credential_gates())
        for gate in gates:
            gate.lock(reason='lifecycle')
        picker = getattr(self.app, '_editor_picker', None)
        if picker is not None:
            picker.cancel(interrupted=True)
        # Cover synchronously before releasing anything or taking a snapshot.
        self.refresh()
        self.app.retire_private_comic_batch()
        self.refresh()
        self.refresh_other_windows()

    def refresh_other_windows(self):
        from features.rclone.mobile.cloud import CloudClient
        for observer in tuple(CloudClient.credential_state.observers):
            if observer is not self and not observer.disposed and not observer.app.loop.is_closed():
                observer.app.loop.call_soon_threadsafe(observer.refresh)

    def reveal(self):
        if self.disposed:
            return
        values = getattr(getattr(self.app, 'preferences', None), 'values', {})
        self.wifi_revision = getattr(self, 'wifi_revision', 0) + 1
        if (self.backend.startswith(('toga_iOS.', 'toga_android.')) and hasattr(self, 'wifi_resume')
                and self.wifi_resume.pending and values.get('session_trusted_wifi') == 'true'):
            # Privacy boundary: never restore document content speculatively.
            # Keep the shield and lock root until a fresh Wi-Fi result authorizes
            # resume. Capture protection is independent of this password waiver.
            # A later lifecycle transition invalidates this callback.
            self.app.loop.create_task(self.resume_on_wifi(self.wifi_revision))
            return
        from .trusted_wifi import current_ssid
        ssid = current_ssid(self.app) if values.get('session_trusted_wifi') == 'true' else None
        self.finish_reveal(ssid)

    async def resume_on_wifi(self, revision):
        if self.disposed:
            return
        from .trusted_wifi import read_ssid
        preferences = self.app.preferences.values
        settings = (preferences.get('session_trusted_wifi'), preferences.get('trusted_wifi_networks'))
        try:
            ssid = await read_ssid(self.app)
        except Exception:
            ssid = None  # A failed native lookup must fall back to password authentication.
        if not self.disposed and self.wifi_revision == revision:
            current = self.app.preferences.values
            if settings != (current.get('session_trusted_wifi'), current.get('trusted_wifi_networks')):
                ssid = None
            self.finish_reveal(ssid)

    def finish_reveal(self, ssid):
        # A credential import may finish before its queued refresh runs.
        self.lock_new_gates(self.gates())
        if hasattr(self, 'wifi_resume'):
            self.wifi_resume.resume(self.app, self.gates(), self.credential_gates(), ssid)
        self.inactive = False
        self.interrupted = False
        self.refresh()
        self.resume_reader()
        from .ios_content_background import sync
        sync(self.app)
        from .browser_ui import sync_browser_population
        sync_browser_population(self.app)

    def resume_reader(self):
        """Memory pressure can retire the visible page while the lock is up."""
        if self.inactive or any(gate.locked for gate in self.gates()):
            return
        video = getattr(self.app, 'video_player', None)
        if video is not None:
            video.reveal()
        for name in ('private_sessions', 'readers'):
            manager = getattr(self.app, name, None)
            owner = getattr(manager, 'active', None)
            session = getattr(owner, 'session', None)
            if session is not None and self.app.visible_reader() == session.id:
                owner.resume_suspended_page()

    def prepare_native_protection(self, *, transitioning=False):
        """Apply native concealment before callbacks can mutate presentation."""
        protected = self.sensitive()
        if self.backend.startswith('toga_iOS.'):
            window = self.app.main_window._impl.native
            captured = bool(native_value(window.screen, 'isCaptured'))
            traits = window.traitCollection
            if traits.respondsToSelector('sceneCaptureState'):
                captured = captured or native_value(traits, 'sceneCaptureState') == 1
            self.captured = captured
            scene = window.windowScene
            scene_inactive = scene is not None and native_value(scene, 'activationState') != 0
            if protected or self.inactive or self.interrupted or scene_inactive or captured:
                output = getattr(getattr(self.app, 'scene_manager', None), 'external_comics', None)
                if output is not None and (protected or (output.source is not None and output.source() is self.app)):
                    output.reader_cover.clear()
            hidden = protected and (self.inactive or getattr(self, 'interrupted', False) or scene_inactive or captured)
            self.set_ios_shield(hidden or (transitioning and protected and self.resume_locked))
            return hidden
        if self.backend.startswith('toga_android.'):
            window = self.app._impl.native.getWindow()
            if protected:
                window.addFlags(0x00002000)  # Supported FLAG_SECURE.
            else:
                window.clearFlags(0x00002000)
        return False

    def set_ios_shield(self, hidden):
        window = self.app.main_window._impl.native
        if hidden:
            from rubicon.objc import ObjCClass
            if self.shield is None:
                self.shield = ObjCClass('UIView').alloc().initWithFrame(window.bounds)
                self.shield.backgroundColor = native_value(ObjCClass('UIColor'), 'blackColor')
                self.shield.opaque = True
                self.shield.autoresizingMask = 18
                self.shield.userInteractionEnabled = True
                self.shield.accessibilityLabel = 'Private content hidden'
                self.shield.accessibilityViewIsModal = True
            self.shield.frame = window.bounds
            window.addSubview(self.shield)  # Reattach after native root replacement.
            window.endEditing(True)
        elif self.shield is not None:
            self.shield.removeFromSuperview()
            self.shield = None

    def lock_new_gates(self, gates):
        # Late imports cannot inherit an earlier window's authentication.
        for gate in gates:
            if not gate.locked and (self.inactive or getattr(self, 'interrupted', False)
                                    or (self.lock_gates and gate not in self.lock_gates)):
                gate.lock(reason='challenge')

    def refresh(self):
        if self.disposed:
            return
        from .protection import for_app
        scope = for_app(self.app)
        gates = self.gates()
        self.lock_new_gates(gates)
        hidden = self.prepare_native_protection(transitioning=True)
        scope.changed()
        video = getattr(self.app, 'video_player', None)
        if video is not None:
            video.retire_changed_policy()
        self.sync_lock_view(gates)
        output = getattr(self.app, 'audio_output', None)
        if output is not None:
            output.capture_changed(self.sensitive() and self.captured)
        video = getattr(self.app, 'video_player', None)
        if video is not None:
            if self.sensitive() and (self.inactive or getattr(self, 'interrupted', False)
                                     or self.captured or self.resume_locked):
                video.conceal()
            elif not hidden:
                video.reveal()  # Restore controls, never playback.
        if hidden:
            from .ios_content_background import clear
            clear(self.app)
        from .browser_ui import sync_browser_population
        sync_browser_population(self.app)
        from .external_display import sync as sync_external
        sync_external(self.app)
        # Reveal only after all required protection effects completed.
        if self.backend.startswith('toga_iOS.'):
            self.set_ios_shield(hidden)

    def sync_lock_view(self, gates):
        """Replace the entire navigation root; routes may update safely behind it."""
        locked = any(gate.locked for gate in gates)
        if locked:
            from .privacy_effects import dismiss_floating_panels
            dismiss_floating_panels(self.app)
            from .comic_feedback import clear as clear_comic_feedback
            clear_comic_feedback(self.app)
            from features.books.mobile.media_controls import enforce_privacy
            enforce_privacy(self.app)
            self.lock_gates = gates
            if self.lock_view is None:
                import toga
                from toga.style import Pack
                from toga.style.pack import COLUMN, CENTER
                from .appearance import action_button, surface
                self.lock_icon = toga.Label('🔒', style=Pack(font_size=40, text_align=CENTER, margin_bottom=12))
                from .settings.forms import SettingsLabel
                self.lock_title = SettingsLabel('Welcome back', style=Pack(font_size=24, font_weight='bold', margin_bottom=8))
                self.lock_credential = SettingsLabel('', style=Pack(font_size=16, font_weight='bold', margin_top=16, margin_bottom=12))
                self.lock_hint = SettingsLabel('Enter the session password to resume.')
                self.lock_password = PasswordInput(placeholder='Session password',
                    on_confirm=self.unlock, style=Pack(height=48))
                self.lock_confirmation = PasswordInput(placeholder='Confirm new lock password',
                    style=Pack(height=48))
                from .keyboard import prepare_picker_input
                prepare_picker_input(self.lock_password.field)
                prepare_picker_input(self.lock_confirmation.field)
                self.lock_status = SettingsLabel('', style=Pack(margin_top=12))
                self.lock_button = action_button(toga.Button('Unlock', on_press=self.unlock, style=Pack(height=48, margin_top=16)))
                self.lock_fields = toga.Box(children=[self.lock_title, self.lock_hint,
                    self.lock_credential, self.lock_password, self.lock_button, self.lock_status],
                    style=Pack(direction=COLUMN, flex=1))
                self.lock_layout = toga.Box(children=[self.lock_icon, self.lock_fields],
                    style=Pack(direction=COLUMN, margin=12))
                backend = type(self.lock_icon._impl).__module__
                if backend.startswith('toga_iOS.'):
                    self.lock_icon._impl.native.isAccessibilityElement = False
                elif backend.startswith('toga_android.'):
                    self.lock_icon._impl.native.setImportantForAccessibility(2)  # NO
                # The rounded surface stays inside the viewport; only its
                # form scrolls, preserving all corners on short/IME layouts.
                class LockFormScroll(toga.ScrollContainer):
                    # The bounded card owns size, including IME heights below
                    # Toga's ordinary 100-point scrolling-widget minimum.
                    _MIN_HEIGHT = 0
                self.lock_scroll = LockFormScroll(horizontal=False,
                    content=self.lock_layout, style=Pack(flex=1, margin=12))
                self.lock_card = surface(toga.Box(children=[self.lock_scroll],
                    style=Pack(direction=COLUMN)), radius=20)
                self.lock_body = toga.Box(children=[self.lock_card],
                    style=Pack(direction=COLUMN, align_items=CENTER, flex=1, margin=20))
                self.lock_view = toga.Box(children=[self.lock_body],
                    style=Pack(direction=COLUMN, flex=1))
            pending = tuple(gate for gate in gates if gate.locked)
            names = list(dict.fromkeys(getattr(gate, 'credential_name', '') for gate in pending
                                       if getattr(gate, 'credential_name', '')))
            labels = names + (['Private session'] if any(not getattr(gate, 'credential_name', '') for gate in pending) else [])
            self.lock_credential.text = '\n'.join(labels)
            setup = any(gate.proof is None for gate in pending)
            self.lock_title.text = 'Set session password' if setup else 'Session locked'
            self.lock_hint.text = ('Create a temporary password to protect this session.' if setup
                else ('Enter the password for this credential file.' if len(labels) == 1 and names and names[0].lower().endswith('.zip')
                      else 'Enter a listed credential’s password to continue.' if names
                      else 'Enter your private session password to continue.'))
            self.lock_password.placeholder = 'New session password' if setup else 'Credential password' if names else 'Session password'
            if setup and self.lock_confirmation not in self.lock_fields.children:
                self.lock_fields.insert(self.lock_fields.children.index(self.lock_password) + 1, self.lock_confirmation)
            elif not setup and self.lock_confirmation in self.lock_fields.children:
                self.lock_fields.remove(self.lock_confirmation)
            self.lock_button.text = 'Set lock password' if setup else 'Unlock'
            self.fit_lock_view()
            if self.app.main_window.content is not self.lock_view:
                self.saved_content = self.app.main_window.content
                if self.backend.startswith('toga_iOS.'):
                    container = self.app.main_window._impl.container
                    self.saved_lock_layout = container.on_native_layout
                    container.on_native_layout = self.layout_lock_view
                self.app.main_window.content = self.lock_view
                if self.backend.startswith('toga_android.'):
                    self.install_android_lock_layout()
                    host = getattr(self.app, 'native_host', None)
                    if host is not None and getattr(host.adapter, '_reader_action_bar_active', False):
                        from .android_reader_chrome import sync
                        sync(self.app, object(), host.state.destination)
                if self.backend.startswith('toga_iOS.'):
                    self.layout_lock_view(container)
        elif self.saved_content is not None:
            self.lock_password.value = self.lock_confirmation.value = ''
            self.lock_status.text = ''
            self.restore_lock_layout()
            self.app.main_window.content = self.saved_content
            self.saved_content = None
            self.lock_gates = ()
            if self.backend.startswith('toga_android.'):
                self.app.adaptive.render()
            self.resume_reader()

    def fit_lock_view(self, width=None, height=None):
        if self.disposed:
            return
        if self.lock_view is None:
            return
        from .settings.forms import fit_section
        if height is None and self.backend.startswith('toga_android.'):
            viewport = self.android_lock_viewport()
            if viewport is not None:
                width, height = viewport
        # Explicit wrapping prevents long credential labels from imposing a
        # wider content minimum than the native viewport can display.
        width = self.app.main_window.size.width if width is None else width
        card_width = max(24, min(560, width - 40))
        if self.lock_card.style.width != card_width:
            self.lock_card.style.width = card_width
        if height is None:
            height = self.lock_view.layout.height or self.app.main_window.size.height
        # Keep a 48-point scrolling control viewport even on short landscape
        # keyboards, reducing only vertical outer padding when necessary.
        margin = max(12, min(20, (height - 72) / 2))
        if self.lock_body.style.margin_top != margin:
            self.lock_body.style.margin_top = self.lock_body.style.margin_bottom = margin
        card_height = max(72, min(520, height - 2 * margin))
        if self.lock_card.style.height != card_height:
            self.lock_card.style.height = card_height
        from toga.style.pack import COLUMN, ROW, CENTER
        wide = card_width >= 500
        direction = ROW if wide else COLUMN
        if self.lock_layout.style.direction != direction:
            self.lock_layout.remove(self.lock_icon)
            self.lock_layout.insert(1 if wide else 0, self.lock_icon)
            self.lock_layout.style.direction = direction
            self.lock_icon.style.margin_left = 20 if wide else 0
            self.lock_icon.style.margin_bottom = 0 if wide else 12
            self.lock_icon.style.font_size = 64 if wide else 40
            if wide:
                self.lock_layout.style.align_items = CENTER
                self.lock_icon.style.width = 88
            else:
                del self.lock_layout.style.align_items
                del self.lock_icon.style.width
        fit_section(self.lock_fields, max(24, card_width - 48 - (108 if wide else 0)))

    def android_lock_viewport(self):
        # A fixed card is also the toolkit root's minimum height. Measure the
        # native visible frame independently so that minimum cannot hide IME
        # overlap or prevent the next resize from shrinking the card.
        from android.graphics import Rect
        from java import jarray, jint
        native = self.lock_view._impl.native
        visible, position = Rect(), jarray(jint)(2)
        native.getWindowVisibleDisplayFrame(visible)
        native.getLocationOnScreen(position)
        width = min(native.getWidth(), visible.right - max(visible.left, position[0]))
        height = visible.bottom - max(visible.top, position[1])
        if width > 0 and height > 0:
            density = float(native.getResources().getDisplayMetrics().density)
            return width / density, height / density
        return None

    def install_android_lock_layout(self):
        if self.android_lock_layout is not None:
            return
        import weakref
        from java import dynamic_proxy, jclass
        reference = weakref.ref(self)
        class Layout(dynamic_proxy(jclass('android.view.ViewTreeObserver$OnGlobalLayoutListener'))):
            def onGlobalLayout(listener):
                owner = reference()
                if (owner is not None and not owner.disposed
                        and owner.app.main_window.content is owner.lock_view):
                    owner.fit_lock_view()
        decor = self.app._impl.native.getWindow().getDecorView()
        listener = Layout()
        self.android_lock_layout = decor, listener
        decor.getViewTreeObserver().addOnGlobalLayoutListener(listener)
        self.fit_lock_view()

    def layout_lock_view(self, container):
        # The normal root hosts native navigation controllers, whose leaf
        # containers handle safe areas. The lock form replaces that entire
        # hierarchy, so its root must now reserve the system insets itself.
        insets = container.native.safeAreaInsets
        container.top_inset, container.bottom_inset = insets.top, insets.bottom
        container.left_inset, container.right_inset = insets.left, insets.right
        size = container.native.bounds.size
        self.fit_lock_view(self.app.main_window.size.width - insets.left - insets.right,
                           size.height - insets.top - insets.bottom)
        self.app.main_window._impl.notify_resize(container)
        if container.content is not None:
            container.content.interface.refresh()

    def restore_lock_layout(self):
        if self.android_lock_layout is not None:
            decor, listener = self.android_lock_layout
            observer = decor.getViewTreeObserver()
            if observer.isAlive():
                observer.removeOnGlobalLayoutListener(listener)
            self.android_lock_layout = None
        if self.saved_lock_layout is not None:
            container = self.app.main_window._impl.container
            container.on_native_layout = self.saved_lock_layout
            self.saved_lock_layout = None
            container.on_native_layout(container)

    async def unlock(self, widget=None, **kwargs):
        import asyncio
        if self.unlock_busy or self.inactive or getattr(self, 'interrupted', False):
            return
        lifecycle_revision = getattr(self, 'wifi_revision', 0)
        snapshot = self.gates()
        gates = tuple(gate for gate in snapshot if gate.locked)
        revisions = tuple(gate.revision for gate in gates)
        secret, confirmation = self.lock_password.value, self.lock_confirmation.value
        self.lock_password.value = self.lock_confirmation.value = ''
        setup = any(gate.proof is None for gate in gates)
        if not secret or (setup and secret != confirmation):
            self.lock_status.text = 'Enter matching, nonempty passwords.' if setup else 'Enter the session password.'
            return
        self.unlock_busy = True
        self.lock_button.enabled = False
        try:
            # Each remaining credential/view gate must be authenticated. Multiple
            # different passwords are entered in successive attempts.
            accepted = []
            for gate in gates:
                if gate.proof is None:
                    accepted.append(await asyncio.to_thread(gate.configure, secret))
                else:
                    accepted.append(await asyncio.to_thread(gate.verify, secret))
            if (self.disposed or self.inactive or getattr(self, 'interrupted', False)
                    or getattr(self, 'wifi_revision', 0) != lifecycle_revision or self.gates() != snapshot
                    or tuple(gate.revision for gate in gates) != revisions):
                if not self.disposed:
                    self.refresh()
                return
            for gate, valid, revision in zip(gates, accepted, revisions):
                if valid:
                    gate.authorize(revision)
            if any(gate.locked for gate in gates):
                self.lock_status.text = ('Enter the password for the remaining private session.' if any(accepted)
                                         else 'Incorrect password. Session remains locked.')
            else:
                self.lock_status.text = ''
            self.refresh()
            self.refresh_other_windows()
        finally:
            secret = confirmation = None
            self.unlock_busy = False
            self.lock_button.enabled = True

    def dispose(self):
        self.disposed = True
        failure = None

        def attempt(cleanup, *args):
            nonlocal failure
            try:
                cleanup(*args)
            except Exception as error:
                failure = failure or error
                return False
            return True

        subscription = self.lock_layout_subscription
        if subscription is not None and attempt(subscription.dispose):
            self.lock_layout_subscription = None
        scope = self.protection_scope
        if scope is not None:
            scope.process.listeners.discard(self)
            if attempt(scope.dispose):
                self.protection_scope = None
        attempt(self.restore_lock_layout)
        if self.credential_observers is not None:
            self.credential_observers.discard(self)
            self.credential_observers = None
        if self.activity_listener is not None:
            if attempt(lambda: self.application.unregisterActivityLifecycleCallbacks(self.activity_listener)):
                self.activity_listener = self.application = None
        if self.trait_registration is not None:
            if attempt(lambda: self.trait_window.unregisterForTraitChanges(self.trait_registration)):
                self.trait_registration = None
        if self.trait_registration is None:
            self.trait_window = self.trait_block = None
        pending = []
        for token, block in self.observers:
            if not attempt(lambda: self.center.removeObserver(token)):
                pending.append((token, block))
        self.observers = pending
        if self.shield is not None and attempt(self.shield.removeFromSuperview):
            self.shield = None
        if failure is not None:
            raise failure
