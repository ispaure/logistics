"""Use guarded native subclasses at the Toga widget construction boundary."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"


def install(blocked):
    from threading import Lock
    from java import jclass
    from toga_android.widgets import textinput, webview

    textinput.EditText = jclass('io.github.ispaure.logisticsmobile.SessionClipboard$Text')
    webview.A_WebView = jclass('io.github.ispaure.logisticsmobile.SessionClipboard$Web')
    policy = jclass('io.github.ispaure.logisticsmobile.SessionClipboard')
    publication = Lock()

    def publish():
        with publication:
            policy.setBlocked(blocked())

    return publish


def copy_text(text):
    import toga
    from android.content import ClipData, Context
    activity = toga.App.app._impl.native
    activity.getSystemService(Context.CLIPBOARD_SERVICE).setPrimaryClip(ClipData.newPlainText('Logistics', text))
