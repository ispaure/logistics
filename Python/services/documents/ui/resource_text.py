"""Progress for a Qt provider-backed text window."""

from commonUtils.ui.resources.editor import ResourceTextWindow

from .text_position import TextPosition


class ResourceTextReader(ResourceTextWindow):
    def __init__(self, choice, session, choose, open_choice, parent=None):
        super().__init__(choice, session, choose, open_choice, parent)
        self.position = TextPosition(self, {'source': self.editor}, notice=self.status.setText)
        self.bind_position()

    def bind_position(self, *, restore=True):
        self.position.bind(self.choice.provider, self.choice.path, self.session.text.data,
                           kind='desktop-text', restore=restore)

    def _saved(self, session, error):
        closing = self.pending_close
        super()._saved(session, error)
        if not error and not closing:
            self.bind_position(restore=False)

    def closeEvent(self, event):
        self.position.flush()
        ready = self.position.ready
        self.position.ready = False
        super().closeEvent(event)
        if event.isAccepted():
            self.position.retire()
        else:
            self.position.ready = ready
