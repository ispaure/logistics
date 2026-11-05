"""Bind an attached notebook before its first HTML; never take over a live stroke."""
import asyncio
import json
from weakref import ref
from uuid import uuid4
from commonUtils.ui.native.text_size import native_backend


class NativePencilFeed:
    owns_native_transport = True

    def __init__(self, web, window, view_id, window_id=None):
        self.web, self.window, self.view_id = web, window, view_id
        self.window_id = window_id or uuid4().hex
        self.closed = False
        self.reporter = None

    @property
    def enabled(self):
        return not self.closed and bool(self.window.notebookWebViewEnabled(self.web._impl.native))

    @property
    def pending(self):
        if self.closed:
            return False
        from commonUtils.ui.native.keyboard import native_value
        binding = native_value(self.window.notebookBindings.objectForKey(self.web._impl.native))
        return binding is not None and (bool(native_value(binding.pending))
            or int(native_value(binding.packets.count)) > 0
            or native_value(binding.touch) is not None)

    def start_reporting(self, loop, output):
        if self.reporter is not None or self.closed:
            return False
        reporter = NativePencilReporter.__new__(NativePencilReporter)
        self.reporter = reporter
        try:
            reporter.__init__(self, loop, output)
            return True
        except Exception:
            try:
                reporter.close()
            except Exception:
                pass
            self.reporter = None
            return False

    def native_snapshot(self):
        from commonUtils.ui.native.keyboard import native_value
        from rubicon.objc import py_from_ns
        value = py_from_ns(native_value(self.window.notebookPencilSnapshot))
        producer = value.get('native_producer') if isinstance(value, dict) else None
        if type(producer) not in (bool, int) or producer != 1:
            raise ValueError('Native producer counters unavailable')
        return value

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.window.unbindNotebookWebView(self.web._impl.native)
        finally:
            try:
                if self.reporter is not None:
                    self.reporter.close()
            except Exception:
                pass  # Optional diagnostics must not block input retirement.
            finally:
                self.reporter = None
                self.web = self.window = None


def attach(web, *, window=None, window_owner=None, constant_pressure=False):
    """Must run after native mounting, before initial set_inline_html.

    Event pressure is the default. Explicit constant mode is reserved for an
    owner-confirmed non-pressure device; it is never inferred from iPad models.
    Unavailable compiled windows retain ordinary DOM input.
    An owning host may supply its window before view attachment; native event
    admission still requires the actual touch.window and descendant WK target.
    """
    if type(constant_pressure) is not bool:
        raise TypeError('Constant pressure choice must be explicit')
    if not native_backend(web).startswith('toga_iOS.'):
        return None
    from commonUtils.ui.native.keyboard import native_value
    from rubicon.objc import ObjCClass
    try:
        window = window if window is not None else native_value(web._impl.native.window)
        if window is None or not window.isKindOfClass(ObjCClass('LogisticsNotebookInputWindow')):
            return None
        view_id = uuid4().hex
        if not window.bindNotebookWebView(web._impl.native, forceMode=int(constant_pressure), viewID=view_id):
            return None
        window_id = getattr(window_owner, '_notebook_native_trace_id', None)
        if not isinstance(window_id, str) or len(window_id) != 32 or any(c not in '0123456789abcdef' for c in window_id):
            window_id = uuid4().hex
            if window_owner is not None:
                window_owner._notebook_native_trace_id = window_id
        return NativePencilFeed(web, window, view_id, window_id)
    except (AttributeError, NameError):
        return None


_METRICS = frozenset(('raw_begin', 'raw_move', 'raw_end', 'raw_cancel', 'admitted_begin',
    'submitted', 'completed', 'timeout', 'overflow', 'retired', 'delivery_error', 'capture_error'))


class NativePencilReporter:
    """Low-frequency collector receipt, never a native event/gesture callback.

    Native counters cover the owned window; DOM counters cover this canvas.
    We deliberately leave legacy pair_stable false for those different scopes.
    """
    def __init__(self, feed, loop, output):
        self.feed = ref(feed)
        self.loop, self.output = loop, output
        self.observer_id = uuid4().hex
        self.view_id, self.window_id = feed.view_id, feed.window_id
        self.closed = False
        self.counts = {}
        self.baseline_counts = None
        self.window_counts_before_dom_query = None
        self.dom = self.dom_native_counts = None
        self.query = self.task = self.timer = None
        self._query_consumer_added = False
        self.write_report()  # Fresh lifetime immediately replaces stale evidence.
        self.timer = self.loop.call_later(3, self.tick)

    def snapshot(self):
        feed = self.feed()
        value = {}
        try:
            if feed is not None and feed.window is not None:
                value = feed.native_snapshot()
        except Exception:
            pass
        raw = value.get('counts', {})
        self.counts = {key: count for key, count in raw.items()
                       if key in _METRICS and type(count) is int and 0 <= count <= 9007199254740991} if isinstance(raw, dict) else {}
        if self.baseline_counts is None and value:
            self.baseline_counts = dict(self.counts)
        counters = {}
        for key, maximum in (('bindings', 16), ('queued_packets', 2048), ('queued_samples', 131072), ('inflight', 16)):
            number = value.get(key)
            if type(number) is int and 0 <= number <= maximum:
                counters[key] = number
        return dict(observer_id=self.observer_id, view_id=self.view_id, window_id=self.window_id,
                    diagnostic_only=True, native_producer=True, native_available=bool(value),
                    scope='owned-window aggregate; DOM is current canvas', counts=dict(self.counts),
                    baseline_counts=self.baseline_counts, window_counts_before_dom_query=self.window_counts_before_dom_query,
                    pairing='separate-scopes', dom_view_matches=self.dom is not None and self.dom.get('view_id') == self.view_id,
                    **counters)

    def write_report(self):
        # Reuse the existing bounded private collector writer/architecture owner.
        # No gesture construction, base close, contact-path flush or new IO owner.
        from .ios_input import PencilInputTrace
        PencilInputTrace.write_report(self)

    def _consume_query(self):
        if self.query is not None and not self.query.done() and not self._query_consumer_added:
            from .ios_input import _consume_trace_result
            self.query.add_done_callback(_consume_trace_result)
            self._query_consumer_added = True

    def tick(self):
        self.timer = None
        if self.closed:
            return
        feed = self.feed()
        if feed is None or feed.closed:
            self.close()
            return
        if self.task is not None and not self.task.done():
            return
        if self.query is not None and not self.query.done():
            # Native counters stay fresh, but never overlap a hung DOM request.
            self.write_report()
            self.timer = self.loop.call_later(3, self.tick)
            return
        self.task = self.loop.create_task(self.poll())

    async def poll(self):
        try:
            feed = self.feed()
            if self.closed:
                return
            if feed is None or feed.closed:
                self.close()
                return
            self.snapshot()
            self.window_counts_before_dom_query = dict(self.counts)
            self.query = asyncio.ensure_future(feed.web.evaluate_javascript(
                'JSON.stringify(window.logisticsInputTrace?window.logisticsInputTrace():null)'))
            self._query_consumer_added = False
            done, _ = await asyncio.wait((self.query,), timeout=2)
            if done and not self.closed:
                from .ios_input import _safe_dom_trace
                self.dom = _safe_dom_trace(json.loads(self.query.result()))
        except Exception:
            pass  # Availability is explicit in the bounded diagnostic receipt.
        finally:
            self._consume_query()
            if not self.closed:
                self.write_report()
                self.timer = self.loop.call_later(3, self.tick)
            self.task = None

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        if self.task is not None and not self.task.done():
            try:
                current = asyncio.current_task()
            except RuntimeError:
                current = None
            if self.task is not current:
                self.task.cancel()  # asyncio.wait never cancels native JS futures.
        self._consume_query()
        self.write_report()  # Called after unbind, before feed drops native refs.
