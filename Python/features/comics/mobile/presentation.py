"""Comic page presentation over an injected native canvas factory."""
import toga
from toga.style import Pack
from toga.style.pack import NONE
from features.images.validation import image_dimensions


def page_view(data, *, canvas, on_page, on_toggle, width=None):
    image_dimensions(data)
    view = canvas(image=toga.Image(src=data), on_page=on_page,
                  on_toggle=on_toggle, description='Comic page. Pinch to zoom; swipe at fit size to change pages.',
                  style=Pack(flex=1, width=width if width is not None else NONE))
    view.page_swipes_at_edges = True
    view._external_comic_page = True
    return view


class SpreadView(toga.Box):
    """A complete spread on one native canvas, including its shared gutter."""
    def __init__(self, data, *, canvas, on_page, on_toggle, right_to_left=False, width=None, viewport=None, seam=None, crop=None, seam_gap=0, anchor_right=False):
        from .composite import compose_spread
        self._on_page = on_page
        image = compose_spread(data, right_to_left=right_to_left, viewport=viewport or ((width, None) if width else None), seam=seam, crop=crop, seam_gap=seam_gap, anchor_right=anchor_right)
        self.canvas = canvas(image=image, on_page=self.turn, on_toggle=on_toggle,
            description=('Wide comic page half. Swipe at fit size to continue; pinch to zoom.' if crop is not None else
                         'Comic spread. Pinch to zoom both pages; drag across the spread. Swipe at fit size to turn.'),
            style=Pack(flex=1))
        self.canvas.page_swipes_at_edges = True
        self.canvas._external_comic_page = True
        self.canvases = [self.canvas]
        super().__init__(children=[self.canvas], style=Pack(flex=1, width=width if width is not None else NONE))

    def prepare_replacement(self, data, *, right_to_left=False, viewport=None, seam=None, crop=None, seam_gap=0, anchor_right=False):
        """Decode completely without changing the displayed pixels yet."""
        from .composite import compose_spread
        image = compose_spread(data, right_to_left=right_to_left, viewport=viewport, seam=seam,
                               crop=crop, seam_gap=seam_gap, anchor_right=anchor_right)
        description = ('Wide comic page half. Swipe at fit size to continue; pinch to zoom.' if crop is not None else
                       'Comic spread. Pinch to zoom both pages; drag across the spread. Swipe at fit size to turn.')
        def publish():
            self.canvas.description = description
            self.canvas.image = image
            self.canvas.fit_page()
        return publish

    def replace(self, data, **options):
        self.prepare_replacement(data, **options)()
        return self

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



def place_page(view, region):
    """Constrain a discrete page above a horizontal fold; retain its owner."""
    if region is None:
        del view.style.height
        view.style.flex = 1
    else:
        view.style.height, view.style.flex = max(1, region[3]), 0
    return view


async def watch_layout(*, alive, available, viewport, view, reload, changed, initial=None, force=lambda previous, current: False):
    """Refresh a fitted spread after a viewport change; hosts own task lifetime."""
    previous = viewport() if initial is None else initial
    first = True
    while alive():
        if not first or initial is None:
            await changed()
        first = False
        if not alive():
            return
        current = viewport()
        if current != previous and available():
            spread = view()
            canvases = getattr(spread, 'canvases', [spread])
            if not force(previous, current) and any(getattr(canvas, 'zoom_scale', 1) > 1.05 for canvas in canvases):
                continue
            previous = current
            await reload()
