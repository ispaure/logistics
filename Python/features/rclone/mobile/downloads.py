"""Offline-copy selection, import routing and export lifetime for mobile rclone."""
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from .storage_location import collection_path


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
        cloud.download_labels = {f'{i + 1}. {path.name}': path for i, path in enumerate(cloud.downloads.items())}
        cloud.download_selector.items = list(cloud.download_labels)
        if selected:
            cloud.download_selector.value = next(key for key, path in cloud.download_labels.items() if path == selected)

    async def open_download(self, widget=None, *, path=None, destination=None, **kwargs):
        cloud = self.cloud
        selected = path if path is not None else cloud.download_labels.get(cloud.download_selector.value)
        if selected is None:
            return False
        with cloud.rclone_ui.opening_status(dict(path=str(selected)), destination=destination):
            await asyncio.sleep(0)
            return await self._open_download(path=selected, destination=destination)

    async def _open_download(self, *, path, destination=None):
        cloud = self.cloud
        from commonUtils.runtime.resources.documents import LocalDocuments
        destination = destination or cloud.native_host.state.destination
        if not hasattr(cloud, 'cloud_view'):
            cloud.show_cloud(present=False)
        selected = path if path is not None else cloud.download_labels.get(cloud.download_selector.value)
        selected = Path(selected) if selected is not None else None
        if selected is not None and selected.suffix.lower() == '.rmdoc':
            from services.documents.mobile_notebooks import open_notebook
            return await open_notebook(cloud.app, path=selected, destination=destination)
        if selected is not None and Path(selected).suffix.lower() == '.pdf':
            from features.pdf.mobile.copies import PDFCopies
            from commonUtils.runtime.resources.local import LocalFiles
            selected = Path(selected)
            return await cloud.open_crypt(copies=PDFCopies(LocalFiles(selected.parent)), key=selected.name, destination=destination)
        independent = (cloud.cloud_busy and path is not None
                       and selected.resolve().is_relative_to((collection_path(cloud.private_root)).resolve()))
        if (cloud.cloud_busy and not independent) or selected is None:
            return False
        if not independent:
            cloud.set_cloud_busy(True)
        try:
            ResourceImports = cloud.rclone_ui.ResourceImports
            collection_root = (None if Path(selected).resolve().is_relative_to(Path(cloud.private_root).resolve())
                               else collection_path(cloud.private_root).resolve())
            if (not hasattr(cloud, 'resource_imports')
                    or cloud.resource_imports.collection_root != collection_root):
                cloud.resource_imports = ResourceImports(cloud.private_root, collection_root=collection_root)
            imported = cloud.resource_imports.find(selected)
            def remember_folder(provider, resource):
                if not hasattr(cloud.app, '_document_folder_sources'):
                    cloud.app._document_folder_sources = {}
                cloud.app._document_folder_sources[provider, resource] = dict(type='local', path=str(selected))
            if imported is not None:
                remember_folder(imported['provider'], imported['resource'])
                if imported['provider'] == 'library':
                    if not any(session.identity == ('library', imported['resource'])
                               for session in cloud.app.workspace.sessions.values()):
                        cloud.reader_manager().catalog.library_store.remember_source(imported['resource'], selected)
                    return await cloud.open_book(imported['resource'], destination=destination)
                elif cloud.open_document(imported['resource']):
                    cloud.show_documents(resume=True, destination=destination)
                else:
                    raise ValueError('The imported copy is unavailable; its index and source were preserved.')
                return True
            if selected.suffix.lower() in {'.epub', '.cbz', '.zip'}:
                catalog = cloud.reader_manager().catalog
                generation = cloud.navigation_generation
                record = await asyncio.to_thread(catalog.library_store.import_book, LocalDocuments(), selected)
                cloud.resource_imports.remember(selected, 'library', record['id'])
                remember_folder('library', record['id'])
                if not cloud.active_host or cloud.navigation_generation != generation:
                    return False
                cloud.refresh_library()
                return await cloud.open_book(record['id'], destination=destination)
            else:
                generation = cloud.navigation_generation
                doc = await asyncio.to_thread(cloud.store.import_document, LocalDocuments(), selected)
                cloud.resource_imports.remember(selected, 'managed-text', doc.id)
                remember_folder('managed-text', doc.id)
                cloud.refresh_documents()
                if not cloud.active_host or cloud.navigation_generation != generation:
                    return False
                if not cloud.open_document(doc.id):
                    return False
                cloud.show_documents(destination=destination)
                return True
        except Exception as error:
            cloud.cloud_status.value = 'Open failed: ' + str(error)[:300]
            if independent:
                cloud.file_status.value = cloud.cloud_status.value
                readers = getattr(cloud, 'readers', None)
                if readers is not None and readers.active is not None:
                    readers.active.book_status.text = cloud.cloud_status.value
            return False
        finally:
            if not independent:
                cloud.set_cloud_busy(False)

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

