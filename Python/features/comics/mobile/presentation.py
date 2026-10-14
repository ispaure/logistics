"""Comic page presentation over an injected native canvas factory."""
import toga
from toga.style import Pack
from .validation import image_dimensions


def page_view(data, *, canvas, on_page, on_toggle):
    image_dimensions(data)
    return canvas(image=toga.Image(src=data), on_page=on_page,
                  on_toggle=on_toggle, description='Comic page. Pinch to zoom; swipe at fit size to change pages.',
                  style=Pack(flex=1))
