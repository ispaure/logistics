"""Private offline transfer UI, with bounded messages and retired callbacks."""
from commonUtils.search.policy import SEARCH_DEBOUNCE_MS
import asyncio
from functools import lru_cache
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import toga
from toga.platform import get_factory
from toga.style import Pack
from toga.style.pack import COLUMN

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
ACTIONS = frozenset(('approve', 'early', 'filter', 'previous', 'next', 'background', 'stop', 'scope', 'start-review', 'settings'))


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
        self.actions = set()
        self.token = uuid4().hex
        self._credential_state = getattr(getattr(app, 'cloud_client', None), 'credential_state', None)
        if self._credential_state is not None:
            self._credential_state.protection_observers.add(self)
        self._focus_navigation = True
        self._transfer_surface = self
        factory = get_factory().WebView.__module__
        if factory.startswith('toga_dummy.'):
            view_type = toga.WebView
        else:
            from commonUtils.ui.native.private_webview import PrivateWebView
            view_type = PrivateWebView
        self.web = view_type(on_navigation_starting=self.navigate, on_webview_load=self.loaded, style=Pack(flex=1))
        self.add(self.web)
        from commonUtils.ui.native.inline_html import set_inline_html
        set_inline_html(self.web, 'https://logistics.invalid/transfer/', surface_html())

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
        from mobile.palette import eink_enabled
        import sys
        device = 'This device'
        if sys.platform == 'ios':
            from rubicon.objc import ObjCClass
            device = 'iPad' if int(ObjCClass('UIDevice').currentDevice.userInterfaceIdiom) == 1 else 'iPhone'
        elif type(self.web._impl).__module__.startswith('toga_dummy.'):
            device = 'iPad' if self.host.main_window.size.width >= 720 else 'iPhone'
        model = dict(model, device=device, eink=eink_enabled(),
                     font_size=int(getattr(self.host, 'preferences', None).values.get('font_size', 16)) if hasattr(self.host, 'preferences') else 16)
        model.pop('revision', None)
        previous = dict(self.model)
        previous.pop('revision', None)
        if model == previous:
            return
        self.revision += 1
        self.model = dict(model, revision=self.revision)
        self.pending = self.model
        self.queue_send()

    def queue_send(self):
        if not self.closed and self.ready and self.visible() and self.pending is not None and self.send_task is None:
            self.send_task = self.host.loop.create_task(self.flush())

    async def loaded(self, widget=None, **kwargs):
        if self.closed or widget is not self.web:
            return
        ready = await self.web.evaluate_javascript('!!window.Transfer')
        if not ready or self.closed:
            return
        await self.web.evaluate_javascript('window.Transfer.start(' + json.dumps(self.bridge) + ')')
        if not self.closed:
            self.ready = True
            self.queue_send()

    async def flush(self):
        try:
            while not self.closed and self.pending is not None and self.visible():
                model, self.pending = self.pending, None
                result = await self.web.evaluate_javascript('window.Transfer && window.Transfer.update(' + json.dumps(model) + ')')
                if self.closed:
                    return
                if result:
                    self.delivered_revision = model['revision']
                else:
                    self.pending = self.model
                    self.ready = False
                    return
                await asyncio.sleep(0)
        except (Exception, asyncio.CancelledError):
            if not self.closed:
                self.pending = self.model
                self.ready = False
        finally:
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
        # An open native confirmation can return late; its host checks closed.
        from services.documents.mobile_views import retire_webview
        retire_webview(self.web)
        self._credential_state = None
        self.visible = lambda: False
        self.host = None
