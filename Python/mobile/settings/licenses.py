"""Read-only, offline component notices reached from Settings → About."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from services.open_source import installed_notices
from .forms import SettingsLabel, page_button, fit_section, settings_presentation


def show_licenses(app, widget=None, **kwargs):
    notices = installed_notices()
    rows = toga.Box(style=Pack(direction=COLUMN))

    def show_notice(notice):
        text = toga.MultilineTextInput(value=notice.content, readonly=True, style=Pack(flex=1))
        app.show_view(toga.Box(children=[text], style=Pack(direction=COLUMN, flex=1)),
                      destination='settings', route='open-source-notice', title=notice.title)

    def filter_notices(widget=None, **kwargs):
        query = (search.value or '').casefold()
        rows.clear()
        for notice in notices:
            if query in (notice.title + ' ' + notice.license).casefold():
                rows.add(page_button(notice.title, on_press=lambda widget, notice=notice, **kw: show_notice(notice),
                                     style=Pack(height=48)))
        if not rows.children:
            rows.add(SettingsLabel('No matching components.'))
        settings_presentation(rows)
        fit_section(rows, app.adaptive.content_width('settings'))

    search = toga.TextInput(placeholder='Search components', on_change=filter_notices)
    body = toga.Box(children=[SettingsLabel('Open-source licenses', style=Pack(font_size=22)),
        SettingsLabel('Licenses and notices for this app and its installed components. Available offline.'),
        search, rows], style=Pack(direction=COLUMN, margin=12))
    filter_notices()
    view = toga.ScrollContainer(content=body, horizontal=False, style=Pack(flex=1))
    app.show_view(view, destination='settings', route='open-source-licenses', title='Open-source licenses')
    return view
