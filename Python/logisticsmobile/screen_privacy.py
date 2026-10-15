"""Native snapshot shielding and supported screen-capture protection.

iOS public APIs cannot prevent still screenshots. Never claim otherwise or
reparent UIKit views into undocumented secure-text-field internals.
"""


def native_value(owner, name):
    """Rubicon exposes custom Objective-C getters as bound methods."""
    value = getattr(owner, name)
    return value() if callable(value) else value


class ScreenPrivacy:
    def __init__(self, app):
        self.app = app
        self.disposed = False
        self.inactive = False
        self.observers = []
        self.blocks = []
        self.shield = None
        self.lock_view = None
        self.saved_content = None
        self.saved_lock_layout = None
        self.lock_gates = ()
        self.unlock_busy = False
        self.activity_listener = self.application = None
        self.trait_registration = self.trait_block = None
        self.backend = type(app._impl).__module__
        from features.rclone.mobile.cloud import CloudClient
        CloudClient._credential_observers.add(self)
        if self.backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, Block, objc_id
            self.center = ObjCClass('NSNotificationCenter').defaultCenter
            for name, callback in (
                ('UIApplicationWillResignActiveNotification', self.conceal),
                ('UIApplicationDidBecomeActiveNotification', self.reveal),
                ('UIScreenCapturedDidChangeNotification', self.refresh),
            ):
                block = Block(lambda notification, callback=callback: callback(), None, objc_id)
                self.blocks.append(block)
                self.observers.append(self.center.addObserverForName(name, object=None, queue=None, usingBlock=block))
            window = app.main_window._impl.native
            if window.respondsToSelector('registerForTraitChanges:withHandler:'):
                self.trait_block = Block(lambda view, previous: self.refresh(), None, objc_id, objc_id)
                self.trait_registration = window.registerForTraitChanges(
                    [ObjCClass('UITraitSceneCaptureState')], withHandler=self.trait_block)
        elif self.backend.startswith('toga_android.'):
            self.install_android_lifecycle()
        self.refresh()

    def install_android_lifecycle(self):
        from android.app import Application
        from java import dynamic_proxy
        privacy = self

        class Listener(dynamic_proxy(Application.ActivityLifecycleCallbacks)):
            def onActivityPaused(self, activity):
                if activity == privacy.app._impl.native:
                    privacy.conceal()

            def onActivityResumed(self, activity):
                if activity == privacy.app._impl.native:
                    privacy.reveal()

            def onActivityConfigurationChanged(self, activity):
                # Chaquopy proxies dispatch this Android default method to
                # Python too, including uiMode changes without recreation.
                if activity == privacy.app._impl.native:
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

        self.activity_listener = Listener()
        self.application = self.app._impl.native.getApplication()
        self.application.registerActivityLifecycleCallbacks(self.activity_listener)

    def credentials_changed(self):
        if not self.disposed and not self.app.loop.is_closed():
            self.app.loop.call_soon_threadsafe(self.retire_stale)

    def retire_stale(self):
        if self.disposed or not self.app.active_host:
            return
        self.app.retire_private_comic_batch(stale_only=True)
        private = getattr(self.app, 'private_sessions', None)
        if private is not None:
            private.revoke_stale()
        if hasattr(self.app, 'cloud_view'):
            self.app.clear_private_catalog()
            self.app.cloud_rows = {}
            self.app.cloud_entries.items = []
            self.app.cloud_open_remote = None
            self.app.cloud_location.value = self.app.cloud_path = ''
        self.refresh()

    def gates(self):
        from features.rclone.mobile.cloud import CloudClient
        owners = getattr(getattr(self.app, 'private_sessions', None), 'controllers', {})
        client = getattr(self.app, 'cloud_client', None)
        batch = getattr(self.app, 'private_comic_batch', None)
        # Even a scene which has never opened Connections shares the native
        # process credential store and must protect itself immediately.
        candidates = [CloudClient._session_privacy, getattr(client, 'session_privacy', None),
                      getattr(batch, 'privacy_gate', None)]
        if getattr(self.app, 'save_as_data', None) is not None:
            candidates.append(getattr(self.app, 'save_as_privacy_gate', None))
        candidates.extend(CloudClient._package_privacy.values())
        candidates.extend(getattr(owner, 'privacy_gate', None) for owner in owners.values())
        return tuple(dict.fromkeys(gate for gate in candidates if gate is not None))

    def sensitive(self):
        return bool(self.gates())

    def conceal(self):
        self.inactive = True
        if self.lock_view is not None:
            self.lock_password.value = self.lock_confirmation.value = ''
        for gate in self.gates():
            gate.lock()
        # Cover synchronously before releasing anything or taking a snapshot.
        self.refresh()
        self.app.retire_private_comic_batch()
        self.refresh()
        self.refresh_other_windows()

    def refresh_other_windows(self):
        from features.rclone.mobile.cloud import CloudClient
        for observer in tuple(CloudClient._credential_observers):
            if observer is not self and not observer.disposed and not observer.app.loop.is_closed():
                observer.app.loop.call_soon_threadsafe(observer.refresh)

    def reveal(self):
        self.inactive = False
        self.refresh()

    def refresh(self):
        gates = self.gates()
        # A credential import can finish while the application is inactive.
        if self.inactive:
            for gate in gates:
                if not gate.locked:
                    gate.lock()
        elif self.saved_content is not None:
            # A late import/read must not replace the locked session with a
            # fresh unlocked gate while the resume screen is being displayed.
            for gate in gates:
                if gate not in self.lock_gates and not gate.locked:
                    gate.lock()
        self.sync_lock_view(gates)
        if self.backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            window = self.app.main_window._impl.native
            captured = bool(native_value(window.screen, 'isCaptured'))
            traits = window.traitCollection
            if traits.respondsToSelector('sceneCaptureState'):
                captured = captured or native_value(traits, 'sceneCaptureState') == 1
            scene = window.windowScene
            scene_inactive = scene is not None and native_value(scene, 'activationState') != 0
            # Lifecycle state alone is not private content. In particular, a
            # window can still be inactive while the app is starting up.
            hidden = bool(gates) and (self.inactive or scene_inactive or captured)
            if hidden:
                window.endEditing(True)
                if self.shield is None:
                    self.shield = ObjCClass('UIView').alloc().initWithFrame(window.bounds)
                    self.shield.backgroundColor = native_value(ObjCClass('UIColor'), 'blackColor')
                    self.shield.opaque = True
                    self.shield.autoresizingMask = 18  # flexible width and height
                    self.shield.userInteractionEnabled = True
                    self.shield.accessibilityLabel = 'Private content hidden'
                    self.shield.accessibilityViewIsModal = True
                self.shield.frame = window.bounds
                # UIKit can detach overlays while replacing its root hierarchy.
                # Reattach on every conceal/trait/lifecycle notification.
                window.addSubview(self.shield)
            elif self.shield is not None:
                self.shield.removeFromSuperview()
                self.shield = None
        elif self.backend.startswith('toga_android.'):
            window = self.app._impl.native.getWindow()
            # Android's supported secure-window flag covers screenshots,
            # recording, nonsecure displays and recent-task snapshots.
            if self.sensitive():
                window.addFlags(0x00002000)  # FLAG_SECURE
            else:
                window.clearFlags(0x00002000)

    def sync_lock_view(self, gates):
        """Replace the entire navigation root; routes may update safely behind it."""
        locked = any(gate.locked for gate in gates)
        if locked:
            self.lock_gates = gates
            if self.lock_view is None:
                import toga
                from toga.style import Pack
                from toga.style.pack import COLUMN
                self.lock_title = toga.Label('Session locked', style=Pack(font_size=22))
                self.lock_hint = toga.Label('Enter the session password to resume.')
                self.lock_password = toga.PasswordInput(placeholder='Session password',
                    on_confirm=self.unlock, style=Pack(height=48))
                self.lock_confirmation = toga.PasswordInput(placeholder='Confirm new lock password',
                    style=Pack(height=48))
                self.lock_status = toga.Label('')
                self.lock_button = toga.Button('Unlock', on_press=self.unlock, style=Pack(height=48))
                self.lock_view = toga.Box(children=[self.lock_title, self.lock_hint, self.lock_password,
                    self.lock_button, self.lock_status], style=Pack(direction=COLUMN, flex=1, margin=24))
            setup = any(gate.proof is None for gate in gates)
            self.lock_hint.text = ('Set a temporary lock password for this passwordless session.' if setup
                                   else 'Enter the session password to resume.')
            if setup and self.lock_confirmation not in self.lock_view.children:
                self.lock_view.insert(3, self.lock_confirmation)
            elif not setup and self.lock_confirmation in self.lock_view.children:
                self.lock_view.remove(self.lock_confirmation)
            self.lock_button.text = 'Set lock password' if setup else 'Unlock'
            if self.app.main_window.content is not self.lock_view:
                self.saved_content = self.app.main_window.content
                if self.backend.startswith('toga_iOS.'):
                    container = self.app.main_window._impl.container
                    self.saved_lock_layout = container.on_native_layout
                    container.on_native_layout = self.layout_lock_view
                self.app.main_window.content = self.lock_view
                if self.backend.startswith('toga_iOS.'):
                    self.layout_lock_view(container)
        elif self.saved_content is not None:
            self.lock_password.value = self.lock_confirmation.value = ''
            self.lock_status.text = ''
            self.restore_lock_layout()
            self.app.main_window.content = self.saved_content
            self.saved_content = None
            self.lock_gates = ()

    def layout_lock_view(self, container):
        # The normal root hosts native navigation controllers, whose leaf
        # containers handle safe areas. The lock form replaces that entire
        # hierarchy, so its root must now reserve the system insets itself.
        insets = container.native.safeAreaInsets
        container.top_inset, container.bottom_inset = insets.top, insets.bottom
        container.left_inset, container.right_inset = insets.left, insets.right
        self.app.main_window._impl.notify_resize(container)
        if container.content is not None:
            container.content.interface.refresh()

    def restore_lock_layout(self):
        if self.saved_lock_layout is not None:
            container = self.app.main_window._impl.container
            container.on_native_layout = self.saved_lock_layout
            self.saved_lock_layout = None
            container.on_native_layout(container)

    async def unlock(self, widget=None, **kwargs):
        import asyncio
        if self.unlock_busy or self.inactive:
            return
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
            if (self.disposed or self.inactive or self.gates() != snapshot
                    or tuple(gate.revision for gate in gates) != revisions):
                if not self.disposed:
                    self.refresh()
                return
            for gate, valid in zip(gates, accepted):
                if valid:
                    gate.locked = False
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
        self.restore_lock_layout()
        from features.rclone.mobile.cloud import CloudClient
        CloudClient._credential_observers.discard(self)
        if self.activity_listener is not None:
            self.application.unregisterActivityLifecycleCallbacks(self.activity_listener)
            self.activity_listener = self.application = None
        if self.trait_registration is not None:
            self.app.main_window._impl.native.unregisterForTraitChanges(self.trait_registration)
            self.trait_registration = self.trait_block = None
        for observer in self.observers:
            self.center.removeObserver(observer)
        self.observers.clear()
        self.blocks.clear()
        if self.shield is not None:
            self.shield.removeFromSuperview()
            self.shield = None
