"""Settings → Help and About, including deferred installed-build information."""
import asyncio
import toga
from toga.style import Pack
from .forms import page, SettingsLabel, page_button
from .information import build_information


def help(app):
    box = page('Help')
    from ..documentation_ui import show_documentation
    box.add(page_button('Mobile documentation', on_press=lambda widget, **kw: show_documentation(app),
                        style=Pack(height=48)))
    box.add(page_button('About', on_press=lambda widget, **kw: show_about(app), style=Pack(height=48)))
    if type(app._impl).__module__.startswith('toga_android.'):
        from .forms import connection_disclosure, settings_presentation, fit_section
        developer = toga.Button('Android Developer Settings…',
            on_press=app.open_android_developer_settings, style=Pack(height=48))
        more, _ = connection_disclosure('More', [developer],
            on_toggle=lambda panel: fit_section(panel, app.settings_navigation.detail_width - 32))
        settings_presentation(developer.parent)
        more._settings_managed_content = True
        box.add(more)
    return box


def show_about(app, widget=None, **kwargs):
    if not app.checkpoint():
        return
    navigation = app.settings_navigation
    navigation.fit_detail('About')
    view = navigation.options['About']
    navigation.detach(view)
    app.show_view(view, checkpoint=False, destination='settings', route='settings-about', title='About')


def about(app):
    box = page('About')
    label = app.build_version_label = SettingsLabel(
        (app.version or 'Development build') + '\nLoading build information…',
        style=Pack(font_size=12, color='#808080'))
    box.add(label)

    async def load_information():
        try:
            text = await asyncio.to_thread(build_information, app.version)
        except Exception:
            # Keep About usable even if an old/malformed payload cannot be read.
            text = (app.version or 'Development build') + '\nBuild information unavailable.'
        label.text = text

    app.build_information_task = app.loop.create_task(load_information())
    from .licenses import show_licenses
    box.add(page_button('Open-source licenses', on_press=lambda widget, **kw: show_licenses(app),
                        style=Pack(height=48)))
    return box
