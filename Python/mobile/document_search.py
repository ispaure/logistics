"""Cancellable filename-only search of the on-device document providers.

Encrypted names and references exist only in this owner and its live widgets.
Ordinary device names can use the persistent filename cache. Search reads no
file contents and excludes remote-storage providers.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from contextlib import ExitStack, nullcontext
from pathlib import Path, PurePosixPath
from time import monotonic
from commonUtils.runtime.operations import OperationCancelled, check_cancelled
from commonUtils.search.providers import search_resources
from .folder_listing import FolderListing
from .files_ui import local_read_available
from .local_sources import PhoneFiles, device_files_label


def scan_local_documents(app, query, *, cancelled=lambda: False, progress=None):
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
        return _scan_locations(app, roots, query, cancelled=cancelled, progress=progress)


def _scan_locations(app, roots, query, *, cancelled, progress):
    failures, hits, seen = [], [], set()
    checked = 0
    # Local and Received are enumerated separately from Shared to avoid aliases.
    for label in roots:
        check_cancelled(cancelled)
        provider = None
        location_checked = 0
        cache_phase = ''
        consumed = 0
        location = label

        def report_cache(phase):
            nonlocal cache_phase
            cache_phase = phase

        def report(result):
            nonlocal consumed, location_checked
            location_checked = result.scanned
            for row in result.rows[consumed:]:
                check_cancelled(cancelled)
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
            consumed = len(result.rows)
            if progress is not None:
                progress(checked + location_checked, cache_phase, tuple(hits[:50]), location)

        try:
            provider = app.storage_provider(label, roots)
            if getattr(provider, 'remote_storage', False):
                continue
            device = type(provider) is PhoneFiles and not provider.private and not getattr(provider, 'session_only', False)
            if device:
                location = device_files_label(app)
                from .device_name_cache import device_name_listing
                context = device_name_listing(provider, app.private_root / 'Cache', status=report_cache)
            else:
                context = nullcontext()
            if progress is not None:
                progress(checked, cache_phase, tuple(hits[:50]), location)
            # SharedFiles excludes collection roots here. Its recursive hook
            # otherwise includes them, so use the guarded ordinary list path.
            search_listing = getattr(provider, 'search_listing', None)
            listing = (search_listing or getattr(provider, 'indexed_list', None)
                       or getattr(provider, 'list_names', provider.list))
            with context as device_listing:
                def children(folder, *, cancelled):
                    if search_listing is not None:
                        rows = search_listing(folder, cancelled=cancelled, cache_status=report_cache)
                    else:
                        rows = (device_listing or listing)(folder, cancelled=cancelled)
                    return (row for row in rows
                            if app.folder_path_visible(row['path'], directory=row['directory']))

                result = search_resources(provider, '', query, cancelled=cancelled, list_children=children,
                                          load_match=provider.entry if device else None,
                                          progress=report if progress is not None else None)
            report(result)
            failures.extend(result.errors)
        except (OSError, ValueError):
            failures.append((label, 'Location could not be searched.'))
        finally:
            checked += location_checked
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
    return hits, failures


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
    def __init__(self, app, publish, publish_progress):
        self.app, self.publish = app, publish
        self.publish_progress = publish_progress
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
        last_report = float('-inf')
        last_location = ''
        first_match_shown = False
        finished = False

        def display_progress(checked, cache_phase, hits, location):
            if not finished and self.listing.accepts(work, private=True):
                self.publish_progress(checked, cache_phase, hits, location)

        def report(checked, cache_phase, hits, location):
            nonlocal last_report, first_match_shown, last_location
            now = monotonic()
            first_hit = bool(hits) and not first_match_shown
            if not work.cancel.is_set() and (location != last_location or first_hit or now - last_report >= .25):
                last_report = now
                last_location = location
                first_match_shown = first_match_shown or first_hit
                self.app.loop.call_soon_threadsafe(display_progress, checked, cache_phase, hits, location)

        async def search():
            nonlocal finished
            try:
                hits, failures = await asyncio.to_thread(scan_local_documents, self.app, query,
                                                         cancelled=work.cancel.is_set, progress=report)
                finished = True
                if self.listing.accepts(work, private=True):
                    self.publish(hits, failures)
            except (asyncio.CancelledError, OperationCancelled):
                work.cancel.set()
            except (OSError, ValueError):
                finished = True
                if self.listing.accepts(work, private=True):
                    self.publish([], [('Local files', 'Search could not finish.')])
        self.task = self.app.loop.create_task(search())
