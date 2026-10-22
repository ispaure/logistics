"""Logistics-owned document launch catalog, shared by all chooser surfaces."""
from features import registry
from features.contributions import DocumentLauncherContribution


def _open_markdown(parent):
    from commonUtils.ui import pyside as qt
    from services.local_storage import install_local_storage_policy
    install_local_storage_policy()
    from services.documents.ui.editors import install_editor_dialogs
    install_editor_dialogs()
    from commonUtils.ui.markdown.window import open_markdown
    from services.documents.ui.editors import choose_editor_resource, open_editor_choice
    choice = choose_editor_resource(parent, 'open', markdown=True)
    if choice is None:
        return None
    if getattr(choice.provider, 'private', False):
        return open_editor_choice(choice, parent, markdown=True)
    path = choice.provider.root / choice.path
    choice.close()
    return open_markdown(path, allow_edit=True)


def _new_markdown(parent):
    from services.local_storage import install_local_storage_policy
    install_local_storage_policy()
    from services.documents.ui.editors import install_editor_dialogs
    install_editor_dialogs()
    from commonUtils.ui.markdown.window import open_markdown
    return open_markdown(None, allow_edit=True)


def document_launchers(registry_provider=registry):
    """Core Markdown plus enabled feature registrations, in declared order."""
    entries = [DocumentLauncherContribution('markdown', 'Markdown Editor', _open_markdown,
               'markdown', 20, _new_markdown, 'Write and preview formatted notes.')]
    entries.extend(entry.contribution for entry in registry_provider.get_document_launchers())
    return {entry.editor_id: entry for entry in sorted(entries, key=lambda entry: entry.order)}


from dataclasses import dataclass


@dataclass(frozen=True)
class Destination:
    key: str
    title: str
    detail: str
    icon: str
    page: object = None
    rail_key: str = ''

    @property
    def card(self):
        return self.key, self.title, self.detail, self.icon


@dataclass(frozen=True)
class LaunchSnapshot:
    destinations: tuple
    documents: dict

    @property
    def targets(self):
        return {entry.key: entry.page for entry in self.destinations if entry.page is not None}

    @property
    def by_page(self):
        return {entry.page: entry for entry in self.destinations if entry.page is not None}


def launch_key(feature, page_id):
    # Retain established persisted/consumer command IDs.
    return {'git.workspace': 'git', 'ide.workspace': 'ide'}.get(page_id, 'feature:' + feature + ':' + page_id)


def launch_document(launchers, key, parent, *, new=False):
    launcher = launchers.get(key)
    if launcher is None:
        return None
    callback = launcher.new_document if new else launcher.open_document
    return callback(parent) if callback is not None else None


class LaunchCatalog:
    """One registry projection for launch targets, cards, rail identity and commands."""
    CORE = (
        ('browser', 'File Browser', 'Browse and organize files.', 'browser', 'browser'),
        ('folders', 'Workspaces', 'Browse configured folders and services.', 'hub', 'hub'),
        ('bulk_rename', 'Bulk Rename', 'Preview and rename files and folders.', 'rename', 'rename'),
        ('actions', 'Workspace actions', 'Continue running operations and review their results.', 'actions', 'actions'),
    )

    def __init__(self, *, core_types, registry_provider=registry):
        self.core_types, self.registry = core_types, registry_provider

    def snapshot(self, core_pages, feature_pages, *, is_present, actions=None, bulk_rename=None):
        pages = {}
        for _, _, page in core_pages:
            for key, kind in self.core_types.items():
                if isinstance(page, kind):
                    pages[key] = page
                    break
        pages.update(bulk_rename=bulk_rename)
        if actions is not None and actions.count:
            pages['actions'] = actions
        entries = [Destination(key, title, detail, icon, pages.get(key), rail)
                   for key, title, detail, icon, rail in self.CORE
                   if key == 'bulk_rename' or pages.get(key) is not None]
        states = {state.name: state for state in self.registry.get_feature_states()}
        for registered in self.registry.get_pages():
            item = registered.contribution
            page = feature_pages.get((registered.feature_name, item.page_id))
            if item.navigation_icon and page is not None and is_present(page):
                state = states.get(registered.feature_name)
                key = launch_key(registered.feature_name, item.page_id)
                detail = item.launch_description or getattr(state, 'description', '') or f'Open {item.name}.'
                entries.append(Destination(key, item.name, detail, item.navigation_icon, page, key))
        return LaunchSnapshot(tuple(entries), document_launchers(self.registry))
