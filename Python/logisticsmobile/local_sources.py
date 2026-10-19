"""iOS local browser root with a visible, separately managed collection."""
from commonUtils.runtime.local_files import LocalFiles
from features.rclone.mobile.storage_location import shared_documents_path


class SharedFiles(LocalFiles):
    def _guard(self, path):
        relative = path.relative_to(self.root)
        if relative.parts == ('Local',):
            raise ValueError('The Collection folder is managed by Logistics. Open it to manage its contents.')
        return super()._guard(path)

    def list(self, path='', *, cancelled=lambda: False):
        path = self.relative(path)
        if path == 'Local':
            # Recursive search reads the collection too. Mutations still go
            # through entry/_guard, which protects the collection root.
            return LocalFiles(self.root).list(path, cancelled=cancelled)
        if path:
            return super().list(path, cancelled=cancelled)
        rows = []
        from commonUtils.runtime.operations import check_cancelled
        for child in self.root.iterdir():
            check_cancelled(cancelled)
            if child.name == 'Local':
                # Expose the collection as a folder, but keep root mutations
                # protected; normal navigation switches to CollectionFiles.
                row = LocalFiles(self.root).entry(child.name)
                row['display_name'] = 'Collection'
                rows.append(row)
            else:
                rows.append(self.entry(child.name))
        return sorted(rows, key=lambda row: (not row['directory'], row['name'].casefold()))


def shared_files(private_root):
    root = shared_documents_path(private_root)
    return SharedFiles(root) if root is not None else None
