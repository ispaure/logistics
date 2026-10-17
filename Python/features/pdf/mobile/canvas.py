"""PDF page gestures and compact navigation controls."""
import toga
from commonUtils.ui.native.image_canvas import ImageCanvas


class PDFCanvas(ImageCanvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, page_axis='vertical',
            description='PDF page. Tap to toggle fullscreen; swipe up for next page, down for previous page. Hold in fullscreen to magnify.',
            **kwargs)


class PDFTools:
    """Compact page jump and text search, leaving the reading area clear."""
    def __init__(self, controls):
        from toga.style import Pack
        from toga.style.pack import COLUMN
        self.panel = toga.Box(children=controls, style=Pack(direction=COLUMN, margin_top=8))
        self.button = toga.Button('Pages & search', on_press=self.toggle, style=Pack(height=44))
        self.widget = toga.Box(children=[self.button], style=Pack(direction=COLUMN))

    def toggle(self, widget=None, **kwargs):
        if self.panel in self.widget.children:
            self.close()
        else:
            self.widget.add(self.panel)
            self.button.text = 'Hide pages & search'

    def close(self):
        if self.panel in self.widget.children:
            self.widget.remove(self.panel)
        self.button.text = 'Pages & search'
