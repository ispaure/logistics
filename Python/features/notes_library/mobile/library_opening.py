"""Mobile Notes document transitions and accepted reader publications."""
import asyncio
import posixpath
import re
from dataclasses import dataclass
from functools import partial
from html import unescape
from json import dumps
from pathlib import PurePosixPath
from time import perf_counter
from urllib.parse import parse_qs, quote, unquote, urlsplit
from uuid import uuid4
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.runtime.operations import OperationCancelled, check_cancelled
from commonUtils.ui.native.inline_html import set_inline_html
from ..notes import MAX_PREVIEW_HTML, MARKDOWN, document_kind
from ..dataview import ViewPlan, view_plan
from ..dataview_script import worker_policy
from .dataview import PageDataViews
from .inline_video import PAUSE_VIDEOS, PageVideos, install_controls, open_native_video, video_embed
from .library_panels import LibraryOpening


READER_BASE = 'https://markdown.invalid/vault/'
_DOM_MARKER = ("Array.from(document.childNodes)"
               ".find(node => node.nodeType === 8 && node.data.startsWith('logistics-note:'))?.data")


def _script_on_dom(marker, script):
    return f'if ({_DOM_MARKER} === {dumps("logistics-note:" + marker)}) {{ {script} }}'


@dataclass(frozen=True)
class _PreparedMarkdown:
    path: str
    base: str
    html: str
    videos: dict[str, str]
    plan: ViewPlan


@dataclass(eq=False)
class _ReaderPage:
    """An accepted note, retained across generated-content DOM replacements."""

    base: str
    views: PageDataViews
    fragment: str = ''
    videos: PageVideos | None = None


class LibraryDocuments:
    def __init__(self, browser):
        self.browser = browser
        self.epoch = 0
        self.path = self.embedded = None
        self._page = None
        self.editing = False
        self.positions = {}
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
        self.speech.button.on_press = browser.show_read_aloud

    def reading(self):
        return self.browser.valid() and self.path is not None and not self.editing

    @property
    def base(self):
        return self._page.base if self._page is not None else READER_BASE

    @property
    def data_views_loading(self):
        return self._page is not None and self._page.views.loading

    def _has_page(self, page):
        return page is not None and page is self._page and self.reading()

    def _has_dom(self, page, marker):
        return self._has_page(page) and self._load_marker == marker

    async def wait_readable(self, path, current):
        """Wait for the admitted DOM and generated content before mapping speech."""
        from commonUtils.ui.native.text_size import native_backend
        native = native_backend(self.web).startswith(('toga_iOS.', 'toga_android.'))
        deadline = self.browser.host.loop.time() + 10
        page = self._page
        while current() and self._has_page(page) and self.path == path:
            if (self._loaded or not native) and not page.views.loading:
                return True
            if self.browser.host.loop.time() >= deadline:
                return False
            await asyncio.sleep(.02)
        return False

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
        self._page = None
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
        self._clear_page_videos()
        if self._page is not None:
            self._page.views.close()
        self.speech.close()
        self.speech.button.enabled = False
        self.retire_editor()
        self.path = None
        self._page, self._load_marker = None, None
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
            if not editor.dirty:
                return True
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


    async def open_video_file(self, path, *, epoch=None):
        def current():
            return self.browser.valid() if epoch is None else self.accepts(epoch)

        async def pause():
            surfaces = [self.web]
            formatted = getattr(self.embedded, 'formatted', None)
            if formatted is not None:
                surfaces.append(formatted.view)
            for surface in surfaces:
                await surface.evaluate_javascript(PAUSE_VIDEOS)

        return await open_native_video(self.browser, path, pause=pause, close_speech=self.speech.close,
                                       current=current)


    async def open_note(self, path, *, epoch, remember=True, fragment="", resolve_link=False):
        started = perf_counter()
        if not await self.prepare_leave(epoch=epoch):
            return False
        if not resolve_link:
            kind = document_kind(path)
            if kind != 'markdown':
                return await self._open_other_document(path, kind, epoch=epoch, remember=remember)
        return await self._open_markdown_or_link(path, epoch=epoch, remember=remember,
                                                fragment=fragment, resolve_link=resolve_link, started=started)

    async def _open_other_document(self, path, kind, *, epoch, remember):
        from services.documents.file_preview import is_video_file
        if is_video_file(path):
            return await self.open_video_file(path, epoch=epoch)
        if kind is None:
            from .file_preview import LibraryFilePreview
            return await self.open_embedded(path, LibraryFilePreview.open, remember=remember, epoch=epoch)
        opener = self.open_text if kind == 'text' else self.open_canvas
        return await opener(path, remember=remember, epoch=epoch)

    async def _open_markdown_or_link(self, path, *, epoch, remember, fragment, resolve_link, started):
        self._media_open_epoch = epoch
        self._media_open_path, self._media_open_pending = path, True
        if self.browser.host.open_timing is not None:
            self._open_timing = dict(epoch=epoch, started=started, link=resolve_link,
                cached_folders_at_start=len(self.browser.library._link_folders), stages_ms={})
            self.mark_open_timing('started', epoch)
        current = self.path
        cancelled = lambda: not self.accepts(epoch)
        try:
            if not await self._begin_markdown_open(path, epoch=epoch, resolve_link=resolve_link):
                return False
            if not resolve_link:
                path = self.browser.contained(path)
                if PurePosixPath(path).suffix.lower() not in MARKDOWN:
                    raise ValueError("Choose a Markdown note.")
            stage = self._open_stage_reporter(epoch, resolve_link=resolve_link)
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
                kind = document_kind(path)
                if kind != 'markdown':
                    self.page_loading.finish()
                    return await self._open_other_document(path, kind, epoch=epoch, remember=remember)

            base = READER_BASE + uuid4().hex + '/'
            prepared = await asyncio.to_thread(self._prepare_markdown, path, base, data,
                                               cancelled=cancelled, stage=stage)
            if cancelled():
                return False
            self.mark_open_timing('prepared', epoch)
            self._adopt_markdown(prepared, pages, fragment=fragment, remember=remember, epoch=epoch)
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

    async def _begin_markdown_open(self, path, *, epoch, resolve_link):
        try:
            await asyncio.wait_for(self.browser.remember_position(), timeout=.25)
        except asyncio.TimeoutError:
            pass
        if not self.accepts(epoch):
            return False
        self.browser.sidebar.show_detail()
        self.browser.notice.text = ''
        self.page_loading.start(path, finding=resolve_link)
        self.speech.close()
        return True

    def _open_stage_reporter(self, epoch, *, resolve_link):
        def stage(message):
            def publish():
                if not self.accepts(epoch) or not self.page_loading.active:
                    return
                self.page_loading.status.text = message
                if resolve_link and message == 'Finding file…':
                    self.mark_open_timing('finding', epoch)
                elif resolve_link and message.startswith('Reading '):
                    self.mark_open_timing('found', epoch)
            self.browser.host.loop.call_soon_threadsafe(publish)
        return stage

    def _prepare_markdown(self, path, base, data, *, cancelled, stage):
        stage('Preparing Markdown preview…')
        plan = view_plan(data.decode("utf-8-sig"))
        active = bool(plan.scripts)
        text = plan.render() if active else plan.source
        html, videos = self.note_preview(text, path, base, active=active, cancelled=cancelled)
        return _PreparedMarkdown(path, base, html, videos, plan)

    def _adopt_markdown(self, prepared, pages, *, fragment, remember, epoch):
        # Native admission can still reject the styled page. Keep the current
        # editor and history until admission succeeds.
        self.publish_html(prepared.base, prepared.html)
        self._clear_page_videos()
        if self._page is not None:
            self._page.views.close()
        self.browser.cancel_links()
        self.retire_editor()
        self.article.clear()
        self.article.add(self.web)
        self.path = prepared.path
        plan = prepared.plan if prepared.plan.scripts else None
        views = PageDataViews(self.web, self.browser.library, plan)
        page = self._page = _ReaderPage(prepared.base, views, fragment)
        self._set_page_videos(page, prepared.videos)
        if self._open_timing is not None:
            self._open_timing['published_epoch'] = epoch
        self.page_search.loading()
        self.browser.edit.enabled = self.browser.library.writable
        self.speech.button.enabled = True
        self.browser.publish_document(prepared.path, pages, remember=remember)


    def follow_link(self, widget, url, **kwargs):
        page = self._page
        if not self._has_page(page) or self.web.parent is not self.article:
            return False
        base = page.base
        if url == base + '?drawer=files':
            self.browser.sidebar.show_sidebar()
            return False
        if url == base + '?drawer=links':
            async def show_links():
                if self._has_page(page):
                    await self.browser.show_links(toggle=False)
            self.browser.host.loop.create_task(show_links())
            return False
        parsed = urlsplit(url)
        if not parsed.scheme and not parsed.netloc:
            target = url
        elif url.split("?", 1)[0] == base:
            query = parse_qs(parsed.query)
            inline = 'inline-video' in query
            if inline or 'video' in query:
                key = query['inline-video' if inline else 'video'][0]
                if page.videos is not None:
                    page.videos.start(key, self.path, inline=inline)
                return False
            target = query.get("target", [""])[0]
        else:
            return False
        link = urlsplit(target)
        if not link.path and link.fragment:
            if page.views.loading:
                page.fragment = link.fragment
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
            if self._has_page(page):
                await self.browser.open_note(target, resolve_link=True)
        self.browser.host.loop.create_task(open_link())
        return False


    def scroll_fragment(self, fragment):
        self.web.evaluate_javascript(_script_on_dom(self._load_marker,
            "(function(){const h=document.getElementById("
            + dumps(unquote(fragment))
            + ");if(h)h.scrollIntoView();})()"))


    def page_loaded(self, widget=None, url=None, **kwargs):
        page = self._page
        if not self._has_page(page) or self._loaded:
            return
        base = page.base
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
        page = self._page
        try:
            result = await asyncio.wait_for(self.web.evaluate_javascript(
                "document.readyState === 'complete' && " + _DOM_MARKER
            ), timeout=2)
            if marker is not None and self._has_dom(page, marker) and result == 'logistics-note:' + marker:
                self.finish_page_load(base)
        except (OSError, RuntimeError, ValueError, TimeoutError):
            pass
        finally:
            if self._load_task is asyncio.current_task():
                self._load_task = None

    def finish_page_load(self, base):
        page = self._page
        if not self._has_page(page) or page.base != base or self._loaded:
            return
        self._loaded = True
        if (self._open_timing is not None and self._open_timing.get('published_epoch') == self.epoch
                and 'dom_ready' not in self._open_timing['stages_ms']):
            self.mark_open_timing('dom_ready', self.epoch)
        path, marker = self.path, self._load_marker
        page.views.start(self.browser.host.loop, lambda plan: self._render_data_view(page, plan, path, marker))
        from .notes_swipe import document_swipes
        self.web.evaluate_javascript(_script_on_dom(marker, document_swipes(page.base)))
        self.page_search.loaded(reveal=not bool(page.fragment))
        if page.fragment and not page.views.loading:
            fragment, page.fragment = page.fragment, ''
            self.scroll_fragment(fragment)
        elif not page.fragment and path in self.positions:
            self.web.evaluate_javascript(_script_on_dom(marker, f'window.scrollTo(0,{self.positions[path]})'))


    def _clear_page_videos(self):
        page = self._page
        if page is not None and page.videos is not None:
            page.videos.close()
            page.videos = None

    def _set_page_videos(self, page, videos):
        if videos:
            marker = self._load_marker
            page.videos = PageVideos(self.browser, self.web, self.speech, videos,
                current=lambda path: self._has_dom(page, marker) and self.path == path,
                in_dom=partial(_script_on_dom, marker))

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


    async def render_data_views(self, plan, base, path):
        page = self._page
        if self._has_page(page) and page.base == base and self.path == path:
            await self._render_data_view(page, plan, path, self._load_marker)

    async def _render_data_view(self, page, plan, path, marker):
        await page.views.render(plan, path, marker,
            current=lambda: self._has_dom(page, marker) and self.path == path,
            preview=partial(self.note_preview, path=path, base=page.base),
            remember_position=self.browser.remember_position,
            publish=partial(self._publish_data_view, page), show_error=self.document_error)

    def _publish_data_view(self, page, html, videos):
        self.page_search.loading()
        page.views.loading = False
        self.publish_html(page.base, html)
        self._clear_page_videos()
        self._set_page_videos(page, videos)

    async def remember_position(self):
        from commonUtils.ui.native.text_size import native_backend
        page = self._page
        if not self._has_page(page) or not native_backend(self.web).startswith(('toga_iOS.', 'toga_android.')):
            return
        path, marker = self.path, self._load_marker
        try:
            position = await asyncio.wait_for(self.web.evaluate_javascript('window.scrollY'), timeout=.25)
            if self._has_dom(page, marker) and self.path == path and isinstance(position, (int, float)):
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
        """Prepare and adopt a source editor, notebook canvas, or file preview."""
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
        self._adopt_embedded(path, editor, pages, remember=remember)
        await asyncio.to_thread(self.browser.library.release_media, path,
                                active=lambda: self.accepts(epoch))
        return True

    def _adopt_embedded(self, path, editor, pages, *, remember):
        self.browser.cancel_links()
        if self._page is not None:
            self._page.views.close()
        self.retire_editor()
        self.embedded = editor
        self.editing = True
        # Retain the reusable reader, but retire its old DOM and media when a
        # source editor, drawing or file preview replaces the Markdown page.
        self._clear_page_videos()
        self.blank_reader()
        self.path = path
        self.speech.close()
        self.article.clear()
        self.article.add(editor.view)
        self.browser.edit.enabled = False
        self.browser.publish_document(path, pages, remember=remember)


    async def open_editor(self, widget=None, **kwargs):
        if not self.browser.valid() or document_kind(self.path or '') != 'markdown' or not self.browser.library.writable:
            return False
        if self.editing:
            return await self.browser.open_note(self.path, remember=False)
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
            editor = await self._prepare_markdown_editor(path, epoch)
            if editor is None:
                return False
            self._adopt_markdown_editor(editor)
            return True
        finally:
            if epoch == self.epoch:
                opening.finish()

    async def _prepare_markdown_editor(self, path, epoch):
        from .library_document import LibraryMarkdown
        try:
            editor = await LibraryMarkdown.open(self.browser, path)
        except OperationCancelled:
            return None
        except (OSError, ValueError, UnicodeError) as error:
            if self.accepts(epoch):
                await self.document_error('Could not edit document', error)
            return None
        if not self.accepts(epoch):
            editor.dispose()
            return None
        if editor.open_warning is not None:
            try:
                await self.document_error('Formatted editing unavailable', editor.open_warning)
            except BaseException:
                editor.dispose()
                raise
            if not self.accepts(epoch):
                editor.dispose()
                return None
        return editor

    def _adopt_markdown_editor(self, editor):
        if self._page is not None:
            self._page.views.close()
        self._clear_page_videos()
        self.speech.close()
        self.cancel_page_load()
        self.page_search.loading()
        self.embedded, self.editing = editor, True
        self.article.clear()
        self.article.add(editor.view)
        self.browser.refresh_reader_actions()
        self.browser.refresh_chrome()
        self.browser.host.render()


    async def open_text(self, path, *, remember=True, epoch=None):
        from .library_text import LibraryText
        return await self.open_embedded(path, LibraryText.open, remember=remember, epoch=epoch)

