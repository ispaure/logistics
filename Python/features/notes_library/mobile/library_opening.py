"""Mobile document admission, preparation, publication and retirement.

The browser owns library navigation; this owner keeps document transitions and
native publication tokens together. Failed reads retain the published document.
"""
import asyncio
import posixpath
import re
from html import unescape
from json import dumps
from pathlib import PurePosixPath
from textwrap import fill
from time import perf_counter
from urllib.parse import parse_qs, quote, unquote, urlsplit
from uuid import uuid4
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.ui.native.inline_html import set_inline_html
from ..notes import MAX_PREVIEW_HTML, MARKDOWN, document_kind
from ..dataview import view_plan
from ..dataview_script import worker_policy
from .library_panels import LibraryOpening
from .inline_video import install_controls, video_embed


class LibraryDocuments:
    async def document_error(self, title, error):
        if self.valid():
            await self.host.show_error(title, str(error))

    async def prepare_leave(self, *, save=False, confirm=None):
        editor = self.embedded
        if editor is None:
            return True
        if editor.busy and getattr(editor, 'kind', None) != 'notebook':
            self.notice.text = 'Wait for the document operation to finish.'
            return False
        try:
            await editor.flush()
            if not self.valid() or self.embedded is not editor:
                return False
            if editor.busy:
                self.notice.text = 'Wait for the document operation to finish.'
                return False
            if editor.dirty:
                if save or getattr(editor, 'autosave_on_leave', False):
                    return await editor.save() and self.valid() and self.embedded is editor
                confirm = confirm or self.host.confirm
                if confirm is None:
                    return False
                choice = await confirm()
                if not self.valid() or self.embedded is not editor:
                    return False
                if choice == 'save':
                    return await editor.save()
                return choice == 'discard'
            return True
        except (OSError, ValueError) as error:
            self.notice.text = str(error)
            return False


    def retire_editor(self):
        if self.embedded is not None:
            formatted = getattr(self.embedded, 'formatted', None)
            if formatted is not None and self.path is not None:
                self.positions[self.path] = formatted.scroll_top
            self.embedded.dispose()
            self.embedded = None
        self.editing = False
        if self.session is not None:
            self.session.dirty = False


    def mark_open_timing(self, stage, epoch):
        timing = self._open_timing
        if timing is not None and timing['epoch'] == epoch:
            timing['stages_ms'][stage] = round((perf_counter() - timing['started']) * 1000, 2)
            self.host.open_timing({key: value for key, value in timing.items() if key != 'started'})


    async def open_note(self, path, *, remember=True, fragment="", resolve_link=False):
        return_side = getattr(self.sidebar, 'side', None)
        opened = await self._open_note(path, remember=remember, fragment=fragment, resolve_link=resolve_link)
        if opened and return_side is not None:
            self._document_return_side = None if return_side == 'files' and self.sidebar.expanded else return_side
        if opened:
            self.host.remember_document(self)
        return opened


    async def open_video_file(self, path, *, page=None):
        path = self.contained(path)
        if self.host.open_resource is None:
            self.notice.text = 'Video playback is unavailable in this host.'
            return False
        try:
            if not self.valid() or (page is not None and (self.base != page or self.editing)):
                return False
            # Pause page media before handing audio to the native player. Keep
            # the page and provider alive so returning from playback is immediate.
            surfaces = [self.web]
            formatted = getattr(self.embedded, 'formatted', None)
            if formatted is not None:
                surfaces.append(formatted.view)
            for surface in surfaces:
                await surface.evaluate_javascript("document.querySelectorAll('video').forEach(video => video.pause())")
            if not self.valid() or (page is not None and (self.base != page or self.editing)):
                return False
            self.speech.close()
            if page is not None:
                return bool(await self.host.open_resource(self.provider, path, fullscreen=True))
            return bool(await self.host.open_resource(self.provider, path))
        except (OSError, ValueError, PermissionError) as error:
            self.notice.text = str(error)
            return False


    async def _open_note(self, path, *, remember=True, fragment="", resolve_link=False):
        started = perf_counter()
        if not self.valid() or (getattr(self, '_moving_entry', False) and not getattr(self, '_reopening_after_move', False)):
            return False
        if not await self.prepare_leave():
            return False
        from services.documents.file_preview import is_video_file
        if not resolve_link and is_video_file(path):
            return await self.open_video_file(path)
        if not resolve_link and document_kind(path) is None:
            from .file_preview import LibraryFilePreview
            return await self.open_embedded(path, LibraryFilePreview.open, remember=remember)
        if not resolve_link and document_kind(path) == 'text':
            return await self.open_text(path, remember=remember)
        if not resolve_link and PurePosixPath(path).suffix.lower() == '.rmdoc':
            return await self.open_canvas(path, remember=remember)
        if not hasattr(self, 'page_loading'):
            self.page_loading = LibraryOpening(self)
        self.sidebar.show_detail()
        self.links_generation += 1
        self.epoch += 1
        epoch = self.epoch
        self._media_open_epoch = epoch
        self._media_open_path, self._media_open_pending = path, True
        if self.host.open_timing is not None:
            self._open_timing = dict(epoch=epoch, started=started, link=resolve_link,
                cached_folders_at_start=len(self.library._link_folders), stages_ms={})
            self.mark_open_timing('started', epoch)
        current = self.path
        cancelled = lambda: not self.valid() or epoch != self.epoch
        try:
            try:
                await asyncio.wait_for(self.remember_position(), timeout=.25)
            except asyncio.TimeoutError:
                pass
            if cancelled():
                return False
            self.page_loading.start(path, finding=resolve_link)
            self.speech.close()
            if not resolve_link:
                path = self.contained(path)
            if not resolve_link and PurePosixPath(path).suffix.lower() not in MARKDOWN:
                raise ValueError("Choose a Markdown note.")
            def stage(message):
                def publish():
                    if not cancelled() and self.page_loading.active:
                        self.page_loading.status.text = message
                        if resolve_link and message == 'Finding file…':
                            self.mark_open_timing('finding', epoch)
                        elif resolve_link and message.startswith('Reading '):
                            self.mark_open_timing('found', epoch)
                self.host.loop.call_soon_threadsafe(publish)
            path, found_fragment, data = await asyncio.to_thread(self.library.load_note, path,
                current=current, resolve_link=resolve_link, cancelled=cancelled, stage=stage)
            pages = await self.breadcrumb_pages(path, cancelled)
            if self._media_open_epoch == epoch:
                self._media_open_path = path
            if cancelled():
                return False
            fragment = found_fragment or fragment
            if resolve_link:
                self.page_loading.opening(path)
                if document_kind(path) != 'markdown':
                    self.page_loading.finish()
                    if is_video_file(path):
                        return await self.open_video_file(path)
                    if document_kind(path) is None:
                        from .file_preview import LibraryFilePreview
                        return await self.open_embedded(path, LibraryFilePreview.open, remember=remember)
                    opener = self.open_text if document_kind(path) == 'text' else self.open_canvas
                    return await opener(path, remember=remember)

            base = "https://markdown.invalid/vault/" + uuid4().hex + "/"
            def read():
                stage('Preparing embedded media…')
                plan = view_plan(data.decode("utf-8-sig"))
                html, videos = self.note_preview(plan.render() if plan.scripts else plan.source,
                    path, base, active=bool(plan.scripts), cancelled=cancelled)
                return html, videos, plan

            html, videos, plan = await asyncio.to_thread(read)
            if not self.valid() or epoch != self.epoch:
                return False
            self.mark_open_timing('prepared', epoch)
            # Native admission can still reject the styled page. Do not retire
            # the current editor or advance history until it has succeeded.
            set_inline_html(self.web, base, html)
            self.clear_video_actions()
            self.cancel_data_views()
            if remember and path != self.path:
                del self.history[self.history_index + 1 :]
                self.history.append(path)
                self.history_index = len(self.history) - 1
            self.retire_editor()
            self.article.clear()
            self.article.add(self.web)
            self.path = self.selected_path = path
            self.update_tree_selection()
            self.title.text = fill(PurePosixPath(path).name, width=28)
            self.base = base
            self.set_video_actions(videos)
            if self._open_timing is not None:
                self._open_timing['published_epoch'] = epoch
            self.data_view_plan = plan if plan.scripts else None
            self.data_views_loading = bool(plan.scripts)
            self.pending_fragment = fragment
            self.page_search.loading()
            self.edit.enabled = self.library.writable
            self.speech.button.enabled = True
            self.notice.text = ""
            self.back_button.enabled = self.history_index > 0
            self.forward_button.enabled = self.history_index < len(self.history) - 1
            self.up_button.enabled = True
            self.refresh_reader_actions()
            self.folder_pages.update(pages)
            self.sidebar.show_detail()
            self.refresh_chrome()
            self.host.render()
            self.mark_open_timing('published', epoch)
            return True
        except OperationCancelled:
            return False
        except (OSError, UnicodeError, ValueError) as error:
            if self.valid() and epoch == self.epoch:
                self.page_loading.finish()
                await self.document_error('Could not open document', error)
            return False
        finally:
            if self._media_open_epoch == epoch:
                self._media_open_pending = False
                await asyncio.to_thread(self.library.release_media, self.path,
                    active=lambda: self._media_open_epoch == epoch)
            await asyncio.to_thread(self.library.discard_media, path,
                active=lambda: path != self.path and not (
                    self._media_open_pending and path == self._media_open_path))
            if epoch == self.epoch:
                self.page_loading.finish()


    def follow_link(self, widget, url, **kwargs):
        if not self.valid() or self.path is None:
            return False
        if url == self.base + '?drawer=files':
            self.sidebar.show_sidebar()
            return False
        if url == self.base + '?drawer=links':
            self.host.loop.create_task(self.show_links(toggle=False))
            return False
        parsed = urlsplit(url)
        if not parsed.scheme and not parsed.netloc:
            target = url
        elif url.split("?", 1)[0] == self.base:
            query = parse_qs(parsed.query)
            if 'inline-video' in query:
                key = query['inline-video'][0]
                audio = getattr(self, '_inline_audio', None)
                if (key in self._page_videos and not self.editing and audio is not None
                        and audio.interactive()):
                    self.speech.close()
                    if audio.request_play():
                        self.web.evaluate_javascript('window.logisticsPlayVideo?.(' + dumps(key) + ')')
                return False
            if "video" in query:
                path = self._page_videos.get(query["video"][0])
                pending = self._video_opening
                if path is not None and not self.editing and (pending is None or pending.done()):
                    self._video_opening = self.host.loop.create_task(self.open_video_file(path, page=self.base))
                return False
            target = query.get("target", [""])[0]
        else:
            return False
        link = urlsplit(target)
        if not link.path and link.fragment:
            if getattr(self, 'data_views_loading', False):
                self.pending_fragment = link.fragment
            self.scroll_fragment(link.fragment)
            return False
        if (
            link.scheme
            or link.netloc
            or link.query
            or not link.path
            or link.path.startswith(("/", "\\"))
        ):
            return False
        try:
            self.contained(
                posixpath.normpath(
                    posixpath.join(posixpath.dirname(self.path), unquote(link.path))
                )
            )
        except ValueError:
            return False
        self.host.loop.create_task(self.open_note(target, resolve_link=True))
        return False


    def scroll_fragment(self, fragment):
        import json

        self.web.evaluate_javascript(
            "(function(){const h=document.getElementById("
            + json.dumps(unquote(fragment))
            + ");if(h)h.scrollIntoView();})()"
        )


    def page_loaded(self, widget=None, url=None, **kwargs):
        if self.editing or not self.valid():
            return
        if (self._open_timing is not None and self._open_timing.get('published_epoch') == self.epoch
                and 'dom_ready' not in self._open_timing['stages_ms']):
            self.mark_open_timing('dom_ready', self.epoch)
        plan = getattr(self, 'data_view_plan', None)
        if plan is not None:
            self.data_view_plan = None
            self.data_view_task = self.host.loop.create_task(self.render_data_views(plan, self.base, self.path))
        from .notes_swipe import document_swipes
        self.web.evaluate_javascript(document_swipes(self.base))
        self.page_search.loaded(reveal=not bool(self.pending_fragment))
        if self.pending_fragment and not getattr(self, 'data_views_loading', False):
            fragment, self.pending_fragment = self.pending_fragment, ""
            self.scroll_fragment(fragment)
        elif not self.pending_fragment and self.path in self.positions:
            self.web.evaluate_javascript('window.scrollTo(0,' + str(self.positions[self.path]) + ')')


    def clear_video_actions(self):
        if self._video_opening is not None:
            self._video_opening.cancel()
        audio = getattr(self, '_inline_audio', None)
        if audio is not None:
            self.pause_inline_videos()
            audio.unregister(self)
            self._inline_audio = None
        self._page_videos.clear()

    def set_video_actions(self, videos):
        self._page_videos = videos
        if videos:
            self._inline_audio = self.host.audio_output()
            if self._inline_audio is not None:
                self._inline_audio.register(self, self.pause_inline_videos)

    def pause_inline_videos(self):
        if getattr(self, '_inline_audio', None) is not None:
            self.web.evaluate_javascript("document.querySelectorAll('.note-video video').forEach(video => video.pause())")

    def note_preview(self, text, path, base, *, active=False, cancelled=lambda: False):
        sources = {}
        def remember_video(path, url):
            sources[url] = path

        videos = {}
        html = self.host.preview(text, image_source=self.library.image_source(
            path, cancelled=cancelled, on_video=remember_video, batch=True))
        html = self.data_view_html(html, active=active, base=base)
        def video_button(match):
            source = sources.get(unescape(match[1]))
            if source is None:
                return match[0]
            key = uuid4().hex
            videos[key] = source
            return video_embed(match[0], base, key, PurePosixPath(source).name)

        html = re.sub(r'<video controls\b[^>]*\bsrc="([^"]+)"[^>]*>[^<]*</video>',
                      video_button, html)
        if videos:
            html = install_controls(html, uuid4().hex, worker=active)
        self.access.validate_preview(html, MAX_PREVIEW_HTML)
        return html, videos

    def data_view_html(self, html, *, active=False, base=None):
        base = self.base if base is None else base
        html = re.sub(r'href="([^"]*)"', lambda match: 'href="' + base + '?target='
                      + quote(unescape(match[1]), safe='') + '"', html)
        if active:
            html = html.replace('<body>', '<body data-logistics-data-view="' + base + '">', 1)
            return worker_policy(html)
        return html


    def cancel_data_views(self):
        self.data_view_plan = None
        self.data_views_loading = False
        task = getattr(self, 'data_view_task', None)
        running = task is not None and not task.done()
        if running:
            task.cancel()
        self.data_view_task = None
        # Navigation/retirement replaces the document as well; terminate promptly
        # while an opening worker or an editor transition is still pending.
        if running:
            from ..dataview_script import STOP
            self.web.evaluate_javascript(STOP)


    async def render_data_views(self, plan, base, path):
        from .dataview import execute_views
        # Opening attempts may fail while this document remains visible. Its
        # publication token changes only after a replacement is ready.
        def valid():
            return self.valid() and self.base == base and self.path == path and not self.editing
        try:
            text = await asyncio.wait_for(execute_views(self.web, self.library, path, plan,
                valid=valid, marker=base), timeout=35)
            if text is None or not valid():
                return
            html, videos = await asyncio.to_thread(self.note_preview, text, path, base,
                                                  cancelled=lambda: not valid())
            if valid():
                await self.remember_position()
                if valid():
                    self.page_search.loading()
                    self.data_views_loading = False
                    set_inline_html(self.web, self.base, html)
                    self.clear_video_actions()
                    self.set_video_actions(videos)
        except OperationCancelled:
            return
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, asyncio.TimeoutError) as error:
            if valid():
                self.data_views_loading = False
                await self.document_error('Could not update data view',
                    str(error) or 'Execution exceeded 35 seconds.')


    async def remember_position(self):
        from commonUtils.ui.native.text_size import native_backend
        if self.path is None or self.editing or not native_backend(self.web).startswith(('toga_iOS.', 'toga_android.')):
            return
        path = self.path
        try:
            position = await asyncio.wait_for(self.web.evaluate_javascript('window.scrollY'), timeout=.25)
            if self.valid() and self.path == path and isinstance(position, (int, float)):
                self.positions[path] = max(0, int(position))
        except Exception:
            # A retired page has no position to retain. Reading still owns the
            # original note and no source content crosses this presentation path.
            return


    async def open_canvas(self, path, *, remember=True):
        if self.host.document_editor is None:
            return False
        return await self.open_embedded(path, self.host.document_editor, remember=remember)


    async def open_embedded(self, path, opener, *, remember=True):
        """One navigation/lifetime path for source editors and notebook canvases."""
        path = self.contained(path)
        self.epoch += 1
        epoch = self.epoch
        if not hasattr(self, 'page_loading'):
            self.page_loading = LibraryOpening(self)
        self.page_loading.start(path)
        try:
            pages = await self.breadcrumb_pages(path, lambda: not self.valid() or epoch != self.epoch)
            editor = await opener(self, path)
        except (OSError, ValueError, OperationCancelled) as error:
            if self.valid() and epoch == self.epoch:
                self.page_loading.finish()
                if not isinstance(error, OperationCancelled):
                    await self.document_error('Could not open document', error)
            return False
        finally:
            if epoch == self.epoch:
                self.page_loading.finish()
        if not self.valid() or epoch != self.epoch:
            editor.dispose()
            return False
        self.cancel_data_views()
        self.retire_editor()
        self.embedded = editor
        self.editing = True
        # Retain the reusable reader, but retire its old DOM and media when a
        # source editor, drawing or file preview replaces the Markdown page.
        set_inline_html(self.web, self.base, '<!doctype html><html><body></body></html>')
        self.clear_video_actions()
        self.path = self.selected_path = path
        self.folder_pages.update(pages)
        self.update_tree_selection()
        self.title.text = fill(PurePosixPath(path).name, width=28)
        self.speech.close()
        self.up_button.enabled = True
        if remember and (self.history_index < 0 or self.history[self.history_index] != path):
            del self.history[self.history_index + 1:]
            self.history.append(path)
            self.history_index = len(self.history) - 1
        self.article.clear()
        self.article.add(editor.view)
        self.edit.enabled = False
        self.back_button.enabled = self.history_index > 0
        self.forward_button.enabled = self.history_index < len(self.history) - 1
        self.notice.text = ''
        self.refresh_reader_actions()
        self.refresh_chrome()
        self.render_tree()
        self.sidebar.show_detail()
        self.host.render()
        await asyncio.to_thread(self.library.release_media, path,
                                active=lambda: self.valid() and self.epoch == epoch)
        return True


    async def open_editor(self, widget=None, **kwargs):
        if not self.valid() or self.path is None or not self.library.writable:
            return False
        if self.editing:
            return await self.open_note(self.path, remember=False)
        self.sidebar.show_detail()
        from .library_document import LibraryMarkdown
        path = self.path
        self.epoch += 1
        epoch = self.epoch
        if hasattr(self, 'page_loading'):
            self.page_loading.finish()
        opening = self.page_loading = LibraryOpening(self)
        opening.start(path)
        opening.status.text = 'Preparing for editing…'
        try:
            await self.remember_position()
            if not self.valid() or epoch != self.epoch or self.path != path:
                return False
            try:
                editor = await LibraryMarkdown.open(self, path)
            except (OSError, ValueError, UnicodeError, OperationCancelled) as error:
                if self.valid() and epoch == self.epoch:
                    if not isinstance(error, OperationCancelled):
                        await self.document_error('Could not edit document', error)
                return False
            if not self.valid() or epoch != self.epoch or self.path != path:
                editor.dispose()
                return False
            if editor.open_warning is not None:
                try:
                    await self.document_error('Formatted editing unavailable', editor.open_warning)
                except BaseException:
                    editor.dispose()
                    raise
                if not self.valid() or epoch != self.epoch or self.path != path:
                    editor.dispose()
                    return False
            self.cancel_data_views()
            self.clear_video_actions()
            self.embedded, self.editing = editor, True
            self.article.clear()
            self.article.add(editor.view)
            self.refresh_reader_actions()
            self.refresh_chrome()
            self.host.render()
            return True
        finally:
            opening.finish()


    async def open_text(self, path, *, remember=True):
        from .library_text import LibraryText
        return await self.open_embedded(path, LibraryText.open, remember=remember)

