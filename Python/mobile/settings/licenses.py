"""Read-only, offline component notices reached from Settings → About."""
from commonUtils.ui.native.event_loop import DebouncedCallback
import toga
import json
from toga.platform import get_current_platform
from toga.style import Pack
from toga.style.pack import COLUMN

from services.open_source import installed_notices, Notice
from .forms import SettingsLabel, page_button, fit_section, settings_presentation


def show_licenses(app, widget=None, **kwargs):
    inventory = None
    unavailable = None
    if get_current_platform() == 'android':
        try:
            from java import jclass
            scanner = jclass('java.util.Scanner')(
                app._impl.native.getAssets().open('logistics-open-source.json'), 'UTF-8').useDelimiter('\\A')
            try:
                inventory = json.loads(str(scanner.next()))
                if inventory.get('schema') != 1 or inventory.get('platform') != 'android':
                    raise ValueError('Unsupported native notice inventory')
            finally:
                scanner.close()
        except Exception:
            inventory = None
            unavailable = Notice('Android dependency inventory unavailable', '', '', '',
                'This build does not include its resolved native dependency notice inventory.')
    notices = installed_notices(native_inventory=inventory)
    if unavailable is not None:
        notices.insert(0, unavailable)
    rows = toga.Box(style=Pack(direction=COLUMN))

    def show_notice(notice):
        text = toga.MultilineTextInput(value=notice.content, readonly=True, style=Pack(flex=1))
        app.show_view(toga.Box(children=[text], style=Pack(direction=COLUMN, flex=1)),
                      destination='settings', route='open-source-notice', title=notice.title)

    def filter_notices(widget=None, **kwargs):
        query = (search.value or '').casefold()
        rows.clear()
        for notice in notices:
            if query in notice.content.casefold():
                rows.add(page_button(notice.title, on_press=lambda widget, notice=notice, **kw: show_notice(notice),
                                     style=Pack(height=48)))
        if not rows.children:
            rows.add(SettingsLabel('No matching components.'))
        settings_presentation(rows)
        fit_section(rows, app.adaptive.content_width('settings'))

    search = toga.TextInput(placeholder='Search components', on_change=DebouncedCallback(filter_notices))
    body = toga.Box(children=[SettingsLabel('Open-source licenses', style=Pack(font_size=22)),
        SettingsLabel('Licenses and notices for this app and its installed components. Available offline.'),
        search, rows], style=Pack(direction=COLUMN, margin=12))
    filter_notices()
    view = toga.ScrollContainer(content=body, horizontal=False, style=Pack(flex=1))
    app.show_view(view, destination='settings', route='open-source-licenses', title='Open-source licenses')
    return view
