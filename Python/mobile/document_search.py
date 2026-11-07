"""Cancellable filename-only search of the on-device document providers.

Encrypted names and references exist only in this owner and its live widgets.
No search index, file content reads or remote-storage providers are involved.
"""
import asyncio
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from commonUtils.runtime.operations import OperationCancelled, check_cancelled
from commonUtils.search.providers import search_resources
from .folder_listing import FolderListing
from .files_ui import local_read_available


def scan_local_documents(app, query, *, cancelled=lambda: False):
    with ExitStack() as cleanup:
        roots = app.ordinary_file_roots(include_collections=False)
        if local_read_available(app) and app.feature_enabled('rclone'):
            roots.update(app.existing_crypt_locations())
            linked = app.linked_crypt_locations()
            # Discovery opens these providers before traversal starts. Retire
            # even the unvisited providers when a query is cancelled early.
            for provider in linked.values():
                if hasattr(provider, 'close'):
                    cleanup.callback(provider.close)
            roots.update(linked)
        return _scan_locations(app, roots, query, cancelled=cancelled)


def _scan_locations(app, roots, query, *, cancelled):
    failures, hits, seen = [], [], set()
    # Local and Received are enumerated separately from Shared to avoid aliases.
    for label in roots:
        check_cancelled(cancelled)
        provider = None
        try:
            provider = app.storage_provider(label, roots)
            if getattr(provider, 'remote_storage', False):
                continue
            # SharedFiles excludes collection roots here. Its recursive hook
            # otherwise includes them, so use the guarded ordinary list path.
            listing = getattr(provider, 'indexed_list', provider.list)
            def children(folder, *, cancelled):
                return [row for row in listing(folder, cancelled=cancelled)
                        if app.folder_path_visible(row['path'], directory=row['directory'])]
            result = search_resources(provider, '', query, cancelled=cancelled,
                                      list_children=children)
            failures.extend(result.errors)
            for row in result.rows:
                key = provider.relative(row['path'])
                private = bool(provider.private)
                if private:
                    source = dict(type='crypt', remote=provider.remote, identity=provider.identity,
                                  namespace=provider.storage_namespace, key=key)
                    identity = ('crypt', source['identity'], source['namespace'], key)
                else:
                    path = str(Path(provider.root) / key)
                    source, identity = dict(type='local', path=path), ('local', path)
                if identity in seen:
                    continue
                seen.add(identity)
                hits.append(dict(name=PurePosixPath(key).name, path=key, location=label,
                                 source=source, private=private, directory=row['directory']))
        except (OSError, ValueError):
            failures.append((label, 'Location could not be searched.'))
        finally:
            if provider is not None and hasattr(provider, 'close'):
                provider.close()
    check_cancelled(cancelled)
    # Legacy saved drafts have no public collection path, but are local files.
    from commonUtils.search.names import matches_name, search_terms
    terms = search_terms(query)
    if app.feature_enabled('text_editor'):
        for record in app.store.cached_summaries():
            if matches_name(record.name, terms):
                hits.append(dict(name=record.name, path=record.name, location='Saved documents',
                                 source=dict(type='managed', resource=record.id), private=False))
    if app.feature_enabled('notebooks'):
        from features.notebooks.mobile.documents import repository
        for key, name in repository(app).list():
            check_cancelled(cancelled)
            if matches_name(name, terms):
                hits.append(dict(name=name, path=name, location='Saved documents',
                                 source=dict(type='notebook', resource=key), private=False))
    return sorted(hits, key=lambda hit: (hit['name'].casefold(), hit['location'], hit['path'])), failures


async def reveal_search_hit(app, hit):
    """Reveal a search result using the owning browser and its file actions."""
    from .document_sources import show_folder_location
    source = hit['source']
    if source['type'] == 'local':
        return await show_folder_location(app, dict(path=Path(source['path'])))
    if source['type'] != 'crypt':
        return False
    roots = dict(app.existing_crypt_locations())
    roots.update(app.linked_crypt_locations())
    provider = app.storage_provider(hit['location'], roots)
    if (provider.identity != source['identity'] or provider.storage_namespace != source['namespace']
            or provider.remote != source['remote']):
        raise ValueError('The encrypted file connection changed.')
    return await show_folder_location(app, dict(provider=provider, key=source['key']))


class DocumentSearch:
    def __init__(self, app, publish):
        self.app, self.publish = app, publish
        self.task = None
        self.listing = FolderListing(active=lambda: app.active_host,
            context=lambda: app.documents_query.strip(), location=lambda: None,
            credentials=lambda: (getattr(app, 'cloud_client', None),
                                 getattr(getattr(app, 'cloud_client', None), 'generation', None)))

    def stop_local_search(self):
        self.listing.invalidate()
        if self.task is not None:
            self.task.cancel()
            self.task = None

    def start(self, query):
        self.stop_local_search()
        work = self.listing.begin()
        async def search():
            try:
                hits, failures = await asyncio.to_thread(scan_local_documents, self.app, query,
                                                         cancelled=work.cancel.is_set)
                if self.listing.accepts(work, private=True):
                    self.publish(hits, failures)
            except (asyncio.CancelledError, OperationCancelled):
                work.cancel.set()
            except (OSError, ValueError):
                if self.listing.accepts(work, private=True):
                    self.publish([], [('Local files', 'Search could not finish.')])
        self.task = self.app.loop.create_task(search())
