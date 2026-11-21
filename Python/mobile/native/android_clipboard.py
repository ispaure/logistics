"""Use guarded native subclasses at the Toga widget construction boundary."""


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
