"""Comic page presentation over an injected native canvas factory."""
import toga
from toga.style import Pack
from toga.style.pack import NONE
from .validation import image_dimensions


def page_view(data, *, canvas, on_page, on_toggle, width=None):
    image_dimensions(data)
    view = canvas(image=toga.Image(src=data), on_page=on_page,
                  on_toggle=on_toggle, description='Comic page. Pinch to zoom; swipe at fit size to change pages.',
                  style=Pack(flex=1, width=width if width is not None else NONE))
    view.page_swipes_at_edges = True
    return view


class SpreadView(toga.Box):
    """A complete spread on one native canvas, including its shared gutter."""
    def __init__(self, data, *, canvas, on_page, on_toggle, right_to_left=False, width=None, viewport=None, seam=None):
        from .composite import compose_spread
        self._on_page = on_page
        image = compose_spread(data, right_to_left=right_to_left, viewport=viewport or ((width, None) if width else None), seam=seam)
        self.canvas = canvas(image=image, on_page=self.turn, on_toggle=on_toggle,
            description='Comic spread. Pinch to zoom both pages; drag across the spread. Swipe at fit size to turn.',
            style=Pack(flex=1))
        self.canvas.page_swipes_at_edges = True
        self.canvases = [self.canvas]
        super().__init__(children=[self.canvas], style=Pack(flex=1, width=width if width is not None else NONE))

    @property
    def magnifier_enabled(self):
        return self.canvas.magnifier_enabled

    @magnifier_enabled.setter
    def magnifier_enabled(self, enabled):
        self.canvas.magnifier_enabled = enabled

    @property
    def zoom_scale(self):
        return self.canvas.zoom_scale

    def turn(self, direction):
        if self.zoom_scale <= 1.05:
            self._on_page(direction)

    def fit_page(self):
        self.canvas.fit_page()

    def dispose(self):
        self._on_page = lambda *args: None
        self.canvas.dispose()


async def watch_layout(*, alive, available, viewport, view, reload):
    """Refresh a fitted spread after a viewport change; hosts own task lifetime."""
    import asyncio
    previous = viewport()
    while alive():
        await asyncio.sleep(.3)
        if not alive():
            return
        current = viewport()
        if current != previous and available():
            spread = view()
            canvases = getattr(spread, 'canvases', [spread])
            if any(getattr(canvas, 'zoom_scale', 1) > 1.05 for canvas in canvases):
                continue
            previous = current
            await reload()
