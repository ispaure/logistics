"""Measure mobile reader edges and controls across native rotations.

Synthetic imported/provider documents only. Reports retain failed samples so a
matrix run can distinguish missing coverage from a measured layout defect.
"""
from commonUtils.testing.stages import TestStage

import asyncio
import json
from pathlib import Path
import sys
import traceback
from zipfile import ZipFile

from mobile.app import LogisticsMobile
from .fixtures import capture_window, make_books
from .reader_flow_probe import pdf_bytes
from .reader_space_probe import portrait_png
from .rotation_checks import rotate, pose_snapshot

TEST_STAGE = TestStage.REGRESSION
BUNDLE = 'io.github.ispaure.logisticsviewerlayoutqa'


def geometry(app, widget):
    native = widget._impl.native
    if sys.platform == 'ios':
        window = app.main_window._impl.native
        rect = native.convertRect(native.bounds, toView=window)
        return [float(rect.origin.x), float(rect.origin.y),
                float(rect.size.width), float(rect.size.height)]
    from java import jarray, jint
    position = jarray(jint)(2)
    native.getLocationOnScreen(position)
    density = native.getResources().getDisplayMetrics().density
    return [position[0] / density, position[1] / density,
            native.getWidth() / density, native.getHeight() / density]


def safe_bounds(app):
    if sys.platform == 'ios':
        window = app.main_window._impl.native
        bounds, safe = window.bounds, window.safeAreaInsets
        return [float(bounds.origin.x + safe.left), float(bounds.origin.y + safe.top),
                float(bounds.origin.x + bounds.size.width - safe.right),
                float(bounds.origin.y + bounds.size.height - safe.bottom)]
    from android.graphics import Rect
    decor = app._impl.native.getWindow().getDecorView()
    visible = Rect()
    decor.getWindowVisibleDisplayFrame(visible)
    density = decor.getResources().getDisplayMetrics().density
    return [visible.left / density, visible.top / density,
            visible.right / density, visible.bottom / density]


class ViewerLayoutProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'viewer-layout-private'
        super().startup()

    def on_running(self):
        if getattr(self, '_viewer_layout_task', None) is None:
            self._viewer_layout_task = self.loop.create_task(self.check())

    async def settled(self, owner):
        for _ in range(200):
            if not getattr(owner, 'cloud_busy', False):
                await asyncio.sleep(.3)
                if not getattr(owner, 'cloud_busy', False):
                    return
            await asyncio.sleep(.1)
        raise AssertionError('Reader did not settle')

    async def sample(self, owner, name, orientation, output):
        await self.settled(owner)
        before = None
        if 'epub' in name:
            before = await self.epub_metrics(owner)
        await rotate(self, orientation, settle=.5)
        await self.settled(owner)
        self.adaptive.render()
        await asyncio.sleep(.4)
        view = getattr(owner, 'library_view', None) or owner.crypt_view
        row = dict(viewer=name, orientation=orientation, pose=pose_snapshot(self),
                   safe=safe_bounds(self), view=geometry(self, view),
                   bottom_margin=view.style.margin_bottom, errors=[])
        footer = getattr(owner, 'page_footer', None)
        if footer is not None and footer.widget.parent is not None:
            row['footer'] = geometry(self, footer.widget)
            row['slider'] = geometry(self, footer.slider)
            row['vertical'] = footer.vertical
            x, y, width, height = row['footer']
            left, top, right, bottom = row['safe']
            row['bottom_gap'] = bottom - y - height
            from mobile.reader_edges import passive_caption_tail
            extension = (min(passive_caption_tail(view),
                max(0, float(self.main_window._impl.native.safeAreaInsets.bottom) - 4))
                if sys.platform == 'ios' else 0)
            row['passive_caption_extension'] = extension
            row['edge_clearance'] = footer.widget.style.margin_bottom
            if abs(row['bottom_gap'] + extension - row['edge_clearance']) > 2:
                row['errors'].append('Footer is not at the safe bottom')
            if x < left - 2 or x + width > right + 2 or y < top - 2:
                row['errors'].append('Footer extends beyond safe bounds')
            if not footer.vertical:
                row['transport'] = geometry(self, footer.row)
                if row['transport'][1] + row['transport'][3] > bottom + 1:
                    row['errors'].append('Reader transport enters the home-gesture strip')
                if sys.platform == 'ios':
                    from mobile.ios_toolbar import vertical_edge
                    controller = self.native_host.adapter.content_controller(self.native_host.state.destination)
                    title = controller.navigationItem.titleView
                    if vertical_edge(controller) and title is not None and row['pose'].get('hinge_status') != 2:
                        window = self.main_window._impl.native
                        rect = title.convertRect(title.bounds, toView=window)
                        row['title_frame'] = [float(rect.origin.x), float(rect.origin.y),
                            float(rect.size.width), float(rect.size.height)]
                        row['title_top_gap'] = float(rect.origin.y - window.safeAreaInsets.top)
                        row['title_content_gap'] = row['view'][1] - float(rect.origin.y + rect.size.height)
                        if not 4 <= row['title_top_gap'] <= 8 or not 4 <= row['title_content_gap'] <= 8:
                            row['errors'].append('Reader title retains excessive outer/content spacing')
                row['caption'] = geometry(self, footer.spacer)
                if not 44 <= row['transport'][3] <= 50:
                    row['errors'].append('Horizontal footer lost its compact touch row')
                from commonUtils.ui.readers.layout import READER_LAYOUT
                thumb_bottom = row['slider'][1] + row['slider'][3] / 2 + READER_LAYOUT.thumb_extent / 2
                row['caption_thumb_gap'] = row['caption'][1] - thumb_bottom
                if not 4 <= row['caption_thumb_gap'] <= 8:
                    row['errors'].append('Progress caption is not close to and clear of the thumb')
                if row['caption'][2] < width - 2:
                    row['errors'].append('Progress caption does not span the footer for centered text')
                label = footer.spacer._impl.native
                if sys.platform == 'ios':
                    from mobile.screen_privacy import native_value
                    from rubicon.objc import CGPoint
                    slider = footer.slider._impl.native
                    sx, sy, sw, sh = row['slider']
                    hit = self.main_window._impl.native.hitTest(
                        CGPoint(sx + sw / 2, sy + sh - 2), withEvent=None)
                    row['slider_lower_hit'] = bool(hit is not None and
                        (hit == slider or hit.isDescendantOfView(slider)))
                    if not row['slider_lower_hit']:
                        row['errors'].append('Caption blocks the lower slider touch area')
                    intrinsic = native_value(label, 'intrinsicContentSize')
                    row['caption_font'] = float(label.font.pointSize)
                    row['caption_required'] = [float(intrinsic.width), float(intrinsic.height)]
                else:
                    density = label.getResources().getDisplayMetrics().density
                    row['caption_font'] = label.getTextSize() / label.getResources().getDisplayMetrics().scaledDensity
                    row['caption_required'] = [max(label.getPaint().measureText(line) for line in footer.spacer.text.split('\n')) / density,
                        label.getLineHeight() * label.getLineCount() / density]
                from commonUtils.ui.readers.layout import READER_LAYOUT
                if abs(row['caption_font'] - READER_LAYOUT.caption_size) > .01:
                    row['errors'].append('Progress caption differs from the native subtitle font size')
                if any(actual + 1 < required for actual, required in zip(row['caption'][2:], row['caption_required'])):
                    row['errors'].append('Progress caption clips its native text metrics')
            if footer.vertical and height < 88:
                row['errors'].append('Vertical progress has no usable scrubbing length')
        else:
            # Images and text may have no progress control; their reading frame
            # must still use the available height without a retired footer gap.
            row['bottom_gap'] = row['safe'][3] - row['view'][1] - row['view'][3]
            row['intentional_margin'] = getattr(getattr(view, '_reading_frame_owner', None), 'margin', 12)
            if abs(row['bottom_gap'] - row['intentional_margin']) > 2:
                row['errors'].append('Reader frame is not at the safe bottom')
        if 'epub' in name:
            row['epub'] = await self.epub_metrics(owner)
            dom = row['epub']
            if dom['padding'] != [0, 32, 0, 32]:
                row['errors'].append('EPUB padding differs from compact vertical/chosen horizontal gutters')
            if abs(dom['viewport_height'] - dom['inner_height']) > 1:
                row['errors'].append('EPUB viewport loses height beyond its vertical gutters')
            if before and before['anchor'] != dom['anchor']:
                row['errors'].append('EPUB rotation lost the retained passage anchor')
            if dom.get('native_adjusted_inset', [0, 0, 0, 0]) != [0, 0, 0, 0]:
                row['errors'].append('EPUB WebView applies another native content inset')
            if not all(dom.get('native_edge_effects', {}).values()):
                row['errors'].append('A native scroll-edge effect can obscure the EPUB text')
            if orientation == 'portrait' and dom['index'] == 0 and dom['count'] > 1:
                web = self.epub_web(owner)
                await web.evaluate_javascript('window.reader.turn(1)')
                await asyncio.sleep(.35)
                turned = await self.epub_metrics(owner)
                if turned['index'] <= dom['index'] or turned['anchor'] <= dom['anchor']:
                    row['errors'].append('EPUB page turn did not advance its passage')
        await capture_window(self, output / f'{name}-{orientation}.png')
        return row

    def epub_web(self, owner):
        web = getattr(owner, 'epub_view', None)
        if web is not None:
            return web
        return owner.provider_epub_view.webview

    async def epub_metrics(self, owner):
        web = self.epub_web(owner)
        script = '''JSON.stringify((() => {
          const pages=document.querySelector('[data-logistics-pages]');
          if(!pages || !window.reader)return null;
          const body=getComputedStyle(document.body), viewport=pages.parentElement;
          return {...window.reader.pagination(), inner_height:innerHeight,
            padding:[body.paddingTop,body.paddingRight,body.paddingBottom,body.paddingLeft].map(parseFloat),
            viewport_height:viewport.getBoundingClientRect().height};
        })())'''
        for _ in range(150):
            # Provider restoration may replace the initial chapter WebView.
            # Observe the currently mounted reader, never its retired surface.
            web = self.epub_web(owner)
            try:
                raw = await asyncio.wait_for(web.evaluate_javascript(script), timeout=3)
            except asyncio.TimeoutError:
                continue
            value = json.loads(raw) if raw else None
            if value:
                break
            await asyncio.sleep(.1)
        else:
            diagnostics = await web.evaluate_javascript('JSON.stringify({url:location.href,ready:document.readyState,marker:!!document.querySelector("meta[name=logistics-reader-root]"),reader:!!window.reader,pages:!!document.querySelector("[data-logistics-pages]")})')
            bridge = web._chapter_bridge
            from features.books.mobile.presentation import SCRIPT
            script = SCRIPT.replace('OPTIONS', json.dumps(dict(root=bridge.root, offset=bridge.offset, motion=False)), 1)
            forced = await asyncio.wait_for(web.evaluate_javascript(
                'var diagnosticError=null;try {' + script + '}catch(e){diagnosticError=String(e)};JSON.stringify({error:diagnosticError,reader:!!window.reader,marker:document.querySelector("meta[name=logistics-reader-root]").content})'), timeout=3)
            raise AssertionError('EPUB native pagination did not initialize: ' + str(diagnostics) +
                f' bridge_ready={bridge.ready} bridge_closed={bridge.closed} root={bridge.root}; forced={forced}')
        value['native_frame'] = geometry(self, web)
        if sys.platform == 'ios':
            from rubicon.objc import SEL
            from mobile.screen_privacy import native_value
            inset = web._impl.native.scrollView.adjustedContentInset
            value['native_adjusted_inset'] = [float(inset.top), float(inset.right), float(inset.bottom), float(inset.left)]
            scroll = web._impl.native.scrollView
            value['native_edge_effects'] = {edge: bool(native_value(getattr(scroll, edge), 'isHidden'))
                for edge in ('topEdgeEffect', 'bottomEdgeEffect') if scroll.respondsToSelector(SEL(edge))}
        return value

    async def check(self):
        output = Path(self.paths.cache) / 'viewer-layout'
        output.mkdir(exist_ok=True)
        report = dict(success=False, platform=sys.platform, samples=[], errors=[])
        try:
            startup = getattr(self, 'startup_task', None)
            if startup is not None:
                await asyncio.shield(startup)
            await self.show_files()
            if sys.platform != 'ios':
                report['private_html'] = await self.private_html_loads()
            root = self.storage_root
            root.mkdir(parents=True, exist_ok=True)
            epub, _ = make_books(root)
            with ZipFile(epub) as archive:
                entries = {name: archive.read(name) for name in archive.namelist()}
            for name in ('one.xhtml', 'two.xhtml'):
                entries[name] = ('<html><body><h1>Native layout chapter</h1>' +
                    '<p>A passage that must remain visible when the reader rotates or folds.</p>' * 100 +
                    '</body></html>').encode()
            with ZipFile(epub, 'w') as archive:
                for name, data in entries.items():
                    archive.writestr(name, data)
            comic = root / 'Layout.cbz'
            with ZipFile(comic, 'w') as archive:
                for index in range(4):
                    archive.writestr(f'{index}.png', portrait_png())
            pdf = root / 'Layout.pdf'
            pdf.write_bytes(pdf_bytes())
            image = root / 'Layout.png'
            image.write_bytes(portrait_png())
            text = root / 'Layout.txt'
            text.write_text('Reader layout fixture\n' * 100)
            self.preferences.values['comic_layout'] = 'single'
            self.preferences.values['reading_margin'] = '32'
            from commonUtils.runtime.resources.documents import LocalDocuments
            from commonUtils.runtime.resources.local import LocalFiles
            from services.documents.provider_documents import ProviderDocuments
            cases = [('imported-comic', comic, True), ('imported-epub', epub, True),
                     ('provider-comic', comic, False), ('provider-epub', epub, False),
                     ('pdf', pdf, False), ('image', image, False), ('text', text, False)]
            for name, path, imported in cases:
                try:
                    if imported:
                        record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), path)
                        assert await self.open_book(record['id'])
                        owner = self.readers.active
                        owner.set_reading_mode(False)
                    else:
                        assert await self.open_crypt(copies=ProviderDocuments(LocalFiles(root)), key=path.name)
                        owner = self.private_sessions.active
                        if getattr(owner, 'crypt_immersive', False):
                            owner.toggle_private_reading_mode()
                    for orientation in ('portrait', 'landscape-left', 'landscape-right', 'portrait'):
                        row = await self.sample(owner, name, orientation, output)
                        report['samples'].append(row)
                        (output / 'progress.json').write_text(json.dumps(report, indent=2))
                        print('VIEWER_LAYOUT_SAMPLE=' + json.dumps(row), flush=True)
                    self.request_reader_close(owner.session.id)
                    for _ in range(100):
                        if owner.session.id not in self.workspace.sessions:
                            break
                        await asyncio.sleep(.1)
                    assert owner.session.id not in self.workspace.sessions
                except Exception:
                    report['errors'].append(dict(viewer=name, error=traceback.format_exc()))
                    break
            if not report['errors']:
                await self.video_samples(output, report)
            report['success'] = len(report['samples']) == (len(cases) + 2) * 4 and not report['errors'] and not any(
                row['errors'] for row in report['samples'])
        except Exception:
            report['errors'].append(dict(error=traceback.format_exc()))
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        # The standard focused runner consumes this path.
        (Path(self.paths.cache) / 'viewer-layout-result.json').write_text(json.dumps(report, indent=2))
        print('VIEWER_LAYOUT_RESULT=' + json.dumps(report), flush=True)

    async def private_html_loads(self):
        """Both memory-only Android paths must dispatch completion and retain text."""
        import toga
        from toga.style import Pack
        from commonUtils.ui.native.private_webview import PrivateWebView
        results = []
        for text in ('Private inline 100% é 漢', '漢%é ' * 180000):
            print('PRIVATE_HTML_START=' + str(len(text)), flush=True)
            loaded = asyncio.Event()
            web = PrivateWebView(on_webview_load=lambda widget, **kw: loaded.set(), style=Pack(flex=1))
            try:
                self.show_view(toga.Box(children=[web], style=Pack(flex=1)))
                web.set_content('https://logistics.invalid/private-load/', '<html><body>' + text + '</body></html>')
                try:
                    await asyncio.wait_for(loaded.wait(), timeout=15)
                except TimeoutError as error:
                    state = await web.evaluate_javascript('JSON.stringify({url:location.href,ready:document.readyState,characters:document.body.textContent.length})')
                    raise AssertionError(f'Private HTML completion missing for {len(text)} characters: {state}') from error
                count = await web.evaluate_javascript('document.body.textContent.length')
                assert count == len(text), (count, len(text))
                results.append(dict(characters=count, loaded=True))
                print('PRIVATE_HTML_LOADED=' + str(count), flush=True)
            finally:
                web.clear_private_content()
                await self.show_files()
        return results

    async def video_samples(self, output, report):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.video.mobile.player import open_video
        root = Path(__file__).with_name('video-fixtures')
        for name in ('h264-aac.mp4', 'mpeg4-mp3.avi'):
            assert await open_video(self, LocalFiles(root), name)
            owner = self.video_player
            await asyncio.sleep(1)
            for orientation in ('portrait', 'landscape-left', 'landscape-right', 'portrait'):
                await rotate(self, orientation, settle=.5)
                native = owner.native.native
                if sys.platform == 'ios':
                    from .video_ui_probe import frame
                    from mobile.screen_privacy import native_value
                    native.setControlsShown(True)
                    view = native_value(native, 'view')
                    view.layoutIfNeeded()
                    window = native_value(view, 'window')
                    controls = frame(native.controlsScroll, window)
                    bounds, safe = window.bounds, window.safeAreaInsets
                    bottom = float(bounds.origin.y + bounds.size.height - safe.bottom)
                    tabletop = bool(native.tabletop)
                    gap = bottom - controls[1] - controls[3]
                    errors = [] if tabletop or abs(gap) < 2 else ['Video controls retain an extra bottom gap']
                    row = dict(viewer='video-' + name, orientation=orientation, pose=pose_snapshot(self),
                        controls=controls, bottom_gap=gap, tabletop=tabletop, errors=errors)
                else:
                    from java import jarray, jint
                    def field(key):
                        value = native.getClass().getDeclaredField(key)
                        value.setAccessible(True)
                        return value.get(native)
                    native.status('')
                    root_view, controls = field('root'), field('controlsScroll')
                    await asyncio.sleep(.2)
                    density = controls.getResources().getDisplayMetrics().density
                    top = jarray(jint)(2)
                    origin = jarray(jint)(2)
                    controls.getLocationOnScreen(top)
                    root_view.getLocationOnScreen(origin)
                    insets = root_view.getRootWindowInsets()
                    bottom = origin[1] + root_view.getHeight() - insets.getSystemWindowInsetBottom()
                    gap = (bottom - top[1] - controls.getHeight()) / density
                    row = dict(viewer='video-' + name, orientation=orientation,
                        bottom_gap=gap, errors=[] if abs(gap) < 2 else ['Video controls retain an extra bottom gap'])
                report['samples'].append(row)
                (output / 'progress.json').write_text(json.dumps(report, indent=2))
                await capture_window(self, output / f'video-{name}-{orientation}.png')
            await owner.close()


def main():
    return ViewerLayoutProbe('Viewer Layout QA', BUNDLE)
