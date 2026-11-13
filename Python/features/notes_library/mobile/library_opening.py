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
from threading import Event
from time import perf_counter
from urllib.parse import parse_qs, quote, unquote, urlsplit
from uuid import uuid4
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.runtime.operations import OperationCancelled, check_cancelled
from commonUtils.ui.native.inline_html import set_inline_html
from ..notes import MAX_PREVIEW_HTML, MARKDOWN, document_kind
from ..dataview import view_plan
from ..dataview_script import worker_policy
from .library_panels import LibraryOpening
from .inline_video import install_controls, video_embed


PREPARING_VIDEO = 'Preparing video…'
READER_BASE = 'https://markdown.invalid/vault/'


class LibraryDocuments:
    def __init__(self, browser):
        self.browser = browser
        self.epoch = 0
        self.path = self.embedded = None
        self.base = READER_BASE
        self.editing = False
        self.positions = {}
        self.pending_fragment = ''
        self.data_view_plan = self.data_view_task = None
        self.data_views_loading = False
        self._page_videos = {}
        self._video_opening = self._inline_audio = None
        self._open_timing = None
        self._media_open_epoch = self._media_open_path = None
        self._media_open_pending = False
        self._load_marker = self._load_task = None
        self._loaded = False

        self.web = browser.access.webview(max_bytes=MAX_PREVIEW_HTML,
            on_navigation_starting=self.follow_link, on_webview_load=self.page_loaded,
            style=Pack(flex=1))
        browser.host.presentation.bind_font(self.web, 'markdown', web=True)
        self.article = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.page_loading = LibraryOpening(self.article, self.cancel_open)
        from commonUtils.ui.native.markdown_search import MarkdownPageSearch
        self.page_search = MarkdownPageSearch(self.web, self.article, valid=self.reading)
        self.speech = browser.host.speech(self.web, self.article,
            document_title=lambda: browser.access.title(self.path),
            privacy_gate=browser.access.speech_gate, valid=self.reading)
        self.speech.button.enabled = False

    def reading(self):
        return self.browser.valid() and self.path is not None and not self.editing

    def accepts(self, epoch):
        return self.browser.valid() and self.epoch == epoch

    def cancel_open(self, widget=None, **kwargs):
        self.epoch += 1
        self.page_loading.finish()
        return self.epoch

    def publish_html(self, base, html):
        marker = uuid4().hex
        html += '<!--logistics-note:' + marker + '-->'
        self.browser.access.validate_preview(html, MAX_PREVIEW_HTML)
        set_inline_html(self.web, base, html)
        self.cancel_page_load()
        self._load_marker = marker
        self._loaded = False

    def cancel_page_load(self):
        if self._load_task is not None:
            self._load_task.cancel()
            self._load_task = None

    def blank_reader(self):
        self.cancel_page_load()
        self.base = READER_BASE
        self._load_marker = None
        self._loaded = False
        self.page_search.loading()
        self.page_search.hide()
        self.page_search.query.value = ''
        set_inline_html(self.web, self.base, '<!doctype html><html><body></body></html>')

    def clear(self):
        path = self.path
        self.retire_page()
        self.blank_reader()
        return path

    def retire_page(self):
        self.cancel_open()
        self.cancel_page_load()
        self.browser.cancel_links()
        self.clear_video_actions()
        self.cancel_data_views()
        self.speech.close()
        self.speech.button.enabled = False
        self.retire_editor()
        self.path = None
        self.base, self._load_marker = READER_BASE, None
        self.pending_fragment = ''
        self._open_timing = None

    async def release_media(self, path):
        if path is not None:
            await asyncio.to_thread(self.browser.library.discard_media, path,
                active=lambda: path != self.path and not (self._media_open_pending and path == self._media_open_path))

    def dispose(self):
        self.retire_page()
        self.page_search.dispose()
        self.positions.clear()
        from services.documents.mobile_views import retire_webview
        retire_webview(self.web)

    async def document_error(self, title, error):
        if self.browser.valid():
            await self.browser.host.show_error(title, str(error))

    async def prepare_leave(self, *, save=False, confirm=None, epoch=None):
        browser = self.browser
        epoch = self.epoch if epoch is None else epoch
        editor = self.embedded
        def current():
            return self.accepts(epoch) and self.embedded is editor

        if editor is None:
            return current()
        if editor.busy and getattr(editor, 'kind', None) != 'notebook':
            browser.notice.text = 'Wait for the document operation to finish.'
            return False
        try:
            await editor.flush()
            if not current():
                return False
            if editor.busy:
                browser.notice.text = 'Wait for the document operation to finish.'
                return False
            if editor.dirty:
                if save or getattr(editor, 'autosave_on_leave', False):
                    return await editor.save() and current()
                confirm = confirm or browser.host.confirm
                if confirm is None:
                    return False
                choice = await confirm()
                if not current():
                    return False
                if choice == 'save':
                    return await editor.save() and current()
                return choice == 'discard'
            return True
        except (OSError, ValueError) as error:
            if current():
                browser.notice.text = str(error)
            return False


    def retire_editor(self):
        if self.embedded is not None:
            formatted = getattr(self.embedded, 'formatted', None)
            if formatted is not None and self.path is not None:
                self.positions[self.path] = formatted.scroll_top
            self.embedded.dispose()
            self.embedded = None
        self.editing = False
        if self.browser.session is not None:
            self.browser.session.dirty = False


    def mark_open_timing(self, stage, epoch):
        timing = self._open_timing
        if timing is not None and timing['epoch'] == epoch:
            timing['stages_ms'][stage] = round((perf_counter() - timing['started']) * 1000, 2)
            self.browser.host.open_timing({key: value for key, value in timing.items() if key != 'started'})


    async def open_video_file(self, path, *, page=None, epoch=None):
        def current():
            return self.browser.valid() and (epoch is None or self.accepts(epoch)) and (
                page is None or self.reading() and self.base == page)

        path = self.browser.contained(path)
        if self.browser.host.open_resource is None:
            self.browser.notice.text = 'Video playback is unavailable in this host.'
            return False
        try:
            if not current():
                return False
            # Pause page media before handing audio to the native player. Keep
            # the page and provider alive so returning from playback is immediate.
            surfaces = [self.web]
            formatted = getattr(self.embedded, 'formatted', None)
            if formatted is not None:
                surfaces.append(formatted.view)
            for surface in surfaces:
                await surface.evaluate_javascript("document.querySelectorAll('video').forEach(video => video.pause())")
            if not current():
                return False
            self.speech.close()
            if page is not None:
                return bool(await self.browser.host.open_resource(self.browser.provider, path, fullscreen=True))
            return bool(await self.browser.host.open_resource(self.browser.provider, path))
        except (OSError, ValueError, PermissionError) as error:
            if current():
                self.browser.notice.text = str(error)
            return False


    async def open_note(self, path, *, epoch, remember=True, fragment="", resolve_link=False):
        started = perf_counter()
        if not await self.prepare_leave(epoch=epoch):
            return False
        from services.documents.file_preview import is_video_file
        if not resolve_link and is_video_file(path):
            return await self.open_video_file(path, epoch=epoch)
        if not resolve_link and document_kind(path) is None:
            from .file_preview import LibraryFilePreview
            return await self.open_embedded(path, LibraryFilePreview.open, remember=remember, epoch=epoch)
        if not resolve_link and document_kind(path) == 'text':
            return await self.open_text(path, remember=remember, epoch=epoch)
        if not resolve_link and PurePosixPath(path).suffix.lower() == '.rmdoc':
            return await self.open_canvas(path, remember=remember, epoch=epoch)
        self._media_open_epoch = epoch
        self._media_open_path, self._media_open_pending = path, True
        if self.browser.host.open_timing is not None:
            self._open_timing = dict(epoch=epoch, started=started, link=resolve_link,
                cached_folders_at_start=len(self.browser.library._link_folders), stages_ms={})
            self.mark_open_timing('started', epoch)
        current = self.path
        cancelled = lambda: not self.accepts(epoch)
        try:
            try:
                await asyncio.wait_for(self.browser.remember_position(), timeout=.25)
            except asyncio.TimeoutError:
                pass
            if cancelled():
                return False
            self.browser.sidebar.show_detail()
            self.browser.notice.text = ''
            self.page_loading.start(path, finding=resolve_link)
            self.speech.close()
            if not resolve_link:
                path = self.browser.contained(path)
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
                self.browser.host.loop.call_soon_threadsafe(publish)
            path, found_fragment, data = await asyncio.to_thread(self.browser.library.load_note, path,
                current=current, resolve_link=resolve_link, cancelled=cancelled, stage=stage)
            pages = await self.browser.breadcrumb_pages(path, cancelled)
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
                        return await self.open_video_file(path, epoch=epoch)
                    if document_kind(path) is None:
                        from .file_preview import LibraryFilePreview
                        return await self.open_embedded(path, LibraryFilePreview.open, remember=remember, epoch=epoch)
                    opener = self.open_text if document_kind(path) == 'text' else self.open_canvas
                    return await opener(path, remember=remember, epoch=epoch)

            base = READER_BASE + uuid4().hex + '/'
            def read():
                stage('Preparing Markdown preview…')
                plan = view_plan(data.decode("utf-8-sig"))
                html, videos = self.note_preview(plan.render() if plan.scripts else plan.source,
                    path, base, active=bool(plan.scripts), cancelled=cancelled)
                return html, videos, plan

            html, videos, plan = await asyncio.to_thread(read)
            if cancelled():
                return False
            self.mark_open_timing('prepared', epoch)
            # Native admission can still reject the styled page. Do not retire
            # the current editor or advance history until it has succeeded.
            self.publish_html(base, html)
            self.clear_video_actions()
            self.cancel_data_views()
            self.browser.cancel_links()
            self.retire_editor()
            self.article.clear()
            self.article.add(self.web)
            self.path = path
            self.base = base
            self.set_video_actions(videos)
            if self._open_timing is not None:
                self._open_timing['published_epoch'] = epoch
            self.data_view_plan = plan if plan.scripts else None
            self.data_views_loading = bool(plan.scripts)
            self.pending_fragment = fragment
            self.page_search.loading()
            self.browser.edit.enabled = self.browser.library.writable
            self.speech.button.enabled = True
            self.browser.publish_document(path, pages, remember=remember)
            self.mark_open_timing('published', epoch)
            return True
        except OperationCancelled:
            return False
        except (OSError, UnicodeError, ValueError) as error:
            if not cancelled():
                self.page_loading.finish()
                await self.document_error('Could not open document', error)
            return False
        finally:
            if self._media_open_epoch == epoch:
                self._media_open_pending = False
                await asyncio.to_thread(self.browser.library.release_media, self.path,
                    active=lambda: self.accepts(epoch))
            await self.release_media(path)
            if epoch == self.epoch:
                self.page_loading.finish()


    def follow_link(self, widget, url, **kwargs):
        if not self.reading() or self.web.parent is not self.article:
            return False
        base = self.base
        if url == self.base + '?drawer=files':
            self.browser.sidebar.show_sidebar()
            return False
        if url == self.base + '?drawer=links':
            async def show_links():
                if self.reading() and self.base == base:
                    await self.browser.show_links(toggle=False)
            self.browser.host.loop.create_task(show_links())
            return False
        parsed = urlsplit(url)
        if not parsed.scheme and not parsed.netloc:
            target = url
        elif url.split("?", 1)[0] == self.base:
            query = parse_qs(parsed.query)
            inline = 'inline-video' in query
            if inline or 'video' in query:
                key = query['inline-video' if inline else 'video'][0]
                self.start_embedded_video(key, inline=inline)
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
            self.browser.contained(
                posixpath.normpath(
                    posixpath.join(posixpath.dirname(self.path), unquote(link.path))
                )
            )
        except ValueError:
            return False
        async def open_link():
            if self.reading() and self.base == base:
                await self.browser.open_note(target, resolve_link=True)
        self.browser.host.loop.create_task(open_link())
        return False


    def scroll_fragment(self, fragment):
        import json

        self.web.evaluate_javascript(
            "(function(){const h=document.getElementById("
            + json.dumps(unquote(fragment))
            + ");if(h)h.scrollIntoView();})()"
        )


    def page_loaded(self, widget=None, url=None, **kwargs):
        if not self.reading() or self._loaded:
            return
        base = self.base
        if url is not None and url.replace('app-document:', 'https:', 1) != base:
            return
        from commonUtils.ui.native.text_size import native_backend
        if native_backend(self.web).startswith(('toga_iOS.', 'toga_android.')):
            # Native callbacks omit the URL. Match the ready DOM against the
            # current publication, including the Android disk-backed fallback.
            self.cancel_page_load()
            self._load_task = self.browser.host.loop.create_task(self.verify_page_load(base, self._load_marker))
            return
        self.finish_page_load(base)

    async def verify_page_load(self, base, marker):
        try:
            result = await asyncio.wait_for(self.web.evaluate_javascript(
                "document.readyState === 'complete' && Array.from(document.childNodes)"
                ".find(node => node.nodeType === 8 && node.data.startsWith('logistics-note:'))?.data"
            ), timeout=2)
            if marker is not None and result == 'logistics-note:' + marker and self._load_marker == marker:
                self.finish_page_load(base)
        except (OSError, RuntimeError, ValueError, TimeoutError):
            pass
        finally:
            if self._load_task is asyncio.current_task():
                self._load_task = None

    def finish_page_load(self, base):
        if not self.reading() or self.base != base or self._loaded:
            return
        self._loaded = True
        if (self._open_timing is not None and self._open_timing.get('published_epoch') == self.epoch
                and 'dom_ready' not in self._open_timing['stages_ms']):
            self.mark_open_timing('dom_ready', self.epoch)
        plan = getattr(self, 'data_view_plan', None)
        if plan is not None:
            self.data_view_plan = None
            self.data_view_task = self.browser.host.loop.create_task(self.render_data_views(plan, self.base, self.path))
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
            self._video_opening = None
            if self.browser.notice.text == PREPARING_VIDEO:
                self.browser.notice.text = ''
        audio = getattr(self, '_inline_audio', None)
        if audio is not None:
            self.pause_inline_videos()
            audio.unregister(self)
            self._inline_audio = None
        self._page_videos.clear()

    def set_video_actions(self, videos):
        self._page_videos = videos
        if videos:
            self._inline_audio = self.browser.host.audio_output()
            if self._inline_audio is not None:
                self._inline_audio.register(self, self.pause_inline_videos)

    def pause_inline_videos(self):
        if getattr(self, '_inline_audio', None) is not None:
            self.web.evaluate_javascript("document.querySelectorAll('.note-video video').forEach(video => video.pause())")

    def start_embedded_video(self, key, *, inline):
        videos = self._page_videos
        if key not in videos or self.editing or (
                self._video_opening is not None and not self._video_opening.done()):
            return
        audio = getattr(self, '_inline_audio', None)
        if inline:
            if audio is None or not audio.interactive():
                return
            self.speech.close()
            if not audio.request_play():
                return
        self._video_opening = self.browser.host.loop.create_task(
            self.play_embedded_video(key, videos[key], self.path, self.base, videos, audio if inline else None))

    async def play_embedded_video(self, key, target, document, base, videos, audio):
        def current():
            return (self.browser.valid() and not self.editing and self.path == document
                    and self.base == base and self._page_videos is videos and key in videos)

        def cancelled():
            return not current() or stopped.is_set()

        stopped = Event()
        self.browser.notice.text = PREPARING_VIDEO
        try:
            if audio is None:
                path, _ = await asyncio.to_thread(self.browser.library.link, document, target, cancelled=cancelled)
                return current() and await self.open_video_file(path, page=base)
            url = await asyncio.to_thread(self.browser.library.open_embedded_video, document, target, cancelled=cancelled)
            if not current() or not audio.interactive() or not audio.permitted():
                return False
            if url is None:
                raise ValueError('Video unavailable.')
            await self.web.evaluate_javascript('window.logisticsPlayVideo?.(' + dumps(key) + ',' + dumps(url) + ')')
            return True
        except OperationCancelled:
            return False
        except (OSError, RuntimeError, ValueError):
            if current():
                self.browser.notice.text = 'Video unavailable.'
            return False
        finally:
            stopped.set()
            if current() and self.browser.notice.text == PREPARING_VIDEO:
                self.browser.notice.text = ''

    def note_preview(self, text, path, base, *, active=False, cancelled=lambda: False):
        from commonUtils.ui.native.markdown_preview import VideoPlaceholder
        from services.documents.markdown_media import video_reference

        videos = {}
        images = self.browser.library.image_source(path, cancelled=cancelled, batch=True)

        def media(target):
            check_cancelled(cancelled)
            if not video_reference(target):
                return images(target)
            key = uuid4().hex
            videos[key] = target
            return 'video/mp4', VideoPlaceholder(key)

        html = self.browser.host.preview(text, image_source=media)
        html = self.data_view_html(html, active=active, base=base)
        def video_button(match):
            key = match[1]
            filename = PurePosixPath(unquote(urlsplit(videos[key]).path)).name
            return video_embed(match[0], base, key, filename)

        html = re.sub(r'<video controls\b[^>]*\bdata-video-key="([0-9a-f]+)"[^>]*>[^<]*</video>',
                      video_button, html)
        if videos:
            html = install_controls(html, uuid4().hex, worker=active)
        self.browser.access.validate_preview(html, MAX_PREVIEW_HTML)
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
            return self.browser.valid() and self.base == base and self.path == path and not self.editing
        try:
            text = await asyncio.wait_for(execute_views(self.web, self.browser.library, path, plan,
                valid=valid, marker=base), timeout=35)
            if text is None or not valid():
                return
            html, videos = await asyncio.to_thread(self.note_preview, text, path, base,
                                                  cancelled=lambda: not valid())
            if valid():
                await self.browser.remember_position()
                if valid():
                    self.page_search.loading()
                    self.data_views_loading = False
                    self.publish_html(base, html)
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
        path, base = self.path, self.base
        try:
            position = await asyncio.wait_for(self.web.evaluate_javascript('window.scrollY'), timeout=.25)
            if self.reading() and self.base == base and isinstance(position, (int, float)):
                self.positions[path] = max(0, int(position))
        except Exception:
            # A retired page has no position to retain. Reading still owns the
            # original note and no source content crosses this presentation path.
            return


    async def open_canvas(self, path, *, remember=True, epoch=None):
        if self.browser.host.document_editor is None:
            return False
        return await self.open_embedded(path, self.browser.host.document_editor, remember=remember, epoch=epoch)


    async def open_embedded(self, path, opener, *, remember=True, epoch=None):
        """One navigation/lifetime path for source editors and notebook canvases."""
        epoch = self.cancel_open() if epoch is None else epoch
        if not self.accepts(epoch):
            return False
        try:
            path = self.browser.contained(path)
            self.page_loading.start(path)
            pages = await self.browser.breadcrumb_pages(path, lambda: not self.accepts(epoch))
            if not self.accepts(epoch):
                return False
            editor = await opener(self.browser, path)
        except (OSError, ValueError, OperationCancelled) as error:
            if self.accepts(epoch):
                self.page_loading.finish()
                if not isinstance(error, OperationCancelled):
                    await self.document_error('Could not open document', error)
            return False
        finally:
            if epoch == self.epoch:
                self.page_loading.finish()
        if not self.accepts(epoch):
            editor.dispose()
            return False
        self.browser.cancel_links()
        self.cancel_data_views()
        self.retire_editor()
        self.embedded = editor
        self.editing = True
        # Retain the reusable reader, but retire its old DOM and media when a
        # source editor, drawing or file preview replaces the Markdown page.
        self.clear_video_actions()
        self.pending_fragment = ''
        self.blank_reader()
        self.path = path
        self.speech.close()
        self.article.clear()
        self.article.add(editor.view)
        self.browser.edit.enabled = False
        self.browser.publish_document(path, pages, remember=remember)
        await asyncio.to_thread(self.browser.library.release_media, path,
                                active=lambda: self.accepts(epoch))
        return True


    async def open_editor(self, widget=None, **kwargs):
        if not self.browser.valid() or document_kind(self.path or '') != 'markdown' or not self.browser.library.writable:
            return False
        if self.editing:
            return await self.browser.open_note(self.path, remember=False)
        from .library_document import LibraryMarkdown
        path = self.path
        epoch = self.cancel_open()
        self.browser.sidebar.show_detail()
        opening = self.page_loading
        opening.start(path)
        opening.status.text = 'Preparing for editing…'
        try:
            await self.browser.remember_position()
            if not self.accepts(epoch):
                return False
            try:
                editor = await LibraryMarkdown.open(self.browser, path)
            except (OSError, ValueError, UnicodeError, OperationCancelled) as error:
                if self.accepts(epoch):
                    if not isinstance(error, OperationCancelled):
                        await self.document_error('Could not edit document', error)
                return False
            if not self.accepts(epoch):
                editor.dispose()
                return False
            if editor.open_warning is not None:
                try:
                    await self.document_error('Formatted editing unavailable', editor.open_warning)
                except BaseException:
                    editor.dispose()
                    raise
                if not self.accepts(epoch):
                    editor.dispose()
                    return False
            self.cancel_data_views()
            self.clear_video_actions()
            self.speech.close()
            self.cancel_page_load()
            self.page_search.loading()
            self.embedded, self.editing = editor, True
            self.article.clear()
            self.article.add(editor.view)
            self.browser.refresh_reader_actions()
            self.browser.refresh_chrome()
            self.browser.host.render()
            return True
        finally:
            if epoch == self.epoch:
                opening.finish()


    async def open_text(self, path, *, remember=True, epoch=None):
        from .library_text import LibraryText
        return await self.open_embedded(path, LibraryText.open, remember=remember, epoch=epoch)

