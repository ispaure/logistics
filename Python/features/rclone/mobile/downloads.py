"""Offline-copy selection, import routing and export lifetime for mobile rclone."""
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from services.documents.locations import collection_path


@dataclass
class DownloadState:
    # Controls/resources remain absent until their owning view is constructed.
    downloads: Any = field(init=False, repr=False)
    download_labels: Any = field(init=False, repr=False)
    download_selector: Any = field(init=False, repr=False)
    download_export: Any = field(init=False, repr=False)
    download_open: Any = field(init=False, repr=False)
    resource_imports: Any = field(init=False, repr=False)


class DownloadWorkflow:
    def __init__(self, cloud):
        self.cloud = cloud

    def refresh_downloads(self, selected=None):
        cloud = self.cloud
        if not hasattr(cloud, 'downloads'):
            return
        cloud.download_labels = {f'{i + 1}. {path.name}': path for i, path in enumerate(cloud.downloads.items())}
        cloud.download_selector.items = list(cloud.download_labels)
        if selected:
            cloud.download_selector.value = next(key for key, path in cloud.download_labels.items() if path == selected)

    async def open_download(self, widget=None, *, path=None, destination=None, **kwargs):
        cloud = self.cloud
        selected = path if path is not None else cloud.download_labels.get(cloud.download_selector.value)
        if selected is None:
            return False
        if not cloud.app.require_document_feature(str(selected)):
            return False
        with cloud.rclone_ui.opening_status(dict(path=str(selected)), destination=destination):
            await asyncio.sleep(0)
            return await self._open_download(path=selected, destination=destination)

    async def _open_download(self, *, path, destination=None):
        return await self.cloud.open_local_document(path, destination=destination)

    async def export_download(self, widget=None, **kwargs):
        cloud = self.cloud
        export_file = cloud.rclone_ui.export_file
        selected = cloud.download_labels.get(cloud.download_selector.value)
        if cloud.cloud_busy or selected is None:
            return
        cloud.set_cloud_busy(True)
        try:
            done = await export_file(cloud, selected)
            cloud.cloud_status.value = 'Private copy exported.' if done else 'Export cancelled.'
        except Exception as error:
            cloud.cloud_status.value = 'Export failed: ' + str(error)[:300]
        finally:
            cloud.set_cloud_busy(False)

