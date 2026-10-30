"""Desktop session video concealment and memory-only resume authorization."""

from concurrent.futures import ThreadPoolExecutor
from commonUtils.ui import pyside as qt
from services.documents.video_authorization import resume_authorization


class VideoResumeGuard(qt.QObject):
    verified = qt.Signal(bool, int)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.blocked = False
        self.revision = 0
        self.closed = False
        self.busy = False
        self.password_gate = None
        self.authorization = resume_authorization(window.content.provider)
        self.password_gate = self.authorization.password_gate
        original = window.takeCentralWidget()
        self.stack = qt.QStackedWidget()
        self.stack.addWidget(original)
        panel = qt.QWidget()
        layout = qt.QVBoxLayout(panel)
        self.hint = qt.QLabel("Enter the credential password to resume video.")
        layout.addWidget(self.hint)
        self.secret = qt.QLineEdit()
        self.secret.setEchoMode(qt.QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText("Session password")
        layout.addWidget(self.secret)
        self.confirmation = qt.QLineEdit()
        self.confirmation.setEchoMode(qt.QLineEdit.EchoMode.Password)
        self.confirmation.setPlaceholderText("Confirm new session password")
        self.confirmation.setVisible(self.password_gate is not None)
        layout.addWidget(self.confirmation)
        self.button = qt.QPushButton("Unlock video")
        self.button.clicked.connect(self.unlock)
        self.secret.returnPressed.connect(self.unlock)
        layout.addWidget(self.button)
        self.status = qt.QLabel()
        layout.addWidget(self.status)
        self.stack.addWidget(panel)
        window.setCentralWidget(self.stack)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-resume")
        self.verified.connect(self.finish)
        self.app = qt.QApplication.instance()
        self.app.applicationStateChanged.connect(self.application_state)
        window.destroyed.connect(self.dispose)
        if self.password_gate is not None:
            self.lock()
            self.hint.setText(
                "Set a temporary password to protect this session-only video."
            )
        elif self.app.applicationState() != qt.Qt.ApplicationState.ApplicationActive:
            self.lock()

    def application_state(self, state):
        if state != qt.Qt.ApplicationState.ApplicationActive:
            self.lock()

    def lock(self):
        if self.closed:
            return
        self.revision += 1
        self.secret.clear()
        self.confirmation.clear()
        if self.blocked:
            return
        self.blocked = True
        window = self.window
        for name in ("tools_menu", "chapter_menu"):
            menu = getattr(window, name, None)
            if menu is not None:
                menu.close()
                menu.clear()
        self.title = window.windowTitle()
        window.setWindowTitle("Session video locked")
        window.resume_at = window.player.position() or window.resume_at
        window.audio.setMuted(True)
        window.player.stop()
        window.player.setSource(qt.QUrl())
        window.caption.clear()
        window.transport.suspend()
        self.stack.setCurrentIndex(1)

    def unlock(self):
        if self.closed or self.busy or not self.blocked:
            return
        if self.app.applicationState() != qt.Qt.ApplicationState.ApplicationActive:
            return
        secret = self.secret.text()
        confirmation = self.confirmation.text()
        self.secret.clear()
        self.confirmation.clear()
        setup = self.password_gate is not None and self.password_gate.proof is None
        if not secret or (setup and secret != confirmation):
            self.status.setText(
                "Enter matching, nonempty passwords."
                if setup
                else "Enter your credential password."
            )
            return
        self.busy = True
        self.button.setEnabled(False)
        revision = self.revision

        def verify():
            return self.authorization.verify(secret)

        future = self.pool.submit(verify)

        def completed(result):
            try:
                accepted = result.result()
            except Exception:
                accepted = False
            if not self.closed:
                self.verified.emit(accepted, revision)

        future.add_done_callback(completed)

    def finish(self, accepted, revision):
        self.busy = False
        self.button.setEnabled(True)
        if (
            self.closed
            or revision != self.revision
            or self.app.applicationState() != qt.Qt.ApplicationState.ApplicationActive
        ):
            return
        if not accepted:
            self.status.setText(
                "Incorrect password or changed credential package. Video remains hidden."
            )
            return
        try:
            self.window.content.check_access()
        except (OSError, ValueError, PermissionError):
            self.status.setText(
                "Credentials were locked or revoked. Unlock them and reopen this video."
            )
            return
        self.blocked = False
        self.window.transport.resume()
        self.window.player.setSource(qt.QUrl(self.window.transport.url))
        self.window.audio.setMuted(False)
        self.window.setWindowTitle(self.title)
        self.stack.setCurrentIndex(0)
        self.status.clear()
        self.confirmation.hide()
        self.hint.setText("Enter the session password to resume video.")
        # Reattaching a source restores only controls; explicit Play is required.

    def dispose(self, *_):
        self.closed = True
        self.revision += 1
        self.pool.shutdown(wait=False, cancel_futures=True)
