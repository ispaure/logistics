"""Run document/core fixtures inside real mobile interpreters, without a UI."""
import argparse
import importlib.abc
import json
from pathlib import Path
import platform
import sys
import unittest

PREFIX = 'LOGISTICS_MOBILE_RESULT='
FORBIDDEN = {'PySide6', 'PIL', 'patoolib', 'pyzipper', 'toga', 'java', 'rubicon'}
EXPECTED_TESTS = (
    'test_android_adapter_closes_cursor_and_stream_on_consumer_failure',
    'test_bom_encoding_and_endings_survive_recovery_and_save',
    'test_changed_or_deleted_private_file_preserves_draft_and_requires_copy',
    'test_failed_checkpoint_and_failed_save_keep_original_and_recovery',
    'test_import_consumes_a_scoped_stream_and_never_modifies_source',
    'test_invalid_records_names_large_documents_and_links_are_preserved',
    'test_ios_adapter_balances_scope_on_success_and_read_failure',
    'test_private_creation_works_without_hard_links_and_hides_incomplete_records',
    'test_recovery_after_process_recreation_preserves_unsaved_text',
    'test_comic_pages_and_metadata_work_without_image_decoder',
    'test_epub_read_and_metadata_save_preserve_resources',
    'test_markdown_and_text_save_reject_stale_changes',
    'test_mobile_markdown_preview_is_offline_and_escapes_active_content',
    'test_mobile_preferences_preserve_invalid_and_concurrent_files',
    'test_mobile_preferences_survive_restart_without_hard_links',
    'test_mobile_comic_reads_native_page_bytes_in_natural_order',
    'test_mobile_epub_import_navigation_progress_and_bookmarks_preserve_source',
    'test_mobile_epub_sanitizer_removes_active_html_and_external_resources',
    'test_mobile_reader_rejects_unsafe_archives_and_oversized_image_dimensions',
    'test_import_boundary', 'test_runtime_identity',
)


class RejectDesktop(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in FORBIDDEN:
            raise ImportError('Mobile core excludes ' + fullname)
        return None


def environment():
    if sys.platform == 'ios':
        return 'ios-simulator' if platform.ios_ver().is_simulator else 'ios-device'
    if sys.platform == 'android':
        return 'android-emulator' if platform.android_ver().is_emulator else 'android-device'
    return 'desktop-harness'


class RuntimeChecks(unittest.TestCase):
    target = 'host'

    def test_runtime_identity(self):
        from commonUtils.runtime.platform import get_os, OS
        if self.target == 'host':
            self.assertIn(get_os(), (OS.MAC, OS.WIN, OS.LINUX))
        else:
            self.assertEqual(sys.platform, self.target)
            self.assertIs(get_os(), {'ios': OS.IOS, 'android': OS.ANDROID}[self.target])
            self.assertEqual(environment(), {'ios': 'ios-simulator', 'android': 'android-emulator'}[self.target])

    def test_import_boundary(self):
        self.assertFalse(any(name.split('.')[0] in FORBIDDEN for name in sys.modules))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('host', 'android', 'ios'), required=True)
    args = parser.parse_args(argv)
    if args.target != 'host' and sys.platform != args.target:
        parser.error('Expected an actual ' + args.target + ' interpreter; got ' + sys.platform)
    if args.target == 'host' and sys.platform not in ('darwin', 'win32', 'linux'):
        parser.error('Host mode is only for desktop harness checks.')
    if any(name.split('.')[0] in FORBIDDEN for name in sys.modules):
        raise RuntimeError('Run this suite in a fresh interpreter.')
    source_path = Path(__file__).with_name('source.json')
    source = json.loads(source_path.read_text()) if source_path.exists() else None
    if args.target != 'host' and (not source or source.get('dirty') is not False):
        raise RuntimeError('Mobile evidence requires a clean staged source manifest.')
    blocker = RejectDesktop()
    sys.meta_path.insert(0, blocker)
    try:
        from test_mobile_documents import MobileDocumentsTests
        from portable_documents import PortableDocuments
        from test_mobile_hub import MobileHubTests
        from test_mobile_readers import MobileReaderTests
        RuntimeChecks.target = args.target
        suite = unittest.TestSuite()
        for case in (MobileDocumentsTests, PortableDocuments, MobileHubTests, MobileReaderTests, RuntimeChecks):
            suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        report = dict(schema=1, suite='logistics-mobile-documents', target=args.target,
                      sys_platform=sys.platform, environment=environment(),
                      python=platform.python_version(), machine=platform.machine(),
                      tests_run=result.testsRun, expected_tests=list(EXPECTED_TESTS),
                      failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                      success=result.wasSuccessful() and not result.skipped,
                      source=source, native_picker_tested=False)
        print(PREFIX + json.dumps(report, sort_keys=True), flush=True)
        return 0 if report['success'] else 1
    finally:
        sys.meta_path.remove(blocker)


if __name__ == '__main__':
    raise SystemExit(main())
