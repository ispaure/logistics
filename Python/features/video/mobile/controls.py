"""Mobile command routing; native surfaces own gestures, this owner retains resources."""

import asyncio
import json
from pathlib import Path

from features.video.playback import SubtitleContent
from features.video.session import FolderQueue, parse_time
from services.documents.video_settings import SettingsStore


def native_options(options, content=None):
    """Deliver shared reader metrics without persisting host layout as a preference."""
    from commonUtils.ui.readers.layout import READER_LAYOUT
    values = json.loads(options)
    values['reader_layout'] = dict(margin=READER_LAYOUT.overlay_margin, extent=READER_LAYOUT.touch_extent)
    if content is not None:
        from services.documents.storage import document_sources
        private = any(getattr(source, 'private', False) for source in document_sources(content.provider))
        values['video_title'] = Path(content.path).name
        values['source_remote'] = content.remote
        values['source_private'] = private
        values['source_label'] = ('Cloud file' if content.remote else
                                  'Local encrypted file' if private else 'Local file')
    return json.dumps(values)


class PlaybackControls:
    def __init__(self, owner):
        self.owner = owner
        self.store = SettingsStore(Path(owner.app.private_root) / "Video")
        self.settings = self.store.load()
        self.queue = FolderQueue(owner.content.path, [])
        self.busy = False
        self.task = None
        self.jobs = set()

    def dispatch(self, name, value=""):
        owner = self.owner

        def schedule():
            if not owner.closed:
                task = owner.app.loop.create_task(self.command(str(name), str(value)))
                self.jobs.add(task)
                task.add_done_callback(self.finished)

        owner.app.loop.call_soon_threadsafe(schedule)

    def finished(self, task):
        self.jobs.discard(task)
        if not task.cancelled() and task.exception() is not None:
            self.owner.app.loop.call_exception_handler(
                dict(message="Video control failed", exception=task.exception())
            )

    async def finish(self):
        jobs = [job for job in self.jobs if job is not self.task]
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)

    async def command(self, name, value):
        owner = self.owner
        if owner.closed or owner.hidden or not owner.allowed():
            return
        try:
            if name == "settings":
                self.settings = await asyncio.to_thread(
                    self.store.save, json.loads(value)
                )
                if not owner.closed and not owner.hidden and owner.allowed():
                    owner.native.configure(
                        self.settings.json(), json.dumps(self.queue.rows())
                    )
            elif name == "seek":
                owner.native.seek(parse_time(value))
            elif name in ("previous", "next", "queue", "ended"):
                if self.busy or (name == "ended" and not self.settings.autoplay_next):
                    return
                path = (
                    value
                    if name == "queue"
                    else self.queue.adjacent(-1 if name == "previous" else 1)
                )
                if path and path in self.queue.paths and path != owner.content.path:
                    from .player import open_video

                    self.busy = True
                    self.task = asyncio.current_task()
                    try:
                        await open_video(owner.app, owner.content.provider, path)
                    finally:
                        self.busy = False
                        self.task = None
            elif name == "showInFolder":
                if self.busy:
                    return
                from services.documents.mobile_views import show_reader_source
                # Keep the provider alive until the browser has acquired its own scope.
                self.busy = True
                self.task = asyncio.current_task()
                try:
                    owner.native.pause()
                    owner.native.hide()
                    owner.hidden = True
                    await show_reader_source(owner.app, owner.content.provider, owner.content.path)
                finally:
                    try:
                        await owner.close()
                    finally:
                        self.busy = False
                        self.task = None
            elif name == "subtitleBrowse":
                await self.browse(value)
            elif name == "subtitleAttach":
                subtitle = await asyncio.to_thread(
                    SubtitleContent, owner.content.provider, value
                )
                try:
                    if subtitle.size > 8 * 1024 * 1024:
                        raise ValueError("Subtitles must be smaller than 8 MiB.")
                    if owner.closed or not owner.allowed():
                        return
                    url = owner.transport.add_subtitle(subtitle)
                    owner.native.add_subtitle(url)
                    owner.subtitles.append(subtitle)
                    subtitle = None
                finally:
                    if subtitle is not None:
                        subtitle.close()
        except (OSError, ValueError, PermissionError) as error:
            if not owner.closed and owner.native is not None:
                owner.native.status(str(error)[:150])

    async def browse(self, folder):
        owner = self.owner
        rows = await asyncio.to_thread(owner.content.provider.list, folder)
        if owner.closed or owner.hidden or not owner.allowed():
            return
        entries = []
        if folder:
            entries.append(
                dict(
                    name="↑ Parent folder",
                    path=folder.rpartition("/")[0],
                    directory=True,
                )
            )
        entries.extend(
            dict(name=row["name"], path=row["path"], directory=bool(row["directory"]))
            for row in rows[:10000]
            if row["directory"]
            or Path(row["name"]).suffix.lower() in SubtitleContent.extensions
        )
        owner.native.subtitle_browser(json.dumps(entries))
