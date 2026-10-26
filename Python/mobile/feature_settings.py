"""Device feature switches and safe updates across mobile windows."""
import json

from services.mobile_features import FEATURES, BY_NAME, enabled, group_enabled, disabled_features, document_feature, selection_preferences


def hosts(app):
    owners = getattr(getattr(app, 'scene_manager', None), 'owners', None)
    return tuple(owners.hosts.values()) if owners is not None else (app,)


def set_enabled(app, name, value, *, refresh=True):
    if name not in BY_NAME or type(value) is not bool:
        raise ValueError('Choose a mobile feature and an on/off value.')
    members = BY_NAME[name].names
    if not value:
        for host in hosts(app):
            for session in host.workspace.sessions.values():
                feature = document_feature(session.title, session.kind)
                from .document_sources import session_source
                source = session_source(host, session) if name == 'rclone' else None
                if feature in members or (source is not None and source.get('type') != 'local'):
                    raise ValueError(f'Close the open {BY_NAME[name].label} documents before turning this feature off. Your files and settings will be kept.')
            chat = host.__dict__.get('_chat_controller')
            if name == 'lm' and chat is not None and (chat.state.busy or chat.state.generating):
                raise ValueError('Wait for the chat request to finish before turning LM Chat off.')
            if name == 'rclone' and (getattr(host, 'cloud_busy', False) or getattr(host, 'transfer_busy', False)):
                raise ValueError('Wait for the storage operation to finish before turning rclone off.')
    preferences = selection_preferences(app.preferences)
    names = disabled_features(preferences.values['disabled_features'])
    names.difference_update(members) if value else names.update(members)
    preferences.save(disabled_features=json.dumps(sorted(names)))
    for host in hosts(app):
        if host.preferences is not preferences:
            host.preferences.feature_preferences = preferences
        if refresh:
            host.loop.call_soon(refresh_features, host)
    return True


def refresh_features(app):
    if not app.active_host:
        return
    # Keep retained readers and their drafts. Hubs are rebuilt on next entry.
    app.__dict__.pop('_home_content_state', None)
    retired = set()
    if not enabled(app.preferences, 'rclone'):
        retired.update(('remote-browser', 'remote-actions', 'remote-item', 'connections',
            'import-credentials', 'smb-connection', 'choose-credential', 'credential-package',
            'unlock-credential', 'transfers', 'transfer-copy', 'transfer-settings', 'transfer-review', 'local-push'))
    if not enabled(app.preferences, 'lm'):
        retired.add('chat-settings')
    if not enabled(app.preferences, 'books') and not enabled(app.preferences, 'comics'):
        retired.add('library')
    for destination, screens in app.routes.screens.items():
        index = next((index for index, screen in enumerate(screens) if screen[0] in retired), None)
        if index is not None:
            app.routes.trim(destination, index)
    folder = app.__dict__.get('_folder_controller')
    if folder is not None:
        folder.folder_picker_view = None
        if not enabled(app.preferences, 'rclone'):
            folder.folder_source = 'Local'
        folder.invalidate_folder_discovery()
    chat = app.__dict__.get('_chat_controller')
    readers = app.__dict__.get('readers')
    if readers is not None:
        readers.catalog.refresh_library()
    if not enabled(app.preferences, 'lm') and hasattr(app, 'routes'):
        root = app.routes.roots['chat']
        for child in list(root.children):
            root.remove(child)
        root.add(disabled_view(app, 'lm', destination='chat'))
        app.routes.trim('chat', 0)
    elif chat is not None and hasattr(app, 'routes'):
        # Chat lazily remounts its retained conversation on the next tab entry.
        app.routes.trim('chat', 0)
    if enabled(app.preferences, 'lm') and app.native_host.state.destination == 'chat':
        app.show_chat(present=False)
    navigation = getattr(app, 'settings_navigation', None)
    selected = navigation.selected if navigation is not None else None
    app.show_settings(present=False, rebuild=True)
    if selected not in app.settings_navigation.sections:
        app.routes.trim('settings', 0)
    if app.native_host.state.destination == 'settings':
        app.show_settings()
        if selected in app.settings_navigation.sections:
            app.settings_navigation.choose(selected)
    else:
        app.refresh_hub(app.native_host.state.destination)


def disabled_view(app, name, *, destination=None):
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN
    feature = BY_NAME[name]
    from .settings.forms import SettingsLabel, fit_section
    status = SettingsLabel('', style=Pack(margin_top=12))
    def enable(widget=None, **kwargs):
        try:
            set_enabled(app, name, True)
        except (OSError, ValueError) as error:
            status.text = str(error)
            return
        app.routes.back()
        if destination == 'chat':
            app.loop.call_soon(app.show_chat)
    view = toga.Box(style=Pack(direction=COLUMN, margin=16), children=[
        toga.Label(feature.label + ' is turned off', style=Pack(font_size=20, margin_bottom=12)),
        SettingsLabel('Enable it here or in Settings → Features. Your files and settings are kept.'),
        toga.Button('Enable ' + feature.label, on_press=enable, style=Pack(height=48, margin_top=12)), status])
    fit_section(view, app.adaptive.content_width(destination or app.native_host.state.destination, margin=0))
    return view


def require(app, name, *, destination=None, present=True):
    if enabled(app.preferences, name):
        return True
    view = disabled_view(app, name, destination=destination)
    if present:
        app.show_view(view, destination=destination, route='feature-disabled:' + name, title=BY_NAME[name].label)
    elif destination is not None:
        root = app.routes.roots[destination]
        for child in list(root.children):
            root.remove(child)
        root.add(view)
    return False


def feature_controls(app, box):
    import toga
    from toga.style import Pack
    from .settings.forms import switch_row, SettingsLabel
    box.add(SettingsLabel('Choose the features available on this device. All features are on by default. Changes save automatically; files and settings are kept.'))
    switches = box.feature_switches = {}
    def change(widget, name):
        try:
            set_enabled(app, name, bool(widget.value))
        except (OSError, ValueError) as error:
            widget.on_change = None
            widget.value = group_enabled(app.preferences, name)
            widget.on_change = lambda widget, name=name, **kw: change(widget, name)
            app.settings_status.text = str(error)
    for feature in FEATURES:
        control = toga.Switch(feature.label, value=group_enabled(app.preferences, feature.name), style=Pack(height=48))
        control.on_change = lambda widget, name=feature.name, **kw: change(widget, name)
        switches[feature.name] = control
        box.add(switch_row(app, feature.label, control, feature.description))
    def reset(widget=None, **kwargs):
        try:
            preferences = selection_preferences(app.preferences)
            preferences.save(disabled_features='[]')
        except (OSError, ValueError) as error:
            app.settings_status.text = str(error)
            return
        for host in hosts(app):
            if host.preferences is not preferences:
                host.preferences.feature_preferences = preferences
            host.loop.call_soon(refresh_features, host)
    box.add(toga.Button('Enable all features', on_press=reset, style=Pack(height=48)))
