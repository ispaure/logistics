"""Private offline transfer UI, with bounded messages and retired callbacks."""
from commonUtils.search.policy import SEARCH_DEBOUNCE_MS
import asyncio
from functools import lru_cache
import json
from pathlib import Path
from time import monotonic
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import toga
from toga.platform import get_factory
from toga.style import Pack
from toga.style.pack import COLUMN

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
ACTIONS = frozenset(('approve', 'early', 'filter', 'previous', 'next', 'background', 'stop', 'scope', 'start-review', 'settings'))
RENDER_TIMEOUT = 15
JAVASCRIPT_TIMEOUT = 8
HEALTH_INTERVAL = 5


async def evaluate_bounded(web, script):
    # Native Android callbacks can re-enter the cooperative loop without a
    # current Task. wait() provides a deadline without a task-local timeout.
    result = asyncio.ensure_future(web.evaluate_javascript(script))
    try:
        done, _ = await asyncio.wait((result,), timeout=JAVASCRIPT_TIMEOUT)
        if not done:
            raise TimeoutError('Transfer renderer did not answer.')
        return result.result()
    finally:
        if not result.done():
            result.cancel()
            await asyncio.gather(result, return_exceptions=True)


@lru_cache(maxsize=1)
def surface_html():
    return ((ASSETS / 'surface.html').read_text()
            .replace('/*STYLE*/', (ASSETS / 'surface.css').read_text())
            .replace('/*SCRIPT*/', (ASSETS / 'surface.js').read_text().replace('SEARCH_DEBOUNCE_MS', str(SEARCH_DEBOUNCE_MS))))


class TransferSurface(toga.Box):
    def __init__(self, app, handler, *, visible=lambda: True):
        super().__init__(style=Pack(direction=COLUMN, flex=1))
        self.host, self.handler, self.visible = app, handler, visible
        self.closed, self.ready = False, False
        self.model, self.pending = {}, None
        self.revision = self.delivered_revision = 0
        self.send_task = None
        self.recovery_count = 0
        self.native_fallback = None
        self.last_progress = monotonic()
        self.last_health = self.last_progress
        self.watch_task = None
        self.actions = set()
        self.token = uuid4().hex
        self._credential_state = getattr(getattr(app, 'cloud_client', None), 'credential_state', None)
        if self._credential_state is not None:
            self._credential_state.protection_observers.add(self)
        self._focus_navigation = True
        self._transfer_surface = self
        self.dummy_backend = get_factory().WebView.__module__.startswith('toga_dummy.')
        self.web = None
        try:
            self.create_web()
        except Exception:
            self.recover_rendering()
        if not self.dummy_backend and self.native_fallback is None:
            self.watch_task = self.host.loop.create_task(self.watch_rendering())

    def create_web(self):
        if self.dummy_backend:
            view_type = toga.WebView
        else:
            from commonUtils.ui.native.private_webview import PrivateWebView
            view_type = PrivateWebView
        self.web = view_type(on_navigation_starting=self.navigate, on_webview_load=self.loaded, style=Pack(flex=1))
        self.add(self.web)
        from commonUtils.ui.native.inline_html import set_inline_html
        set_inline_html(self.web, 'https://logistics.invalid/transfer/', surface_html())

    async def watch_rendering(self):
        try:
            while not self.closed:
                await asyncio.sleep(1)
                if self.closed or self.native_fallback is not None:
                    return
                waiting = bool(self.model) and (not self.ready or self.pending is not None or self.send_task is not None)
                if not self.visible():
                    self.last_progress = monotonic()
                elif not waiting:
                    self.last_progress = monotonic()
                    if self.ready and monotonic() - self.last_health >= HEALTH_INTERVAL:
                        web = self.web
                        self.last_health = monotonic()
                        try:
                            healthy = await evaluate_bounded(web, '!!window.Transfer')
                        except Exception:
                            healthy = False
                        if not self.closed and web is self.web and not healthy:
                            self.ready = False
                            self.pending = self.model
                elif monotonic() - self.last_progress >= RENDER_TIMEOUT:
                    self.recover_rendering()
        except asyncio.CancelledError:
            pass
        finally:
            self.watch_task = None

    def retire_web(self):
        web, self.web = self.web, None
        if web is not None:
            if web.parent is self:
                self.remove(web)
            from services.documents.mobile_views import retire_webview
            retire_webview(web)

    def recover_rendering(self):
        """Replace this renderer once; never restart or cancel the transfer."""
        if self.closed or self.native_fallback is not None:
            return
        self.ready = False
        if self.send_task is not None:
            self.send_task.cancel()
            self.send_task = None
        self.retire_web()
        self.token = uuid4().hex
        self.pending = self.model
        self.last_progress = monotonic()
        self.recovery_count += 1
        from commonUtils.runtime.diagnostics import Severity, log
        log(Severity.WARNING, 'Transfer display recovery',
            'Replacing the web view.' if self.recovery_count == 1 else 'Using native transfer controls.')
        if self.recovery_count == 1:
            try:
                self.create_web()
                return
            except Exception:
                self.retire_web()
                self.recovery_count = 2
        from .native_fallback import NativeTransferFallback
        self.native_fallback = NativeTransferFallback(self)
        self.add(self.native_fallback)
        self.queue_send()

    @property
    def bridge(self):
        return 'logistics-transfer://' + self.token + '/'

    def navigate(self, widget, url, **kwargs):
        if self.closed or widget is not self.web or len(url) > 8192:
            return False
        parsed = urlsplit(url)
        if parsed.scheme != 'logistics-transfer' or parsed.netloc != self.token:
            return False
        action = parsed.path.lstrip('/')
        if action not in ACTIONS:
            return False
        try:
            args = {key: values[0] for key, values in parse_qs(parsed.query, max_num_fields=8).items()}
        except ValueError:
            return False
        task = self.host.loop.create_task(self.dispatch(action, args))
        self.actions.add(task)
        def completed(task):
            self.actions.discard(task)
            if not task.cancelled():
                task.exception()
        task.add_done_callback(completed)
        return False

    async def dispatch(self, action, args):
        if self.closed or not getattr(self.host, 'active_host', True) or action not in ACTIONS:
            return
        if action in ('approve', 'early', 'start-review'):
            if (self.pending is not None or self.delivered_revision != self.revision
                    or str(self.revision) != args.get('revision')):
                return
            if action == 'approve' and not self.model.get('can_confirm'):
                return
            if action == 'early' and not self.model.get('can_early'):
                return
        await self.handler(action, args)

    def update(self, model):
        if self.closed:
            return
        from services.appearance_palette import eink_enabled
        import sys
        device = 'This device'
        if sys.platform == 'ios':
            from rubicon.objc import ObjCClass
            device = 'iPad' if int(ObjCClass('UIDevice').currentDevice.userInterfaceIdiom) == 1 else 'iPhone'
        elif self.dummy_backend:
            device = 'iPad' if self.host.main_window.size.width >= 720 else 'iPhone'
        model = dict(model, device=device, eink=eink_enabled(),
                     font_size=int(getattr(self.host, 'preferences', None).values.get('font_size', 16)) if hasattr(self.host, 'preferences') else 16)
        model.pop('revision', None)
        previous = dict(self.model)
        previous.pop('revision', None)
        if model == previous:
            self.queue_send()
            return
        self.revision += 1
        self.model = dict(model, revision=self.revision)
        self.pending = self.model
        self.queue_send()

    def queue_send(self):
        if not self.closed and self.pending is not None and self.model and self.native_fallback is not None and self.visible():
            self.native_fallback.render(self.model)
            self.delivered_revision = self.revision
            self.pending = None
            self.ready = True
            return
        if not self.closed and self.ready and self.visible() and self.pending is not None and self.send_task is None:
            self.send_task = self.host.loop.create_task(self.flush())

    async def loaded(self, widget=None, **kwargs):
        if self.closed or widget is not self.web:
            return
        try:
            ready = await evaluate_bounded(widget, '!!window.Transfer')
            if not ready or self.closed or widget is not self.web:
                return
            await evaluate_bounded(widget, 'window.Transfer.start(' + json.dumps(self.bridge) + ')')
            if not self.closed and widget is self.web:
                self.ready = True
                self.last_progress = monotonic()
                self.queue_send()
        except Exception:
            # The visible-render deadline owns recovery, including a missing
            # finish callback or a JavaScript callback that never completes.
            if widget is self.web:
                self.ready = False

    async def flush(self):
        web = self.web
        try:
            while not self.closed and web is self.web and self.pending is not None and self.visible():
                model, self.pending = self.pending, None
                result = await evaluate_bounded(web, 'window.Transfer && window.Transfer.update(' + json.dumps(model) + ')')
                if self.closed or web is not self.web:
                    return
                if result:
                    self.delivered_revision = model['revision']
                    self.last_progress = monotonic()
                else:
                    self.pending = self.model
                    self.ready = False
                    return
                await asyncio.sleep(0)
        except (Exception, asyncio.CancelledError):
            if not self.closed and web is self.web:
                self.pending = self.model
                self.ready = False
        finally:
            if web is self.web:
                self.send_task = None

    def credentials_changed(self):
        if not self.closed:
            self.host.loop.call_soon_threadsafe(self.revoke)

    def revoke(self):
        if self.closed:
            return
        owner = getattr(self.host, '_transfer_controller', None)
        if owner is not None:
            owner.state.display_revoked = True
            owner.state.metrics = {}
            owner.state.endpoints = None
        self.dispose()
        self.add(toga.Label('Connection locked or changed.\nUse Back to return and unlock again.', style=Pack(margin=22)))

    def dispose(self):
        if self.closed:
            return
        self.closed = True
        if self._credential_state is not None:
            self._credential_state.protection_observers.discard(self)
        self.model, self.pending = {}, None
        self.token = ''
        self.handler = None
        if self.send_task is not None:
            self.send_task.cancel()
        if self.watch_task is not None:
            self.watch_task.cancel()
        # An open native confirmation can return late; its host checks closed.
        self.retire_web()
        if self.native_fallback is not None:
            self.native_fallback.clear_private_content()
            self.remove(self.native_fallback)
            self.native_fallback = None
        self._credential_state = None
        self.visible = lambda: False
        self.host = None
