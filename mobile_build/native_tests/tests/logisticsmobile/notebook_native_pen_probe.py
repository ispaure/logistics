"""Actual Toga/window/mounted producer smoke; synthetic JS dots are not hardware input."""
import asyncio
import json
import os
from pathlib import Path
import traceback

from .notebook_probe import NotebookProbe
from .web_checks import wait_for_text


async def ready(predicate, description, seconds=30):
    from time import monotonic
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(.05)
    raise AssertionError(description)


async def mounted(app, panel):
    from rubicon.objc import ObjCClass
    from toga_iOS.window import MainWindow
    from commonUtils.ui.native.keyboard import native_value
    assert type(app.main_window._impl) is MainWindow, type(app.main_window._impl)
    window = app.main_window._impl.native
    assert window.isKindOfClass(ObjCClass('LogisticsNotebookInputWindow'))
    await wait_for_text(panel.web, 'Notebook')
    assert native_value(panel.web._impl.native.window) == window
    assert panel.pen_input is not None and panel.pen_input.enabled
    reporter = panel.pen_input.reporter
    assert reporter is not None and not reporter.closed
    native_receipt = reporter.snapshot()
    assert native_receipt['native_available'] is True and native_receipt['native_producer'] is True
    assert native_receipt['view_id'] == panel.pen_input.view_id
    assert native_receipt['window_id'] == app.main_window._notebook_native_trace_id
    assert native_receipt['pairing'] == 'separate-scopes'
    assert 'window aggregate' in native_receipt['scope']
    def receipt():
        raw = Path(reporter.output).read_bytes()
        assert len(raw) <= 16384
        value = json.loads(raw)
        assert value['native']['observer_id'] == reporter.observer_id
        assert value['native']['view_id'] == panel.pen_input.view_id
        assert value['native']['window_id'] == app.main_window._notebook_native_trace_id
        assert value['pair_stable'] is False and value['closed'] is False
        return value
    receipt()  # Actual atomic private writer, no mock/gesture/native counter replacement.
    await ready(lambda: reporter.dom is not None and reporter.dom.get('view_id') == panel.pen_input.view_id,
                'Real bounded native reporter did not observe this DOM canvas', 8)
    observed = receipt()
    assert observed['native']['dom_view_matches'] is True
    assert observed['dom']['view_id'] == panel.pen_input.view_id
    state = json.loads(await panel.web.evaluate_javascript(
        'JSON.stringify({enabled:state.native_pen,nonce:state.native_pen_nonce,trace:logisticsInputTrace().view_id})'))
    assert state == dict(enabled=True, nonce=panel.pen_input.view_id, trace=panel.pen_input.view_id), state
    assert panel.view._native_reader_title() == panel.session.title
    controls = [panel.view._reader_close_button, *panel.view._native_reader_buttons()]
    assert controls, 'No native notebook controls'
    band = getattr(panel.view, '_reader_top_band_state', None)
    if band is not None:
        controller = app.native_host.adapter.content_controller(app.native_host.state.destination)
        assert band['controller'] == controller
        assert app._reader_toolbar_controller == controller
        assert str(controller.navigationItem.title) == panel.view._native_reader_title()
        header = band['header']
        assert panel.view._document_title_header is header and header.parent is not None
        row = header.children[0]
        assert native_value(row._impl.native.window) == window
        title = panel.view._document_title_view
        assert title.superview == row._title_content._impl.native
        assert native_value(title.window) == window
        title_rect = title.convertRect(title.bounds, toView=controller.view)
        geometry = band['geometry']
        assert title_rect.size.width >= 44 and title_rect.size.height > 0
        assert title_rect.origin.x >= geometry['left'] - 1
        assert title_rect.origin.x + title_rect.size.width <= geometry['right'] + 1
        assert title_rect.origin.y >= -1
        assert title_rect.origin.y + title_rect.size.height <= geometry['row_height'] + 1
        for control in controls:
            native = control._impl.native
            assert native.isDescendantOfView(row._impl.native)
            assert native_value(native.window) == window and not native.hidden
            bounds = native.convertRect(native.bounds, toView=controller.view)
            assert bounds.size.width >= 44 and bounds.size.height >= 44
            geometry = band['geometry']
            assert bounds.origin.y >= -1
            assert bounds.origin.y + bounds.size.height <= geometry['row_height'] + 1
            assert bounds.origin.x >= geometry['left'] - 1
            assert bounds.origin.x + bounds.size.width <= geometry['right'] + 1
    else:
        controller = app._reader_toolbar_controller
        assert native_value(controller.view.window) == window
        assert str(controller.navigationItem.title) == panel.view._native_reader_title()
        nav = controller.navigationItem
        items = list(nav.leftBarButtonItems or ()) + list(nav.rightBarButtonItems or ())
        from rubicon.objc import SEL
        for selector, attribute in [('leadingItemGroups', 'leadingItemGroups'),
                                    ('trailingItemGroups', 'trailingItemGroups')]:
            if nav.respondsToSelector(SEL(selector)):
                for group in list(getattr(nav, attribute) or ()):
                    items.extend(list(group.barButtonItems or ()))
        if nav.respondsToSelector(SEL('pinnedTrailingGroup')):
            pinned = native_value(nav.pinnedTrailingGroup)
            if pinned is not None:
                items.extend(list(pinned.barButtonItems or ()))
        for control in controls:
            if (getattr(control, 'control_icon', None) in ('more', 'overflow')
                    and native_value(nav.additionalOverflowItems) is not None):
                assert native_value(control._impl.native.menu) is not None
                continue
            item = getattr(control, '_ios_action_item', None)
            assert item is not None and item in items, 'Notebook native action is not mounted'
            assert native_value(item.target) is not None
    assert panel.view._reader_close_button.enabled
    return dict(compiled_window=True, actual_toga_backend=True, attached_feed=True,
                native_title=True, attached_native_controls=len(controls), duplicate_guard_enabled=True,
                actual_private_reporter=True, reporter_native_available=True, reporter_dom_view_matches=True)


async def geometry(app, panel, orientation, output, index):
    from commonUtils.ui.native.keyboard import native_value
    from .fixtures import capture_window
    native = panel.web._impl.native
    window = native_value(native.window)
    rect = native.convertRect(native.bounds, toView=window)
    size = native_value(window.bounds).size
    scene = native_value(window.windowScene)
    status = native_value(scene.statusBarManager.statusBarFrame)
    dom = json.loads(await panel.web.evaluate_javascript("""JSON.stringify({
        width:innerWidth,height:innerHeight,paper:canvas.getBoundingClientRect().toJSON(),
        viewport:$('viewport').getBoundingClientRect().toJSON(),
        header:document.querySelector('header').getBoundingClientRect().toJSON()})"""))
    paper_top = float(rect.origin.y) + dom['paper']['top'] * float(rect.size.width) / dom['width']
    status_bottom = float(status.origin.y + status.size.height)
    band = getattr(panel.view, '_reader_top_band_state', None)
    record = dict(orientation=orientation,window=[float(size.width),float(size.height)],
        status_bottom=status_bottom,paper_window_top=paper_top,dom=dom,
        webview=[float(rect.origin.x),float(rect.origin.y),float(rect.size.width),float(rect.size.height)],
        content_header=band is not None)
    if orientation == 'portrait' and os.environ.get('LOGISTICS_NATIVE_PEN_EXPECT_OPEN') == '1':
        assert [round(size.width),round(size.height)] == [669,951], record
        assert band is not None, record
        assert status_bottom <= paper_top < 206, record
    if orientation == 'landscape-left':
        assert band is None, record
    await capture_window(app, output / ('native-pencil-' + str(index) + '-' + orientation + '.png'))
    return record


class NativePencilProbe(NotebookProbe):
    async def check(self, app):
        result = dict(success=False, synthetic_input=True, physical_pencil_tested=False)
        try:
            await ready(lambda: not getattr(self, '_startup_in_progress', True), 'Startup did not finish', 45)
            background = getattr(self, 'cloud_startup_task', None)
            if background is not None:
                await background
            self.show_cloud(present=False)
            restoring = getattr(self, 'cloud_restore_task', None)
            if restoring is not None:
                await restoring
            from .fixtures import choose_creation_type
            app.set_feature_enabled('notebooks', True, refresh=False)
            app.show_home()
            await choose_creation_type(app, 'rmdoc')
            form = app.editor_picker()
            form.save_as_name.value = 'Notebook Pencil QA'
            form.creation_type.value = 'Remarkable Document (.rmdoc)'
            await form.choose_creation_location()
            picker = app.editor_picker()
            await ready(lambda: picker.editor_picker_location == ('All files', '') and not picker.cloud_busy,
                        'Local picker did not finish')
            row = next(row for row in picker.editor_picker_rows.values() if row['name'] == 'Local')
            assert await picker.browser_editor_folder(row)
            await picker.confirm_editor_file()
            panel = app.notebook_panel
            result['mount'] = await mounted(app, panel)
            before = len(panel.editor.notebook.page(0).strokes)
            # Real production logisticsNativePen -> DOM handler -> native URI bridge
            # -> editor/checkpoint -> acknowledgement, no send/queue substitution.
            await panel.web.evaluate_javascript("""(()=>{
                mode='ink';$('tool').value='17';$('tool').onchange();
                const r=canvas.getBoundingClientRect();
                for(let n=0;n<20;n++){
                    const p=[[Math.max(0,r.left)+30+n*3,Math.max(0,r.top)+70,.5]];
                    if(document.elementFromPoint(p[0][0],p[0][1])!==canvas)throw Error('Synthetic dot not on visible canvas');
                    logisticsNativePen('down',500+n,p,innerWidth,innerHeight);
                    logisticsNativePen('up',500+n,p,innerWidth,innerHeight);
                }
                return true;
            })()""")
            await ready(lambda: len(panel.editor.notebook.page(0).strokes) == before + 20 and not panel.busy,
                        'Twenty synthetic dots did not reach actual editor', 45)
            for _ in range(600):
                state = json.loads(await panel.web.evaluate_javascript('JSON.stringify({busy,queued:queue.length,active,count:state.strokes.length})'))
                if not state['busy'] and not state['queued'] and state['active'] is None:
                    break
                await asyncio.sleep(.05)
            else:
                raise AssertionError(('Native DOM acknowledgement queue did not drain', state))
            assert state['count'] == before + 20, state
            assert all(len(stroke.points) == 1 for stroke in panel.editor.notebook.page(0).strokes[-20:])
            assert await panel.save_from_view()
            key, session = panel.key, panel.session.id
            assert len(panel.repository.open(key).page(0).strokes) == before + 20
            old_feed = panel.pen_input
            # Existing shared Close control goes through its guarded UI action.
            await panel.view._reader_close_button.on_press()
            await ready(lambda: session not in app.workspace.sessions, 'Native Close did not close saved session')
            assert old_feed.closed and panel.web is None
            from features.notebooks.mobile.documents import open_notebook
            assert await open_notebook(app, key=key)
            reopened = app.notebook_panel
            result['reopen'] = await mounted(app, reopened)
            assert len(reopened.editor.notebook.page(0).strokes) == before + 20
            from .rotation_checks import rotate
            captures = Path(self.paths.cache) / 'notebook-ui'
            captures.mkdir(exist_ok=True)
            result['rotation_geometry'] = []
            for index, orientation in enumerate(('portrait', 'landscape-left', 'portrait')):
                await rotate(app, orientation)
                result['rotation_geometry'].append(dict(index=index,
                    mount=await mounted(app, reopened),
                    geometry=await geometry(app, reopened, orientation, captures, index)))
                assert len(reopened.editor.notebook.page(0).strokes) == before + 20
            if os.environ.get('LOGISTICS_NATIVE_PEN_EXPECT_OPEN') == '1':
                from commonUtils.ui.native.keyboard import native_value
                cache = Path(self.paths.cache)
                assert (cache / 'drive-notes-touches').is_file(), 'Owned Simulator touch driver not enrolled'
                assert getattr(reopened.view, '_reader_top_band_state', None) is not None
                close = reopened.view._reader_close_button._impl.native
                window = native_value(close.window)
                assert window == app.main_window._impl.native
                rect = close.convertRect(close.bounds, toView=window)
                point = [float(rect.origin.x + rect.size.width / 2),
                         float(rect.origin.y + rect.size.height / 2)]
                session, final_feed = reopened.session.id, reopened.pen_input
                done = cache / 'notes-touch-done'
                done.unlink(missing_ok=True)
                (cache / 'notes-touch-request.json').write_text(json.dumps(dict(action='tap', points=point)))
                await ready(done.exists, 'Owned Simulator did not acknowledge the real Close tap', 25)
                done.unlink()
                await ready(lambda: session not in app.workspace.sessions,
                            'System hit-testing did not deliver the real top-row Close tap', 20)
                assert final_feed.closed and reopened.web is None
                result['system_close_tap'] = dict(success=True, coordinate_space='owned-window points', point=point,
                                                exact_session_closed=True, feed_retired=True)
            result.update(success=True, synthetic_dots=20, ordered_acknowledgements=True,
                          actual_checkpoint=True, save_reopen=True, native_close_action=True)
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'notebook-native-pen-result.json').write_text(json.dumps(result, indent=2))


def main():
    return NativePencilProbe('Notebook Pencil QA', 'io.github.ispaure.logisticsnotebookqa')
