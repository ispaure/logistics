"""Preferences, secret boundaries and runnable actions use disposable fixtures."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from features.git.preferences import Preferences
from features.git.options import git_defaults
from features.git.accounts import change_credential
from features.git.runner import GitRunner, GitError
from test_git_ui import GitUITests
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt


class GitPreferenceTests(unittest.TestCase):
    def test_round_trip_and_reject_plaintext_secret_metadata(self):
        with TemporaryDirectory() as folder:
            prefs = Preferences(Path(folder) / 'git.json')
            prefs.options['commit_template'] = 'Subject\n\nDetails'
            prefs.options['accounts'] = [{'host': 'github.com', 'username': 'test', 'protocol': 'https', 'default': True, 'helper': 'osxkeychain'}]
            prefs.options['custom_actions'] = [{'caption': 'Show file', 'program': 'git', 'arguments': ['diff', '--', '{file}'], 'shortcut': ''}]
            prefs.save()
            other = Preferences(prefs.path)
            self.assertEqual(other.options, prefs.options)
            self.assertEqual(git_defaults(other.options)['credential.https://github.com.helper'], ['', 'osxkeychain'])
            other.options['accounts'][0]['token'] = 'test-secret'
            with self.assertRaises(ValueError): other.save()
            self.assertNotIn('test-secret', prefs.path.read_text())

    def test_credentials_use_stdin_and_only_secure_helpers(self):
        runner = GitRunner(); runner.config_options = {'credential.helper': 'store'}
        account = {'host': 'github.com', 'username': 'fixture', 'protocol': 'https', 'helper': 'osxkeychain'}
        with patch.object(runner, 'run') as run:
            change_credential(runner, account, 'fixture-secret')
            args, kwargs = run.call_args
            self.assertEqual(args[0], ['credential-osxkeychain', 'store'])
            self.assertNotIn('fixture-secret', repr(args))
            self.assertIn(b'password=fixture-secret', kwargs['input_data'])
            self.assertTrue(kwargs['sensitive'])
        self.assertEqual(runner.config_options, {'credential.helper': 'store'})
        account['helper'] = 'store'
        with self.assertRaises((ValueError, GitError)): change_credential(runner, account, 'secret')

    def test_sensitive_helper_output_never_reaches_log_or_result(self):
        output = []
        runner = GitRunner(progress=output.append)
        result = runner.run(['-c', 'import sys; v=sys.stdin.read(); print(v); print(v,file=sys.stderr)'],
                            external=sys.executable, input_data=b'fixture-secret', sensitive=True)
        self.assertEqual(result.stdout, b''); self.assertEqual(result.stderr, ''); self.assertEqual(output, [])


class PreferenceUITests(QtTestCase):
    setUpClass = classmethod(GitUITests.setUpClass.__func__)
    setUp = GitUITests.setUp
    release_page = GitUITests.release_page
    wait = GitUITests.wait
    open = GitUITests.open
    commit_fixture = GitUITests.commit_fixture
    def settings_panel(self):
        from features.git.ui.application_settings import GitPreferencesPanel
        panel = GitPreferencesPanel(preferences_path=self.page.preferences.path)
        self.addCleanup(panel.deleteLater)
        self.wait_panel(panel)
        return panel

    def wait_panel(self, panel):
        from time import monotonic, sleep
        deadline = monotonic() + 10
        while panel.worker:
            self.assertLess(monotonic(), deadline)
            self.app.processEvents(); sleep(.005)
        self.wait()

    def test_embedded_sections_apply_to_runtime_and_persist(self):
        self.open()
        panel = self.settings_panel(); form = panel.form
        self.assertNotIsInstance(panel, qt.QDialog)
        self.assertEqual([form.tabs.tabText(i) for i in range(form.tabs.count())],
                         ['General', 'Accounts', 'Commit', 'Diff', 'Git', 'Mercurial', 'Custom Actions', 'Update', 'Advanced'])
        self.assertFalse(form.tabs.tabBar().isHidden())
        self.assertTrue(all(form.tabs.tabIcon(i).isNull() for i in range(form.tabs.count())))
        form.template.setPlainText('Default message')
        form.fields['fixed_commit_font'].setChecked(True)
        form.fields['stage_double_click'].setChecked(True)
        form.fields['diff_limit_kb'].setValue(64)
        panel.save(); self.wait_panel(panel)
        self.assertEqual(panel.status.text(), 'Git preferences saved.')
        self.assertEqual(self.page.changes.message.toPlainText(), 'Default message')
        self.assertTrue(self.page.changes.stage_on_double_click)
        self.assertEqual(self.page.changes.message.column_guide, 72)
        self.assertEqual(Preferences(self.page.preferences.path).options['diff_limit_kb'], 64)
        self.assertFalse(self.page.preferences.warning)

    def test_git_preferences_action_requests_feature_settings(self):
        requested = []
        self.page.feature_settings_requested.connect(requested.append)
        self.page.application_settings_dialog()
        self.assertEqual(requested, ['git'])

    def test_saving_retained_preferences_preserves_new_bookmarks(self):
        self.open(); panel = self.settings_panel()
        self.page.preferences.remember(self.root / 'another-repo')
        self.page.preferences.save()
        panel.form.fields['stage_double_click'].setChecked(True)
        panel.save(); self.wait_panel(panel)
        saved = Preferences(self.page.preferences.path)
        self.assertEqual(saved.last_repository, str(self.root / 'another-repo'))
        self.assertTrue(any(entry['path'] == str(self.root / 'another-repo') for entry in saved.repositories))

    def test_discard_backs_up_original_bytes(self):
        self.commit_fixture(); file = self.repo.path / 'file.txt'
        original = file.read_bytes()
        file.write_bytes(b'modified\x00bytes')
        self.open()
        with patch.object(self.page, '_confirm', return_value=True):
            self.page.discard_dialog(self.page.snapshot.status.changes); self.wait()
        self.assertEqual(file.read_bytes(), original)
        folders = list((self.repo.path / '.git' / 'logistics-backups').iterdir())
        self.assertEqual(len(folders), 1)
        manifest = json.loads((folders[0] / 'paths.json').read_text())
        self.assertEqual(manifest, {'0.backup': 'file.txt'})
        self.assertEqual((folders[0] / '0.backup').read_bytes(), b'modified\x00bytes')

    def test_custom_action_arguments_preserve_spaces_and_shell_characters(self):
        self.commit_fixture(); self.open()
        output = self.root / 'arguments.json'
        entry = {'caption': 'Capture arguments', 'program': sys.executable, 'arguments': [
            '-c', 'import sys,json; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))',
            str(output), '{repo}', 'a space & $(echo wrong)'], 'shortcut': ''}
        self.page.run_custom_action(entry); self.wait()
        self.assertEqual(json.loads(output.read_text()), [str(self.repo.path.resolve()), 'a space & $(echo wrong)'])

    def test_global_identity_is_written_only_when_explicitly_enabled(self):
        import os
        global_config = self.root / 'global.gitconfig'
        global_config.write_text('[user]\nname = Original\nemail = original@example.invalid\n')
        with patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': str(global_config)}):
            self.open(); panel = self.settings_panel()
            panel.form.author.setText('Changed'); panel.form.email.setText('changed@example.invalid')
            panel.save(); self.wait_panel(panel)
            self.assertIn('name = Original', global_config.read_text())
            panel.form.modify_global.setChecked(True)
            panel.form.author.setText('Changed'); panel.form.email.setText('changed@example.invalid')
            panel.save(); self.wait_panel(panel)
            self.assertIn('name = Changed', global_config.read_text())
            self.assertEqual(self.repo.config_value('user.name', local=True), 'UI Test')

    def test_clean_file_edit_refreshes_status_automatically(self):
        from time import monotonic, sleep
        self.commit_fixture(); self.open()
        (self.repo.path / 'file.txt').write_text('first edit\n')
        deadline = monotonic() + 5
        while not self.page.snapshot.status.changes or self.page.busy:
            self.assertLess(monotonic(), deadline)
            self.app.processEvents(); sleep(.01)
        self.assertEqual(self.page.snapshot.status.changes[0].path, 'file.txt')

    def test_manual_refresh_does_not_retrigger_itself(self):
        from time import monotonic, sleep
        self.commit_fixture(); self.open()
        # Make the index's stat data stale, the condition under which ordinary
        # git status would rewrite it and notify the .git directory watcher.
        file = self.repo.path / 'file.txt'
        file.touch()
        index = self.repo.path / '.git' / 'index'
        original_index = index.read_bytes()
        with patch.object(self.page, '_job', wraps=self.page._job) as jobs:
            self.page.refresh(); self.wait()
            deadline = monotonic() + 2
            while monotonic() < deadline:
                self.app.processEvents(); sleep(.01)
            self.wait()
            # The real file edit may also request one debounced refresh.
            self.assertLessEqual(jobs.call_count, 2)
        self.assertEqual(index.read_bytes(), original_index)
        self.assertFalse(self.page.file_timer.isActive())
        self.assertFalse(self.page._refresh_pending)


del GitUITests
