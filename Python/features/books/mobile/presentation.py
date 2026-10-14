"""Toga EPUB chapter presentation with inert navigation."""
from uuid import uuid4
import toga
from toga.style import Pack


def chapter_view(content, view=None):
    if view is None:
        view = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False, style=Pack(flex=1))
    view.set_content('https://logistics.invalid/' + uuid4().hex + '/', content)
    return view
