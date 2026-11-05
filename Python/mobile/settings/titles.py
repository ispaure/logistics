"""Keep Settings page titles in the body only when the route bar lacks them."""

import toga
from toga.style import Pack

from commonUtils.ui.native.forms import FittedLabel
from commonUtils.ui.native.keyboard import native_value


def page_title(text):
    label = FittedLabel(text, style=Pack(font_size=18, font_weight='bold', margin_bottom=6))
    label._settings_page_title = text
    return label


def title_slot(view):
    content = view.content if isinstance(view, toga.ScrollContainer) else view
    slot = getattr(content, '_settings_title_slot', None)
    if slot is None:
        for index, child in enumerate(getattr(content, 'children', ())):
            if getattr(child, '_settings_page_title', None):
                slot = content._settings_title_slot = (index, child)
                break
    return content, slot


def show_body_title(view, visible=True):
    content, slot = title_slot(view)
    if slot is None:
        return
    index, title = slot
    if visible and title.parent is None:
        content.insert(index, title)
    elif not visible and title.parent is content:
        content.remove(title)


def bar_shows_title(navigation, controller, title):
    """Measure the rendered title, since a navigation item can outlive its label."""
    if (navigation.topViewController != controller or navigation.isNavigationBarHidden()
            or str(native_value(controller.navigationItem.title) or '') != title):
        return False

    from rubicon.objc import ObjCClass
    label_class = ObjCClass('UILabel')
    bar = native_value(navigation.navigationBar)
    if native_value(bar.window) is None:
        return False

    size = native_value(bar.bounds).size

    def shows_title(view):
        if view.isHidden() or float(native_value(view.alpha)) <= 0:
            return False
        if view.isKindOfClass(label_class) and str(native_value(view.text) or '') == title:
            rect = view.convertRect(native_value(view.bounds), toView=bar)
            return (rect.size.width > 0 and rect.size.height > 0
                    and rect.origin.x < size.width
                    and rect.origin.x + rect.size.width > 0
                    and rect.origin.y < size.height
                    and rect.origin.y + rect.size.height > 0)
        return any(shows_title(child) for child in native_value(view.subviews))

    return shows_title(bar)


def sync_route_title(view, navigation, controller):
    _, slot = title_slot(view)
    if slot is not None:
        _, title = slot
        show_body_title(view, not bar_shows_title(navigation, controller, title._settings_page_title))
