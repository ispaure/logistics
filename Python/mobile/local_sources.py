"""Ordinary mobile browse roots, excluding private control and encrypted storage."""
from commonUtils.runtime.resources.local import LocalFiles
from features.rclone.mobile.storage_location import shared_documents_path


class SharedFiles(LocalFiles):
    def _guard(self, path):
        relative = path.relative_to(self.root)
        if relative.parts in (('Local',), ('Received Files',)):
            raise ValueError('This folder is managed by Logistics. Open it to manage its contents.')
        return super()._guard(path)

    def list(self, path='', *, cancelled=lambda: False):
        path = self.relative(path)
        if path in ('Local', 'Received Files'):
            # Recursive search reads the collection too. Mutations still go
            # through entry/_guard, which protects the collection root.
            return LocalFiles(self.root).list(path, cancelled=cancelled)
        if path:
            return super().list(path, cancelled=cancelled)
        rows = []
        from commonUtils.runtime.operations import check_cancelled
        for child in self.root.iterdir():
            check_cancelled(cancelled)
            if child.name in ('Local', 'Received Files'):
                # Expose the collection as a folder, but keep root mutations
                # protected; normal navigation switches to CollectionFiles.
                row = LocalFiles(self.root).entry(child.name)
                rows.append(row)
            else:
                rows.append(self.entry(child.name))
        return sorted(rows, key=lambda row: (not row['directory'], row['name'].casefold()))


def shared_files(private_root):
    root = shared_documents_path(private_root)
    return SharedFiles(root) if root is not None else None


class DeviceFiles(LocalFiles):
    """Android browse root admits only the two ordinary collection directories.

    Private settings, credentials and raw LocalCrypt storage must never become
    visible through this provider, including direct paths and recursive search.
    """
    def __init__(self, private_root):
        from features.rclone.mobile.storage_location import collection_base, collection_path
        from .incoming_files import inbox_path
        self.private_root = private_root
        received = inbox_path(private_root)
        local = collection_path(private_root)
        local.mkdir(parents=True, exist_ok=True)
        self.folders = (local.name, received.name)
        super().__init__(collection_base(private_root))

    def _guard(self, path):
        from features.rclone.mobile.storage_location import collection_base
        if collection_base(self.private_root) != self.root:
            raise ValueError('Collection location changed. Restart Logistics.')
        parts = path.relative_to(self.root).parts
        if parts and parts[0] not in self.folders:
            raise ValueError('This location is private app storage.')
        return super()._guard(path)

    def list(self, path='', *, cancelled=lambda: False):
        from commonUtils.runtime.operations import check_cancelled
        if self.relative(path):
            return super().list(path, cancelled=cancelled)
        rows = []
        for folder in self.folders:
            check_cancelled(cancelled)
            row = self.entry(folder)
            if folder == 'LocalFiles':
                row = dict(row, name='Local')
            rows.append(row)
        return rows

    def _protect_root(self, path):
        if self.relative(path) in ('', *self.folders):
            raise ValueError('This folder is managed by Logistics. Open it to manage its contents.')

    def rename(self, source, destination):
        self._protect_root(source)
        self._protect_root(destination)
        return super().rename(source, destination)

    def remove_empty(self, path, revision):
        self._protect_root(path)
        return super().remove_empty(path, revision)


def device_files(private_root):
    return shared_files(private_root) or DeviceFiles(private_root)
