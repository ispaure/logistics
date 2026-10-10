"""Two synchronized native rich-text pages sharing one paginated document."""
from commonUtils.ui import pyside as qt
from .text_view import BookText


class BookSpread(qt.QObject):
    def __init__(self, page, layout):
        super().__init__(page)
        self.page = page
        self.second = BookText(page.reading_area)
        self.second.spread_owner = page.text
        self.second.setDocument(page.text.document())
        self.second.pageTurn.connect(page.turn_page)
        self.second.anchorClicked.connect(page._link_clicked)
        self.second.hide()
        layout.addWidget(self.second, 1)
        page.text.companion = self.second
        page.reading_area.installEventFilter(self)
        self.enabled = False

    def eventFilter(self, watched, event):
        if event.type() == qt.QEvent.Type.Resize:
            self.update()
        return False

    def update(self):
        page = self.page
        enabled = page.book is not None and page.reading_area.width() >= 1020
        self.enabled = enabled
        self.second.book = page.book
        self.second.navigation_enabled = page.text.navigation_enabled
        self.second.setMaximumWidth(page.reading_width.value())
        if self.second.font() != page.text.font():
            self.second.setFont(page.text.font())
        if self.second.styleSheet() != page.text.styleSheet():
            self.second.setStyleSheet(page.text.styleSheet())
            page.text.layout_settle.start(0)
        self.second.setVisible(enabled)
        if enabled:
            self.second._page = page.text.page_index + 1
            self.second._page_range_changed()

    @property
    def step(self):
        return 2 if self.enabled else 1
