"""Actual system scene creation and writer separation on supported iPads."""
import asyncio


async def exercise_scenes(app):
    manager = app.scene_manager
    if type(app._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        if ObjCClass('UIDevice').currentDevice.userInterfaceIdiom == 1:
            assert manager.supported, 'iPad scene configuration is missing.'
    if not manager.supported:
        assert len(manager.owners.hosts) == 1
        return
    for session in list(app.workspace.sessions.values()):
        if session.transient:
            assert app.close_session(session.id)
    assert manager.new_window()
    for _ in range(100):
        candidates = [host for host in manager.owners.hosts.values() if host is not app]
        if candidates and getattr(candidates[0], 'scene_active', False):
            break
        await asyncio.sleep(.1)
    assert len(manager.owners.hosts) == 2, manager.error
    child = next(host for host in manager.owners.hosts.values() if host is not app)
    child.show_documents()
    assert child.main_window._impl.native.windowScene != app.main_window._impl.native.windowScene
    assert child.main_window._impl.native.windowScene is not None
    assert child.routes is not app.routes and child.editor is not app.editor
    original = app.current.id
    original_text = app.editor.value
    app.editor.value = 'Original window draft\n'
    child.editor.value = 'Independent window draft\n'
    child_key = child.current.id
    assert not child.open_document(original)
    assert child.current.id == child_key
    child.show_settings()
    app.show_documents()
    assert app.editor.value == 'Original window draft\n'
    assert child.editor.value == 'Independent window draft\n'
    # Keep the launch-scene diagnostic opt-in: this beta simulator can
    # terminate the process instead of delivering an in-process close callback.
    import os
    app.original_scene_close_tested = False
    app.scene_environment_limit = 'Physical original-window closure and process restoration remain unverified; the beta simulator may terminate the launch scene process.'
    if os.environ.get('LOGISTICS_PRIMARY_SCENE_PROBE') == '1':
        # A system close of the original scene preserves its warm owner and lets
        # that same window move to a replacement scene without another writer.
        from rubicon.objc import ObjCClass, ObjCInstance, Block, objc_id
        previous_scene = app.native_scene
        previous_identifier = str(previous_scene.session.persistentIdentifier)
        disconnects = manager.primary_disconnects
        errors = []
        error_handler = Block(lambda error: errors.append(str(ObjCInstance(error).localizedDescription)), None, objc_id)
        ObjCClass('UIApplication').sharedApplication.requestSceneSessionActivation(
            child.native_scene.session, userActivity=None, options=None, errorHandler=error_handler)
        for _ in range(100):
            if child.scene_active and not app.scene_active:
                break
            await asyncio.sleep(.1)
        await asyncio.sleep(.5)
        options = ObjCClass('UIWindowSceneDestructionRequestOptions').alloc().init()
        ObjCClass('UIApplication').sharedApplication.requestSceneSessionDestruction(
            previous_scene.session, options=options, errorHandler=error_handler)
        for _ in range(100):
            opened = {str(session.persistentIdentifier) for session in ObjCClass('UIApplication').sharedApplication.openSessions.allObjects()}
            if previous_identifier not in opened or errors:
                break
            await asyncio.sleep(.1)
        app.original_scene_close_tested = previous_identifier not in opened
        if app.original_scene_close_tested:
            manager.reconcile_scenes()
            assert manager.primary_disconnects > disconnects, (errors, list(manager.owners.hosts), list(manager.scenes))
            if manager.primary_disconnected:
                assert manager.new_window()
            for _ in range(100):
                if not manager.primary_disconnected and app.native_scene != previous_scene and app.scene_active:
                    break
                await asyncio.sleep(.1)
            assert not manager.primary_disconnected
            assert app.native_scene != previous_scene
            assert app.current.id == original and app.editor.value == 'Original window draft\n'
            assert child.editor.value == 'Independent window draft\n'
            assert len(manager.owners.hosts) == 2
        else:
            # The retained beta simulator can veto destruction of its launch scene
            # without reporting an error. Preserve that limit in the evidence; the
            # mandatory second-scene close/restore checks still run below.
            app.scene_environment_limit = 'Launch-scene destruction was vetoed by the simulator; physical original-window closure remains unverified.'
    child.checkpoint()
    assert manager.close_window(child)
    for _ in range(100):
        if len(manager.owners.hosts) == 1:
            break
        await asyncio.sleep(.1)
    assert len(manager.owners.hosts) == 1
    assert not child.active_host
    assert app.store.open(child_key).text == 'Independent window draft\n'
    assert manager.new_window(workspace_id=child.window_id)
    for _ in range(100):
        hosts = [host for host in manager.owners.hosts.values() if host is not app]
        if hosts and getattr(hosts[0], 'scene_active', False):
            break
        await asyncio.sleep(.1)
    restored = hosts[0]
    assert restored.window_id == child.window_id
    assert restored.current.id == child_key
    assert restored.editor.value == 'Independent window draft\n'
    assert restored.native_host.state.destination == 'settings'
    assert manager.close_window(restored)
    for _ in range(100):
        if len(manager.owners.hosts) == 1:
            break
        await asyncio.sleep(.1)
    assert len(manager.owners.hosts) == 1
    app.editor.value = original_text
