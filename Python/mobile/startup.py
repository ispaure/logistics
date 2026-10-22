"""Visible, phased native startup without exposing document or account names."""
import asyncio
import inspect
import logging
from enum import IntEnum

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN

class StartupPhase(IntEnum):
    STORAGE = 0
    PREFERENCES = 1
    DOCUMENTS = 2
    EDITOR = 3
    NAVIGATION = 4
    RESTORE = 5
    WORKSPACE = 6
    WINDOW = 7


STEPS = ('Preparing private storage…', 'Loading preferences…', 'Restoring documents…',
         'Preparing the editor…', 'Preparing navigation…', 'Restoring open documents…',
         'Preparing your workspace…', 'Opening your workspace…')


class StartupScreen:
    def __init__(self):
        from .appearance import surface
        self.status = surface(toga.Label(STEPS[0], style=Pack(text_align=CENTER, margin_bottom=16)),
                              radius=0, background='transparent', foreground='text', outlined=False, eink_outlined=False)
        self.progress = toga.ProgressBar(max=len(STEPS), value=0, style=Pack(height=8, margin_bottom=12))
        self.detail = surface(toga.Label('Step 1 of ' + str(len(STEPS)), style=Pack(text_align=CENTER, font_size=12)),
                              radius=0, background='transparent', foreground='muted', outlined=False, eink_outlined=False)
        title = surface(toga.Label('Logisticks', style=Pack(text_align=CENTER, font_size=28,
                            font_weight='bold', margin_bottom=24)), radius=0,
                            background='transparent', foreground='text', outlined=False, eink_outlined=False)
        panel = toga.Box(children=[title, self.status, self.progress, self.detail],
                         style=Pack(direction=COLUMN, margin=32))
        self.view = surface(toga.Box(children=[panel],
            style=Pack(direction=COLUMN, justify_content=CENTER, flex=1)),
            radius=0, background='window', outlined=False)

    def hide_chrome(self, app):
        backend = type(app._impl).__module__
        if backend.startswith('toga_android.'):
            self.bar = app._impl.native.getSupportActionBar()
            self.bar_visible = bool(self.bar and self.bar.isShowing())
            if self.bar is not None:
                self.bar.hide()
        elif backend.startswith('toga_iOS.'):
            self.bar = app.main_window._impl.native.rootViewController
            self.bar_visible = not bool(self.bar.isNavigationBarHidden())
            self.bar.setNavigationBarHidden(True, animated=False)

    def restore_chrome(self, app):
        if getattr(self, 'bar', None) is not None:
            if type(app._impl).__module__.startswith('toga_android.'):
                if self.bar_visible:
                    self.bar.show()
            else:
                self.bar.setNavigationBarHidden(not self.bar_visible, animated=False)

    def cover_workspace(self, app):
        if type(app._impl).__module__.startswith('toga_android.'):
            self.cover = AndroidStartupCover(app)

    async def reveal_workspace(self, app):
        cover = getattr(self, 'cover', None)
        if cover is not None:
            try:
                await cover.ready()
            finally:
                cover.dispose()
                self.cover = None

    def show_step(self, index, name):
        self.status.text = name
        self.progress.value = index
        self.detail.text = f'Step {index + 1} of {len(STEPS)}'

    def failed(self):
        self.status.text = 'Couldn’t finish starting Logisticks.'
        self.detail.text = 'Close and reopen the app to try again.'


def load_startup_models(root, workspace_root):
    """Prepare durable models and display metadata without constructing controls."""
    from .preferences import Preferences
    from .documents import DocumentStore
    from .recent_documents import RecentDocuments
    from .workspace import Workspace
    preferences = Preferences(workspace_root)
    store = DocumentStore(root / 'Documents')
    recent = RecentDocuments(workspace_root)
    workspace = Workspace(workspace_root)
    display = {}
    keys = {session.resource for session in workspace.sessions.values() if session.provider == 'managed-text'}
    keys.update(item['resource'] for item in recent.items if item['provider'] == 'managed-text')
    for key in keys:
        try:
            doc = store.open(key)
            display[key] = dict(name=doc.name, modified=doc.modified, conflict=doc.conflict,
                revision=store._recovery_revision(store.path(key, '.json')),
                source_revision=store._recovery_revision(store.path(key, '.data')))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if preferences.values['clear_unmodified_documents_on_restart'] == 'true':
        for session in list(workspace.sessions.values()):
            if (preferences.values['restore_last_document'] == 'true'
                    and session.id == workspace.active):
                continue
            if session.provider == 'managed-text':
                info = display.get(session.resource)
                if info is None or info['modified'] or info['conflict']:
                    continue
            workspace.close(session.id, guard=lambda value: True)
    store.summaries()
    return dict(preferences=preferences, store=store, recent=recent, workspace=workspace, display=display)


async def finish_startup(app):
    """Run UI work on its native thread, allowing a frame between real phases."""
    try:
        for index, name in enumerate(app._startup_steps()):
            app.startup_screen.show_step(index, name)
            # A timed yield gives UIKit/Android a draw turn; sleep(0) can keep
            # draining Python callbacks without presenting the updated screen.
            await asyncio.sleep(1 / 60)
            prepare = getattr(app, '_prepare_startup_phase', None)
            if prepare is not None:
                await prepare(index)
        restore = getattr(app, 'startup_document_task', None)
        if restore is not None:
            await restore
        app.startup_screen.progress.value = len(STEPS)
        app._startup_layout_ready = True
        app.resize_workspace()
        await app.startup_screen.reveal_workspace(app)
        app._startup_in_progress = False
        start_cloud = getattr(app, '_start_background_cloud', None)
        if start_cloud is not None:
            start_cloud()
        return True
    except asyncio.CancelledError:
        cover = getattr(app.startup_screen, 'cover', None)
        if cover is not None:
            cover.dispose()
        raise
    except Exception:
        logging.getLogger(__name__).exception('Application startup failed')
        app.active_host = False
        app._startup_in_progress = True
        app.startup_screen.failed()
        app.main_window.content = app.startup_screen.view
        cover = getattr(app.startup_screen, 'cover', None)
        if cover is not None:
            cover.dispose()
        app.main_window.on_lose_focus = None
        app.main_window.on_resize = None
        app.on_exit = lambda app: True
        return False


async def restore_cloud_in_background(app):
    """Start connections after Home's first draw, without owning navigation."""
    await asyncio.sleep(1 / 60)
    if not app.active_host:
        return
    try:
        restore = app.start_cloud_restore()
        if restore is not None:
            await restore
    except asyncio.CancelledError:
        raise
    except Exception:
        # Connection errors must not turn an already usable Home into a
        # startup failure, or log credential/provider details.
        logging.getLogger(__name__).error('Background connection initialization failed')


def begin_startup(app):
    app.active_host = False
    app.startup_screen = StartupScreen()
    app._startup_window = app.main_window = toga.MainWindow(title='Logisticks', content=app.startup_screen.view)
    app.main_window.show()
    app.startup_screen.hide_chrome(app)
    running = app.on_running
    app.startup_task = app.loop.create_task(finish_startup(app))

    async def when_ready(sender):
        if await app.startup_task:
            result = running(app)
            if inspect.isawaitable(result):
                await result
    app.on_running = when_ready


class AndroidStartupCover:
    """Keep the last loading frame above the live, measuring workspace."""
    def __init__(self, app):
        from android.graphics import Bitmap, Canvas
        from android.widget import FrameLayout, ImageView
        from android.view import ViewTreeObserver
        from java import dynamic_proxy
        self.app = app
        self.parent = app.main_window._impl.container.native_parent
        # Toga Android flattens Box children into the window container; the
        # Box's own native view only draws its background.
        native = app.main_window._impl.container.native_content
        self.bitmap = Bitmap.createBitmap(max(1, native.getWidth()), max(1, native.getHeight()),
                                          Bitmap.Config.ARGB_8888)
        native.draw(Canvas(self.bitmap))
        self.image = ImageView(self.parent.getContext())
        self.image.setImageBitmap(self.bitmap)
        self.image.setScaleType(ImageView.ScaleType.FIT_XY)
        self.image.setClickable(True)
        self.image.setContentDescription('Opening your workspace…')
        self.image.setImportantForAccessibility(1)
        self.root = app.navigation._impl.native
        self.accessibility = self.root.getImportantForAccessibility()
        self.root.setImportantForAccessibility(4)  # Hide unfinished descendants.
        self.parent.addView(self.image, FrameLayout.LayoutParams(-1, -1))
        self.future = app.loop.create_future()
        self.geometry = None
        self.observer = None
        cover = self

        class Listener(dynamic_proxy(ViewTreeObserver.OnPreDrawListener)):
            def onPreDraw(self):
                try:
                    cover.before_draw()
                except Exception as error:
                    if not cover.future.done():
                        cover.future.set_exception(error)
                return True

        self.listener = Listener()

    async def ready(self):
        self.observer = self.parent.getViewTreeObserver()
        self.observer.addOnPreDrawListener(self.listener)
        self.parent.invalidate()
        await self.future

    def before_draw(self):
        if self.future.done():
            return
        root = self.app.navigation._impl.native
        content = self.app.navigation._impl.native_content
        geometry = (root.getWidth(), root.getHeight(), content.getWidth(), content.getHeight())
        if min(geometry) <= 0 or root.isLayoutRequested() or content.isLayoutRequested():
            self.parent.invalidate()
            return
        if geometry != self.geometry:
            self.geometry = geometry
            # Android has now allocated the final rail/content viewport. Reflow
            # against those measurements while the loading snapshot stays up.
            self.app.resize_workspace()
            self.app.navigation.refresh()
            self.parent.invalidate()
            return
        self.future.set_result(True)

    def dispose(self):
        if self.observer is not None and self.observer.isAlive():
            self.observer.removeOnPreDrawListener(self.listener)
        self.root.setImportantForAccessibility(self.accessibility)
        self.parent.removeView(self.image)
        self.image.setImageDrawable(None)
        # Let Android release the bitmap after its last display list is retired.
        self.bitmap = None
        if not self.future.done():
            self.future.cancel()
