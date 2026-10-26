"""Ordinary document import and reopen; independent of connection features."""
import asyncio
from pathlib import Path
from services.documents.locations import collection_path


async def open_local_document(app, path, *, destination=None):
    from commonUtils.runtime.resources.documents import LocalDocuments
    destination = destination or app.native_host.state.destination
    selected = path
    selected = Path(selected) if selected is not None else None
    if selected is not None and selected.suffix.lower() == '.rmdoc':
        from services.documents.mobile_notebooks import open_notebook
        return await open_notebook(app, path=selected, destination=destination)
    if selected is not None and Path(selected).suffix.lower() == '.pdf':
        from features.pdf.mobile.copies import PDFCopies
        from commonUtils.runtime.resources.local import LocalFiles
        selected = Path(selected)
        return await app.open_crypt(copies=PDFCopies(LocalFiles(selected.parent)), key=selected.name, destination=destination)
    if getattr(app, '_local_document_opening', False) or selected is None:
        return False
    app._local_document_opening = True
    try:
        from .resource_imports import ResourceImports
        collection_root = (None if Path(selected).resolve().is_relative_to(Path(app.private_root).resolve())
                           else collection_path(app.private_root).resolve())
        if (not hasattr(app, 'resource_imports')
                or app.resource_imports.collection_root != collection_root):
            app.resource_imports = ResourceImports(app.private_root, collection_root=collection_root)
        imported = app.resource_imports.find(selected)
        def remember_folder(provider, resource):
            if not hasattr(app, '_document_folder_sources'):
                app._document_folder_sources = {}
            app._document_folder_sources[provider, resource] = dict(type='local', path=str(selected))
        if imported is not None:
            remember_folder(imported['provider'], imported['resource'])
            if imported['provider'] == 'library':
                if not any(session.identity == ('library', imported['resource'])
                           for session in app.workspace.sessions.values()):
                    app.reader_manager().catalog.library_store.remember_source(imported['resource'], selected)
                return await app.open_book(imported['resource'], destination=destination)
            elif app.open_document(imported['resource']):
                app.show_documents(resume=True, destination=destination)
            else:
                raise ValueError('The imported copy is unavailable; its index and source were preserved.')
            return True
        if selected.suffix.lower() in {'.epub', '.cbz', '.zip'}:
            catalog = app.reader_manager().catalog
            generation = app.navigation_generation
            record = await asyncio.to_thread(catalog.library_store.import_book, LocalDocuments(), selected)
            app.resource_imports.remember(selected, 'library', record['id'])
            remember_folder('library', record['id'])
            if not app.active_host or app.navigation_generation != generation:
                return False
            app.refresh_library()
            return await app.open_book(record['id'], destination=destination)
        else:
            generation = app.navigation_generation
            doc = await asyncio.to_thread(app.store.import_document, LocalDocuments(), selected)
            app.resource_imports.remember(selected, 'managed-text', doc.id)
            remember_folder('managed-text', doc.id)
            app.refresh_documents()
            if not app.active_host or app.navigation_generation != generation:
                return False
            if not app.open_document(doc.id):
                return False
            app.show_documents(destination=destination)
            return True
    except Exception as error:
        app.document_status.value = 'Open failed: ' + str(error)[:300]
        return False
    finally:
        app._local_document_opening = False
