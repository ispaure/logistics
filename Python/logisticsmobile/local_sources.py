"""Ordinary iOS shared files outside the managed Local collection."""
from commonUtils.runtime.local_files import LocalFiles
from features.rclone.mobile.storage_location import shared_documents_path


class SharedFiles(LocalFiles):
    def _guard(self, path):
        relative = path.relative_to(self.root)
        if relative.parts and relative.parts[0] == 'Local':
            raise ValueError('Open managed Local copies from their Workspaces source.')
        return super()._guard(path)

    def list(self, path='', *, cancelled=lambda: False):
        if path:
            return super().list(path, cancelled=cancelled)
        rows = []
        from commonUtils.runtime.operations import check_cancelled
        for child in self.root.iterdir():
            check_cancelled(cancelled)
            if child.name != 'Local':
                rows.append(self.entry(child.name))
        return sorted(rows, key=lambda row: (not row['directory'], row['name'].casefold()))


def shared_files(private_root):
    root = shared_documents_path(private_root)
    return SharedFiles(root) if root is not None else None
