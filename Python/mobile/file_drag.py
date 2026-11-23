"""Same-browser drag moves using the guarded mobile file operation."""

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from uuid import uuid4
from weakref import ref

from commonUtils.runtime.resources.provider import capabilities
from .file_operations import FileDestination, FileOperationRequest


@dataclass(frozen=True)
class DragSource:
    token: str
    path: PurePosixPath
    revision: object
    stamp: tuple


SPRING_DELAY = .7
SPRING_FLASH = .12


class FileDrag:
    def __init__(self, owner, browser):
        self.owner = ref(owner)
        self.browser = ref(browser)
        self.source = None
        self.task = None
        self.hover_task = None
        self.hover_entry = None
        self.hover_point = None
        self.highlight = None
        self.opening = False
        self.entered = None
        self.entered_at = None

    def context(self):
        owner, browser = self.owner(), self.browser()
        if (owner is None or browser is None or browser.closed or not owner.active_host
                or owner.file_browser is not browser or owner.cloud_busy or browser.navigation_busy
                or browser.search_open or browser.on_check_entry is not None):
            return None
        provider = owner.file_provider
        access = capabilities(provider)
        if not (access.create and access.rename and access.delete) or getattr(provider, 'read_only', False):
            return None
        client = owner.cloud_client
        scope = (owner.file_loaded_location[0], provider.storage_id, provider.storage_namespace,
                 id(client), getattr(client, 'generation', None))
        stamp = (scope, browser.epoch, owner.navigation_generation, owner.file_path)
        return owner, browser, provider, client, stamp

    @staticmethod
    def path(browser, provider, entry):
        if entry is None or not browser._entry_current(entry):
            return None
        row = entry.payload
        if not row or not row.get('path') or row.get('revision') is None:
            return None
        from .local_sources import SharedFiles
        if isinstance(provider, SharedFiles) and provider.is_managed_collection(row['path']):
            return None
        return PurePosixPath(row['path'])

    def begin(self, entry):
        context = self.context()
        if context is None or self.opening or self.task is not None and not self.task.done():
            return None
        _, browser, provider, _, stamp = context
        path = self.path(browser, provider, entry)
        if path is None:
            return None
        self.clear_hover()
        self.entered = None
        self.entered_at = None
        self.source = DragSource(uuid4().hex, path, entry.payload['revision'], stamp)
        return self.source.token

    def end(self, token):
        if self.source is not None and self.source.token == token:
            self.source = None
            self.entered = None
            self.entered_at = None
            self.clear_hover()

    def request(self, token, folder):
        source, context = self.source, self.context()
        if source is None or source.token != token or context is None or self.opening:
            return None
        owner, browser, provider, client, stamp = context
        if source.stamp != stamp:
            return None
        if folder is not None and folder.container:
            destination = self.path(browser, provider, folder)
            if destination is None:
                return None
            revision = folder.payload['revision']
        elif self.entered is not None and str(self.entered[0]) == owner.file_path:
            destination, revision = self.entered
        else:
            return None
        origin = source.path
        if destination in (origin, origin.parent) or origin in destination.parents:
            return None
        location = FileDestination(owner.private_root, client, provider, stamp[0][-1])
        return FileOperationRequest('move', provider, origin.as_posix(), (destination / origin.name).as_posix(),
                                    location, expected_revision=source.revision, expected_parent_revision=revision)

    def target_entry(self, entry, point):
        if self.entered_at is not None and point is not None:
            if sum((new - old) ** 2 for new, old in zip(point, self.entered_at)) < 12 ** 2:
                return None
            self.entered_at = None
        return entry

    def hover(self, token, folder, highlight, point=None):
        if self.opening:
            return
        if folder is not None and folder is self.hover_entry:
            self.hover_point = point
            return
        self.clear_hover()
        if folder is None or not folder.container or self.request(token, folder) is None:
            return
        self.hover_entry, self.highlight = folder, highlight
        self.hover_point = point
        self.hover_task = self.owner().loop.create_task(self.spring_open(token, folder, highlight))

    def clear_hover(self):
        if self.opening:
            return
        if self.hover_task is not None:
            self.hover_task.cancel()
        if self.highlight is not None:
            self.highlight(False)
        self.hover_task = self.hover_entry = self.hover_point = self.highlight = None

    async def spring_open(self, token, folder, highlight):
        await asyncio.sleep(SPRING_DELAY)
        for _ in range(2):
            if self.request(token, folder) is None:
                return
            highlight(True)
            await asyncio.sleep(SPRING_FLASH)
            highlight(False)
            await asyncio.sleep(SPRING_FLASH)
        if self.request(token, folder) is None:
            return
        source, owner = self.source, self.owner()
        path = PurePosixPath(folder.payload['path'])
        opened_at = self.hover_point
        self.opening = True
        try:
            if not await owner.browser_file_folder(folder.payload) or self.source is not source:
                return
            context = self.context()
            if context is not None and context[-1][0] == source.stamp[0] and owner.file_path == str(path):
                self.source = replace(source, stamp=context[-1])
                self.entered = path, folder.payload['revision']
                self.entered_at = opened_at
                return True
            self.end(token)
        finally:
            self.opening = False
            self.hover_task = self.hover_entry = self.hover_point = self.highlight = None

    def finish(self, token, folder):
        if self.opening and self.hover_task is not None:
            task = self.hover_task

            async def finish_opening():
                if not await task or not self.drop(token, None):
                    self.end(token)

            self.owner().loop.create_task(finish_opening())
        elif not self.drop(token, folder):
            self.end(token)

    def drop(self, token, folder):
        request = self.request(token, folder)
        if request is None:
            return False
        owner = self.owner()
        stamp = self.source.stamp
        self.end(token)
        self.task = owner.loop.create_task(self.move(request, stamp))
        return True

    async def move(self, request, stamp):
        context = self.context()
        if context is None or context[-1] != stamp:
            return False
        owner = context[0]
        if not await owner.file_operations().run(lambda: request):
            return False
        context = self.context()
        if context is not None and context[-1] == stamp and await owner.browse_files():
            name = PurePosixPath(request.target).parent.name
            owner.file_status.value = f'Moved to {name}.'
        return True
