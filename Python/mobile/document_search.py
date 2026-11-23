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
from .local_search import search_location_label
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
    def run(location, listing, load_match, phase, *, cache_pass=False):
        nonlocal checked
        label, provider = location.label, location.provider
        consumed = scanned = 0

        def report_cache(value):
            nonlocal phase
            phase = value

        def report(result):
            nonlocal consumed, scanned
            scanned = result.scanned
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
                if identity not in seen:
                    seen.add(identity)
                    hits.append(dict(name=PurePosixPath(key).name, path=key, location=label,
                                     source=source, private=private, directory=row['directory']))
            consumed = len(result.rows)
            if progress is not None:
                progress(checked + scanned, phase, tuple(hits[:50]), location.name)

        def children(folder, *, cancelled):
            rows = listing(folder, cancelled=cancelled, status=report_cache)
            return (row for row in rows
                    if app.folder_path_visible(row['path'], directory=row['directory']))

        try:
            if progress is not None:
                progress(checked, phase, tuple(hits[:50]), location.name)
            result = search_resources(provider, '', query, cancelled=cancelled,
                                      list_children=children, load_match=load_match,
                                      progress=report if progress is not None else None)
            report(result)
            if not cache_pass:
                failures.extend(result.errors)
        except (OSError, ValueError):
            if not cache_pass:
                failures.append((label, 'Location could not be searched.'))
        finally:
            checked += scanned

    # Local and Received are enumerated separately from legacy Shared to avoid aliases.
    with ExitStack() as cleanup:
        locations = []
        for label in roots:
            check_cancelled(cancelled)
            try:
                provider = app.storage_provider(label, roots)
            except (OSError, ValueError):
                failures.append((label, 'Location could not be searched.'))
                continue
            if hasattr(provider, 'close'):
                cleanup.callback(provider.close)
            if not getattr(provider, 'remote_storage', False):
                locations.append(_search_location(app, label, provider, cleanup))
        for location in locations:
            if location.cached is not None:
                phase = 'crypt_cached_hints' if location.provider.private else 'cached_hints'
                run(location, location.cached, location.validate, phase, cache_pass=True)
        for location in locations:
            run(location, location.live, location.reuse, 'checking_storage')
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


def _search_location(app, label, provider, cleanup):
    from types import SimpleNamespace
    from .device_name_cache import device_name_listing, supports_device_name_cache

    name = device_files_label(app) if type(provider) is PhoneFiles else search_location_label(label, provider)
    search_listing = getattr(provider, 'search_listing', None)
    cached_listing = getattr(provider, 'cached_search_listing', None)
    verified = {}

    def validate(path):
        try:
            row = provider.entry(path)
        except (OSError, ValueError) as error:
            # Stale cache hints are disposable. The storage pass owns errors.
            raise FileNotFoundError(path) from error
        verified[path] = row
        return row

    def reuse(path):
        return verified[path] if path in verified else validate(path)

    if supports_device_name_cache(provider):
        listing = cleanup.enter_context(device_name_listing(provider, app.private_root / 'Cache'))
        def live(folder, *, cancelled, status):
            return listing(folder, cancelled=cancelled, cache_status=status)

        def cached(folder, *, cancelled, status):
            return listing(folder, cancelled=cancelled, cached_only=True)

        return SimpleNamespace(label=label, name=name, provider=provider, live=live,
                               cached=cached, validate=validate, reuse=reuse)

    # SharedFiles excludes managed roots. Preserve its guarded listing rather
    # than falling back to an unrestricted physical traversal.
    listing = (getattr(provider, 'indexed_list', None)
               or getattr(provider, 'list_names', provider.list))

    def live(folder, *, cancelled, status):
        if search_listing is not None:
            return search_listing(folder, cancelled=cancelled, cache_status=status, names_only=True)
        return listing(folder, cancelled=cancelled)

    def cached(folder, *, cancelled, status):
        return cached_listing(folder, cancelled=cancelled)

    return SimpleNamespace(label=label, name=name, provider=provider, live=live,
                           cached=cached if cached_listing is not None else None,
                           validate=validate, reuse=reuse if search_listing is not None else None)


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
        last_cache_pass = None
        observed_count = 0
        checked_localcrypt_cache = False
        first_match_shown = False
        finished = False

        def display_progress(checked, cache_phase, hits, location):
            if not finished and self.listing.accepts(work, private=True):
                self.publish_progress(checked, cache_phase, hits, location)

        def report(checked, cache_phase, hits, location):
            nonlocal last_report, first_match_shown, last_location, last_cache_pass
            nonlocal observed_count, checked_localcrypt_cache
            now = monotonic()
            first_hit = bool(hits) and not first_match_shown
            cache_pass = cache_phase in ('cached_hints', 'crypt_cached_hints')
            if cache_phase == 'crypt_cached_hints' and checked > observed_count:
                checked_localcrypt_cache = True
            observed_count = checked
            if not work.cancel.is_set() and (location != last_location or cache_pass != last_cache_pass
                                             or first_hit or now - last_report >= .25):
                last_report = now
                last_location = location
                last_cache_pass = cache_pass
                first_match_shown = first_match_shown or first_hit
                self.app.loop.call_soon_threadsafe(display_progress, checked, cache_phase, hits, location)

        async def search():
            nonlocal finished
            try:
                hits, failures = await asyncio.to_thread(scan_local_documents, self.app, query,
                                                         cancelled=work.cancel.is_set, progress=report)
                finished = True
                if self.listing.accepts(work, private=True):
                    self.publish(hits, failures, checked_localcrypt_cache=checked_localcrypt_cache)
            except (asyncio.CancelledError, OperationCancelled):
                work.cancel.set()
            except (OSError, ValueError):
                finished = True
                if self.listing.accepts(work, private=True):
                    self.publish([], [('Local files', 'Search could not finish.')])
        self.task = self.app.loop.create_task(search())
