"""Foreground idle-sleep leases; they do not grant background execution time."""


class AwakeLease:
    def __init__(self, app):
        self.app, self.native, self.closed = app, None, False
        backend = type(app._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            self.native = ObjCClass('LGScreenAwakeLease').alloc().init()
        elif backend.startswith('toga_android.'):
            # View flags compose with the separate native video player's flag.
            view = app._impl.native.getWindow().getDecorView()
            state = getattr(app, '_transfer_awake_state', None)
            if state is None:
                state = app._transfer_awake_state = [view, bool(view.getKeepScreenOn()), 0]
            state[2] += 1
            state[0].setKeepScreenOn(True)
            self.native = state

    def close(self):
        if self.closed:
            return
        self.closed = True
        native, self.native = self.native, None
        if isinstance(native, list):
            native[2] -= 1
            if native[2] == 0:
                native[0].setKeepScreenOn(native[1])
                self.app._transfer_awake_state = None
        elif native is not None:
            native.finish()
        self.app = None
