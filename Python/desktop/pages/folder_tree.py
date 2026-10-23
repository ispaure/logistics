"""
Generic folder sources, selection, and feature actions.
"""

from collections import Counter

from commonUtils.ui import pyside

from services.folders.policy import folder_parts
from services.folders.workspaces import local_entries, local_entry_category, remote_entries


LOCAL_SOURCE_NAME = 'Local'


class FolderTreePresentation:
    """Project discovered copies into the selectable desktop folder tree."""
    def __init__(self, page):
        self.page = page

    def refresh(self):
        page = self.page
        if page._closing or page._sources is None:
            return
        entries, entry_labels = self._selected_entries()
        if not self._render_entries(entries, entry_labels):
            return

        selected_item = page._entry_items.get(page._selected_entry_key)

        if selected_item is None:
            page._show_empty_state('Select a folder to browse its files.')
            return

        page.folder_tree.setCurrentItem(selected_item)

    def _selected_entries(self):
        page = self.page
        selected_source = page._get_selected_source()
        source_type = selected_source[0] if selected_source is not None else 'local'
        entry_labels = {}

        if source_type == 'local':
            entries = local_entries(page._sources)
            category = page.credential_combo.currentData()
            if category is not None:
                entries = [entry for entry in entries if local_entry_category(entry, page._sources) == category]
            entry_labels.update((page._entry_key(entry), str(entry.local.path)) for entry in entries)
        else:
            _source_type, _feature_name, sources = selected_source
            selected_credential = page.credential_combo.currentData()
            entries = []
            for source in sources:
                if selected_credential is not None and source.source.context != selected_credential:
                    continue
                source_entries = remote_entries(source, page._local_folders)
                entries.extend(source_entries)
                for entry in source_entries:
                    entry_labels[page._entry_key(entry)] = source.source.name

        if not page.visibility.show_legacy:
            entries = [entry for entry in entries if not entry.name.casefold().startswith('legacy-')]
        entries.sort(key=lambda entry: (entry.name.casefold(), str(entry.remote_context)))
        return entries, entry_labels

    def _render_entries(self, entries, entry_labels):
        page = self.page
        name_counts = Counter(entry.name for entry in entries)
        copy_labels = {page._entry_key(entry): getattr(entry.local, 'storage_label', 'Local')
                       if entry.local is not None else 'Remote' for entry in entries}
        copy_counts = Counter((entry.name, copy_labels[page._entry_key(entry)]) for entry in entries)

        page.folder_tree.clear()
        page._entry_items = {}

        if not entries:
            page.selected_entry_name = None
            page._show_empty_state()
            return False

        tree_items = {}

        for entry in entries:
            name_parts = folder_parts(entry.name)
            parent_item = None
            path_parts = []
            entry_key = page._entry_key(entry)

            for index, name_part in enumerate(name_parts):
                path_parts.append(name_part)
                item_path = tuple(path_parts)
                is_leaf = index == len(name_parts) - 1
                if is_leaf and name_counts[entry.name] > 1:
                    item_path = (*item_path, entry_key)
                    label = copy_labels[entry_key]
                    if copy_counts[entry.name, label] > 1:
                        label += ' · ' + entry_labels[entry_key]
                    name_part = f'{name_part} [{label}]'

                item = tree_items.get(item_path)

                if item is None:
                    item = pyside.QTreeWidgetItem([name_part])
                    tree_items[item_path] = item

                    if parent_item is None:
                        page.folder_tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)

                if index == len(name_parts) - 1:
                    item.setData(0, pyside.Qt.ItemDataRole.UserRole, entry)
                    page._style_folder_item(item, entry)
                    item.setToolTip(0, '\n'.join(filter(None, (entry.name, copy_labels[entry_key],
                        entry_labels.get(entry_key, ''), str(entry.local.path) if entry.local is not None else ''))))
                    page._entry_items[entry_key] = item

                parent_item = item

        for item in tree_items.values():
            if item.data(0, pyside.Qt.ItemDataRole.UserRole) is None:
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                item.setFlags(item.flags() & ~pyside.Qt.ItemFlag.ItemIsSelectable)

        page.folder_tree.expandAll()

        return True
