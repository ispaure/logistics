"""Startup prepares durable models off-thread and defers inactive native views."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import get_ident
from unittest import TestCase
from unittest.mock import patch

from mobile.app import LogisticsMobile
from mobile.documents import DocumentStore
from mobile.preferences import Preferences
from mobile.workspace import Workspace
from mobile.startup import load_startup_models


class AsyncStartupApp(LogisticsMobile):
    def startup(self):
        from mobile.appearance import install_appearance
        from mobile.startup import begin_startup
        install_appearance(self)
        self._startup_in_progress = self._async_startup = True
        begin_startup(self)


class StartupModelTests(TestCase):
    def test_restart_cleanup_preserves_only_active_saved_document_when_restore_enabled(self):
        for restore in ('true', 'false'):
            with self.subTest(restore=restore), TemporaryDirectory() as directory:
                root = Path(directory)
                Preferences(root).save(restore_last_document=restore)
                store = DocumentStore(root / 'Documents')
                clean = store.create('Other.txt', b'Saved')
                active = store.create('Active.txt', b'Saved')
                workspace = Workspace(root)
                workspace.open('managed-text', clean.id, 'text')
                workspace.open('managed-text', active.id, 'text')
                workspace.save()
                models = load_startup_models(root, root)
                resources = {session.resource for session in models['workspace'].sessions.values()}
                self.assertEqual(resources, {active.id} if restore == 'true' else set())
                self.assertEqual(store.open(clean.id).text, 'Saved')

    def test_native_startup_reopens_local_epub_before_revealing_workspace(self):
        from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            restored = None
            try:
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                epub, _ = make_books(fixtures)
                self.assertTrue(app.loop.run_until_complete(app.open_download(path=epub)))
                app.loop.run_until_complete(app.next_book_page())
                selected = app.workspace.active
                app.checkpoint()
                restored = AsyncStartupApp('Logistics', 'io.github.ispaure.logisticsmobile')
                self.assertTrue(restored.loop.run_until_complete(restored.startup_task))
                self.assertEqual(restored.native_host.state.destination, 'documents')
                self.assertEqual(restored.workspace.active, selected)
                self.assertIsNotNone(restored.readers.active.book_reader)
                self.assertEqual(restored.readers.active.book_record['position'], 1)
            finally:
                hosts = [app, *([restored] if restored is not None else [])]
                for host in hosts:
                    background = getattr(host, 'cloud_startup_task', None)
                    if background is not None:
                        background.cancel()
                    host.main_window.close()
                for loop in {host.loop for host in hosts}:
                    loop.run_until_complete(asyncio.sleep(0))
                    loop.close()

    def test_async_startup_opens_active_document_and_keeps_recovery_metadata(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            preferences = Preferences(root)
            preferences.save(clear_unmodified_documents_on_restart='false')
            store = DocumentStore(root / 'Documents')
            doc = store.create('Recovered.txt', b'Baseline')
            doc.text = 'Unsaved synthetic draft'
            store.checkpoint(doc)
            workspace = Workspace(root)
            workspace.open('managed-text', doc.id, 'text', doc.name)
            workspace.save()
            LogisticsMobile.storage_root = root
            threads = []
            original = load_startup_models
            def load(*args):
                threads.append(get_ident())
                return original(*args)
            app = None
            try:
                with patch('mobile.startup.load_startup_models', side_effect=load):
                    app = AsyncStartupApp('Logistics', 'io.github.ispaure.logisticsmobile')
                    self.assertTrue(app.loop.run_until_complete(app.startup_task))
                self.assertNotEqual(threads, [get_ident()])
                self.assertEqual(app.current.id, doc.id)
                self.assertEqual(app.native_host.state.destination, 'documents')
                self.assertFalse(hasattr(app, 'folder_list'))
                self.assertEqual(app._startup_display[doc.id]['name'], 'Recovered.txt')
                self.assertTrue(app._startup_display[doc.id]['modified'])
                self.assertEqual(app.current.id, doc.id)
                self.assertEqual(app.current.text, 'Unsaved synthetic draft')
            finally:
                if app is not None:
                    background = getattr(app, 'cloud_startup_task', None)
                    if background is not None:
                        background.cancel()
                    app.main_window.close()
                    app.loop.run_until_complete(asyncio.sleep(0))
                    close_loop(app.loop)
                LogisticsMobile.storage_root = None


class ReplacementAdmissionTests(TestCase):
    def test_overlapping_model_loads_keep_newest_pending_claim_in_both_orders(self):
        from mobile.app import _active_hosts
        from mobile.application_lifecycle import lifecycle
        from mobile.startup import StartupPhase
        from types import SimpleNamespace as NS
        class Host:
            pass
        async def exercise(root, reverse):
            hosts = [Host(), Host()]
            for host in hosts:
                host.private_root, host.active_host, host._async_startup = root, False, True
            gates = [asyncio.Event(), asyncio.Event()]
            entered = [asyncio.Event(), asyncio.Event()]
            calls = 0
            async def load(*args):
                nonlocal calls
                index = calls
                calls += 1
                entered[index].set()
                try:
                    await gates[index].wait()
                except asyncio.CancelledError:
                    # A real to_thread worker can still complete after its wrapper
                    # is cancelled; simulate delivery of that late result too.
                    await gates[index].wait()
                return {'preferences': NS(values={'accent_hue': 1, 'accent_saturation': 1})}
            key = str(root.resolve()) + ':primary'
            with patch('mobile.app.asyncio.to_thread', side_effect=load):
                tasks = []
                try:
                    for index, host in enumerate(hosts):
                        task = asyncio.create_task(LogisticsMobile._prepare_startup_phase(host, StartupPhase.PREFERENCES))
                        host.startup_task = task
                        tasks.append(task)
                        await entered[index].wait()
                    self.assertIs(_active_hosts[key], hosts[1])
                    self.assertFalse(hosts[0].active_host)
                    self.assertTrue(lifecycle(hosts[0]).replaced)
                    for index in ([1, 0] if reverse else [0, 1]):
                        gates[index].set()
                        await asyncio.sleep(0)
                    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
                    self.assertIsInstance(outcomes[0], asyncio.CancelledError)
                    self.assertIsNone(outcomes[1])
                    self.assertNotIn('_startup_models', hosts[0].__dict__)
                    self.assertIn('_startup_models', hosts[1].__dict__)
                    lifecycle(hosts[0]).abort_startup()
                    self.assertIs(_active_hosts[key], hosts[1])
                finally:
                    for gate in gates:
                        gate.set()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    _active_hosts.pop(key, None)
        with TemporaryDirectory() as directory:
            for reverse in (False, True):
                with self.subTest(reverse=reverse):
                    asyncio.run(exercise(Path(directory), reverse))

    def host(self, root, *, window='primary', provider=False):
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        from mobile.private_sessions import PrivateSessions
        from mobile.provider_document import ProviderDocumentSession
        class Host:
            pass
        host = Host()
        host.private_root, host.window_id, host.active_host = root, window, True
        host._async_startup = True
        host.store = NS(flush_checkpoints=Mock())
        host.credential_document_lists = NS(flush_writes=Mock())
        host.screen_privacy = NS(dispose=Mock())
        if provider:
            manager = PrivateSessions.__new__(PrivateSessions)
            manager.app, manager.terminal, manager.positions = host, False, {}
            session = NS(id='doc')
            generation = [0]
            host.workspace = NS(sessions={'doc': session}, token=lambda key: ('doc', generation[0]),
                                accepts=lambda token: token == ('doc', generation[0]),
                                invalidate=lambda key: generation.__setitem__(0, generation[0] + 1))
            reader = NS(source=NS(close=Mock()), text='Saved', editable=True, read_only=False, kind='.md')
            owner = NS(app=host, manager=manager, session=session, workspace=host.workspace,
                       document_access=lambda: None, private_dirty=lambda: owner.crypt_text.value != reader.text,
                       crypt_text=NS(value='Saved'), set_document_busy=lambda busy: None)
            document = ProviderDocumentSession(owner)
            owner.provider_document = lambda: document
            owner._provider_document = document
            document.reader = reader
            editor = NS(view=object(), closed=False, bridge='synthetic', _revision=0)
            owner._provider_markdown = NS(formatted=editor, content=NS(children=[editor.view]),
                                           source=owner.crypt_text, closed=False, dispose=Mock())
            manager.controllers, manager.active = {'doc': owner}, owner
            host.private_sessions = manager
        return host

    def test_overlapping_flushes_newest_attempt_wins_including_newer_failure(self):
        from mobile.app import _active_hosts
        from mobile.application_lifecycle import lifecycle
        from mobile.startup import StartupPhase
        from unittest.mock import AsyncMock
        async def exercise(root, order, failure):
            old = self.host(root, provider=True)
            incoming = [self.host(root), self.host(root)]
            key = str(root.resolve()) + ':primary'
            _active_hosts[key] = old
            editor = old.private_sessions.active._provider_markdown.formatted
            entered = [asyncio.Event(), asyncio.Event()]
            release = [asyncio.Event(), asyncio.Event()]
            calls = 0
            async def flush():
                nonlocal calls
                index = calls
                calls += 1
                entered[index].set()
                await release[index].wait()
                if failure and index == 1:
                    if failure == 'cancelled':
                        raise asyncio.CancelledError
                    raise ValueError('Synthetic newer failure')
                editor._revision += 1
            editor.flush = flush
            tasks = []
            with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.test'), \
                    patch('mobile.app.asyncio.to_thread', new=AsyncMock(return_value={})) as load:
                try:
                    for index, host in enumerate(incoming):
                        host.startup_task = asyncio.create_task(LogisticsMobile._prepare_startup_phase(host, StartupPhase.PREFERENCES))
                        tasks.append(host.startup_task)
                        await entered[index].wait()
                    for index in order:
                        release[index].set()
                        await asyncio.gather(tasks[index], return_exceptions=True)
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    self.assertIsInstance(results[0], asyncio.CancelledError)
                    if failure:
                        self.assertIsInstance(results[1], asyncio.CancelledError if failure == 'cancelled' else OSError)
                        self.assertIs(_active_hosts[key], old)
                        self.assertTrue(old.active_host)
                        self.assertFalse(old.private_sessions.terminal)
                        load.assert_not_awaited()
                    else:
                        self.assertIsNone(results[1])
                        self.assertIs(_active_hosts[key], incoming[1])
                        self.assertTrue(lifecycle(old).replaced)
                        self.assertTrue(old.private_sessions.terminal)
                        load.assert_awaited_once()
                    lifecycle(incoming[0]).abort_startup()
                    self.assertIs(_active_hosts[key], old if failure else incoming[1])
                finally:
                    for gate in release:
                        gate.set()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    _active_hosts.pop(key, None)
        with TemporaryDirectory() as directory:
            for order in ((0, 1), (1, 0)):
                for failure in (False, 'error', 'cancelled'):
                    with self.subTest(order=order, failure=failure):
                        asyncio.run(exercise(Path(directory), order, failure))

    def test_preservation_and_disposal_reentrancy_do_not_overwrite_successor(self):
        from mobile.app import _active_hosts
        from mobile.application_lifecycle import lifecycle
        from unittest.mock import Mock
        from types import SimpleNamespace as NS
        with TemporaryDirectory() as directory:
            root = Path(directory)
            key = str(root.resolve()) + ':primary'
            for during in ('preserve', 'dispose'):
                with self.subTest(during=during):
                    old, middle, winner = [self.host(root) for _ in range(3)]
                    middle._async_startup = winner._async_startup = False
                    _active_hosts[key] = old
                    prefs = NS(values={'accent_hue': 1, 'accent_saturation': 1})
                    def enter():
                        # One-shot callback avoids recursive preservation.
                        old.store.flush_checkpoints = Mock()
                        LogisticsMobile._prepare_startup_preferences(winner, root)
                    callback = old.store.flush_checkpoints if during == 'preserve' else old.screen_privacy.dispose
                    callback.side_effect = enter
                    with patch('mobile.app.Preferences', return_value=prefs), \
                            patch('mobile.appearance.configure_android_eink'), patch('mobile.palette.set_accent'):
                        with self.assertRaises(asyncio.CancelledError):
                            LogisticsMobile._prepare_startup_preferences(middle, root)
                    self.assertIs(_active_hosts[key], winner)
                    self.assertTrue(winner.active_host)
                    lifecycle(middle).abort_startup()
                    self.assertIs(_active_hosts[key], winner)
                    _active_hosts.pop(key, None)

    def test_failed_model_load_releases_only_own_claim_and_other_windows_survive(self):
        from mobile.app import _active_hosts
        from mobile.application_lifecycle import lifecycle
        from mobile.startup import StartupPhase
        from unittest.mock import AsyncMock
        async def exercise(root):
            old, incoming = self.host(root), self.host(root)
            unrelated = self.host(root, window='secondary')
            key = str(root.resolve()) + ':primary'
            other_key = str(root.resolve()) + ':secondary'
            _active_hosts[key], _active_hosts[other_key] = old, unrelated
            try:
                with patch('mobile.app.asyncio.to_thread', new=AsyncMock(side_effect=OSError('Synthetic load failure'))):
                    with self.assertRaises(OSError):
                        await LogisticsMobile._prepare_startup_phase(incoming, StartupPhase.PREFERENCES)
                self.assertNotIn(key, _active_hosts)
                self.assertIs(_active_hosts[other_key], unrelated)
                self.assertTrue(unrelated.active_host)
                self.assertTrue(lifecycle(old).replaced)
                self.assertTrue(lifecycle(incoming).startup_aborted)
                self.assertNotIn('_startup_models', incoming.__dict__)
            finally:
                _active_hosts.pop(key, None)
                _active_hosts.pop(other_key, None)
        with TemporaryDirectory() as directory:
            asyncio.run(exercise(Path(directory)))

    def test_preservation_callback_aborting_incoming_keeps_old_host_in_both_startup_routes(self):
        from mobile.app import _active_hosts
        from mobile.application_lifecycle import lifecycle
        from mobile.startup import StartupPhase
        from unittest.mock import AsyncMock
        async def exercise(root, asynchronous):
            old, incoming = self.host(root, provider=True), self.host(root)
            incoming._async_startup = asynchronous
            key = str(root.resolve()) + ':primary'
            _active_hosts[key] = old
            owner = old.private_sessions.active
            reader = owner.provider_document().reader
            token = old.workspace.token('doc')
            editor = owner._provider_markdown.formatted
            async def flush():
                editor._revision += 1
            editor.flush = flush
            # Sync uses source mode: no unresolved native input to mask the
            # later callback-triggered cancellation being tested.
            if not asynchronous:
                owner._provider_markdown.content.children.clear()
            old.store.flush_checkpoints.side_effect = lambda: lifecycle(incoming).abort_startup()
            try:
                with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_iOS.test'), \
                        patch('mobile.app.asyncio.to_thread', new=AsyncMock()) as load:
                    with self.assertRaises(asyncio.CancelledError):
                        if asynchronous:
                            await LogisticsMobile._prepare_startup_phase(incoming, StartupPhase.PREFERENCES)
                        else:
                            LogisticsMobile._prepare_startup_preferences(incoming, root)
                    load.assert_not_awaited()
                self.assertIs(_active_hosts[key], old)
                self.assertTrue(old.active_host)
                self.assertFalse(old.private_sessions.terminal)
                self.assertIs(owner.provider_document().reader, reader)
                self.assertTrue(old.workspace.accepts(token))
                reader.source.close.assert_not_called()
            finally:
                _active_hosts.pop(key, None)
        with TemporaryDirectory() as directory:
            for asynchronous in (False, True):
                with self.subTest(asynchronous=asynchronous):
                    asyncio.run(exercise(Path(directory), asynchronous))


class NotebookReplacementTests(TestCase):
    """Replacement honors the notebook owner's uncertain-checkpoint retention."""
    def setUp(self):
        from features.notebooks.mobile.documents import open_notebook
        from mobile_build.tests.support.notebooks import create_storage_notebook_app
        self.app, _, _ = create_storage_notebook_app(self)
        self.assertTrue(self.app.loop.run_until_complete(open_notebook(self.app, name='Synthetic retained draft')))
        self.panel = self.app.notebook_panel
        class Shell:
            pass
        self.incoming = Shell()
        self.incoming.private_root = self.app.private_root
        self.incoming.active_host, self.incoming._async_startup = False, True

    def unconfirm_checkpoint(self):
        from features.notebooks.recovery import RecoveryIncomplete
        from mobile_build.tests.support.notebooks import draw_stroke
        document = self.panel.document
        manifest = document.recovery.root / document.key / 'state.json'
        read_bytes = Path.read_bytes
        attempted = False
        def reject_publication(*args, **kwargs):
            nonlocal attempted
            attempted = True
            raise OSError('Synthetic interrupted publication')
        def unreadable(path):
            if attempted and path == manifest:
                raise OSError('Synthetic readback unavailable')
            return read_bytes(path)
        with patch('features.notebooks.recovery.atomic_write_json', side_effect=reject_publication), \
                patch.object(Path, 'read_bytes', unreadable):
            with self.assertRaises(RecoveryIncomplete):
                draw_stroke(self.panel)
        self.assertTrue(document.dirty)
        self.assertTrue(self.panel.editor.checkpoint_unconfirmed)

    def assert_replacement_veto(self, *, synchronous=False):
        from mobile.app import _active_hosts
        from mobile.application_lifecycle import lifecycle
        from mobile.startup import StartupPhase
        panel, editor, document = self.panel, self.panel.editor, self.panel.document
        undo = editor.undo
        token = self.app.workspace.token(panel.session.id)
        identity = str(self.app.private_root.resolve()) + ':primary'
        with patch('mobile.startup.load_startup_models', side_effect=AssertionError('Model load entered')) as load, \
                patch.object(panel, 'dispose', wraps=panel.dispose) as dispose:
            with self.assertRaisesRegex(OSError, 'unconfirmed'):
                if synchronous:
                    self.incoming._async_startup = False
                    LogisticsMobile._prepare_startup_preferences(self.incoming, self.app.private_root)
                else:
                    self.app.loop.run_until_complete(LogisticsMobile._prepare_startup_phase(self.incoming, StartupPhase.PREFERENCES))
            load.assert_not_called()
            dispose.assert_not_called()
        lifecycle(self.incoming).abort_startup()
        self.assertIs(_active_hosts[identity], self.app)
        self.assertTrue(self.app.active_host)
        self.assertTrue(self.app.workspace.accepts(token))
        self.assertIs(panel.document, document)
        self.assertIs(panel.editor, editor)
        self.assertIs(editor.undo, undo)
        self.assertEqual(len(editor.undo), 1)
        self.assertEqual(len(editor.notebook.page(0).strokes), 1)
        self.assertFalse(panel.closed)
        self.assertTrue(document.dirty)
        self.assertTrue(editor.checkpoint_unconfirmed)

    def test_unconfirmed_notebook_vetoes_async_replacement_and_shell_abort(self):
        self.unconfirm_checkpoint()
        self.assert_replacement_veto()

    def test_unconfirmed_notebook_vetoes_synchronous_replacement(self):
        self.unconfirm_checkpoint()
        self.assert_replacement_veto(synchronous=True)

    def test_notebook_became_unconfirmed_during_preservation_callback(self):
        with patch.object(self.app.store, 'flush_checkpoints', side_effect=self.unconfirm_checkpoint):
            self.assert_replacement_veto()

    def test_notebook_became_unconfirmed_during_final_provider_access_check(self):
        from types import SimpleNamespace as NS
        from unittest.mock import AsyncMock, Mock
        checks = 0
        def provider_check(receipt):
            nonlocal checks
            checks += 1
            if checks == 3:
                self.unconfirm_checkpoint()
        private = NS(prepare_replacement=AsyncMock(return_value=object()),
                     require_replacement_safe=Mock(side_effect=provider_check),
                     _admit_retirement=Mock(), retire=Mock())
        with patch.object(self.app, 'private_sessions', private, create=True):
            self.assert_replacement_veto()
        self.assertEqual(checks, 3)
        private._admit_retirement.assert_not_called()
        private.retire.assert_not_called()

    def test_successful_notebook_save_allows_replacement_despite_stale_editor_flag(self):
        from mobile.app import _active_hosts
        from mobile.application_lifecycle import lifecycle
        from mobile.startup import StartupPhase
        self.unconfirm_checkpoint()
        document, editor = self.panel.document, self.panel.editor
        document.save()  # Existing owner clears dirty; the flag may remain until a command.
        self.assertFalse(document.dirty)
        self.assertTrue(editor.checkpoint_unconfirmed)
        with patch('mobile.startup.load_startup_models', return_value={'synthetic': True}) as load:
            self.app.loop.run_until_complete(LogisticsMobile._prepare_startup_phase(self.incoming, StartupPhase.PREFERENCES))
            load.assert_called_once()
        self.assertTrue(lifecycle(self.app).replaced)
        self.assertFalse(self.app.active_host)
        self.assertIsNone(self.panel.document)
        self.assertIs(_active_hosts[str(self.app.private_root.resolve()) + ':primary'], self.incoming)
        lifecycle(self.incoming).abort_startup()
