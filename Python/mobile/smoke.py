"""Run document/core fixtures inside real mobile interpreters, without a UI."""

# TEST_STAGE = TestStage.SMOKE
import argparse
import faulthandler
import importlib.abc
import json
from pathlib import Path
import platform
import re
import sys
import unittest

PREFIX = 'LOGISTICS_MOBILE_RESULT='
FORBIDDEN = {'PySide6', 'PIL', 'patoolib', 'pyzipper', 'toga', 'java', 'rubicon'}
EXPECTED_TESTS = (
    'test_cached_checkpoint_still_rejects_symbolic_link',
    'test_changed_text_name_and_saved_baseline_are_checkpointed',
    'test_failed_durable_checkpoint_retries_even_after_file_publication',
    'test_missing_edited_and_replaced_recovery_files_force_checkpoint',
    'test_unchanged_checkpoint_skips_serialization_and_disk_flushes',
    'test_android_adapter_closes_cursor_and_stream_on_consumer_failure',
    'test_bom_encoding_and_endings_survive_recovery_and_save',
    'test_changed_or_deleted_private_file_preserves_draft_and_requires_copy',
    'test_discard_preserves_external_change_and_deleted_source',
    'test_delete_removes_saved_bytes_and_unsaved_recovery_only_for_target',
    'test_failed_delete_keeps_recovery_and_never_follows_link',
    'test_failed_checkpoint_and_failed_save_keep_original_and_recovery',
    'test_failed_discard_retains_draft_and_baseline',
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
    'test_legacy_visibility_never_survives_restart_or_save',
    'test_preference_writes_filter_session_only_credential_associations',
    'test_mobile_comic_reads_native_page_bytes_in_natural_order',
    'test_large_comic_streaming_keeps_unrelated_members_and_bounds_page_reads',
    'test_mobile_epub_import_navigation_progress_and_bookmarks_preserve_source',
    'test_mobile_epub_sanitizer_removes_active_html_and_external_resources',
    'test_svg_external_cover_does_not_fetch_or_leave_an_empty_page',
    'test_svg_wrapped_opening_cover_preserves_only_the_offline_raster',
    'test_mobile_reader_rejects_unsafe_archives_and_oversized_image_dimensions',
    'test_mobile_chat_cancel_interrupts_blocked_read_and_rejects_redirects_tools',
    'test_mobile_chat_profile_never_accepts_stored_api_keys',
    'test_mobile_chat_records_recover_drafts_interruptions_and_reject_conflicts',
    'test_mobile_chat_refresh_and_stream_use_only_configured_endpoint',
    'test_mobile_api_urls_default_to_v1_and_preserve_custom_paths',
    'test_mobile_timeouts_distinguish_connect_and_generation',
    'test_mobile_cloud_bridge_frees_success_and_invalid_responses',
    'test_mobile_cloud_downloads_recover_only_complete_private_copies',
    'test_mobile_cloud_package_uses_scoped_read_without_saving_credentials',
    'test_native_adapter_namespaces_remain_compatible_with_existing_keys',
    'test_mobile_vault_key_is_device_owned_and_restored_without_password',
    'test_mobile_vault_missing_corrupt_linked_metadata_never_replaces_keys',
    'test_metadata_plan_and_verified_transaction_preserve_comic_pages',
    'test_malformed_comic_metadata_does_not_prevent_reading',
    'test_verified_save_conflict_cancellation_and_encoding',
    'test_text_and_comic_reads_are_memory_only',
    'test_ini_reader_is_editable_memory_only_and_preserves_line_endings',
    'test_epub_source_reads_without_plaintext_files',
    'test_existing_ciphertext_storage_and_locked_listing',
    'test_lock_unloads_credentials_without_forgetting_saved_vault',
    'test_privacy_gate_tracks_only_successful_session_loads_across_clients',
    'test_native_credential_replacement_invalidates_every_client',
    'test_retired_mirror_operations_never_reach_native_bridge',
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


def verify_source(source, target, local_sha256=''):
    if target == 'host':
        if local_sha256:
            raise ValueError('Local mobile snapshot verification requires an actual mobile target.')
        return
    if not isinstance(source, dict):
        raise RuntimeError('Mobile evidence requires a staged source manifest.')
    if local_sha256:
        if not re.fullmatch('[0-9a-f]{64}',local_sha256) or source.get('source_sha256')!=local_sha256:
            raise RuntimeError('Local mobile snapshot fingerprint differs from its staged source.')
    elif source.get('dirty') is not False:
        raise RuntimeError('Mobile evidence requires a clean staged source manifest.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('host', 'android', 'ios'), required=True)
    parser.add_argument('--local-source-sha256', default='', help='Explicit local-only exact staged fingerprint; never hosted release evidence')
    args = parser.parse_args(argv)
    if args.target != 'host' and sys.platform != args.target:
        parser.error('Expected an actual ' + args.target + ' interpreter; got ' + sys.platform)
    if args.target == 'host' and sys.platform not in ('darwin', 'win32', 'linux'):
        parser.error('Host mode is only for desktop harness checks.')
    if any(name.split('.')[0] in FORBIDDEN for name in sys.modules):
        raise RuntimeError('Run this suite in a fresh interpreter.')
    source_path = Path(__file__).with_name('source.json')
    source = json.loads(source_path.read_text()) if source_path.exists() else None
    verify_source(source,args.target,args.local_source_sha256)
    blocker = RejectDesktop()
    sys.meta_path.insert(0, blocker)
    if args.target == 'host':
        faulthandler.dump_traceback_later(20)
    try:
        from test_mobile_documents import MobileDocumentsTests
        from portable_documents import PortableDocuments
        from test_mobile_hub import MobileHubTests
        from test_mobile_readers import MobileReaderTests
        from test_mobile_chat import MobileChatTests
        from test_mobile_cloud import MobileCloudTests
        from test_mobile_vault import MobileVaultTests
        from test_mobile_localcrypt import MobileLocalCryptTests
        RuntimeChecks.target = args.target
        suite = unittest.TestSuite()
        for case in (MobileDocumentsTests, PortableDocuments, MobileHubTests, MobileReaderTests, MobileChatTests, MobileCloudTests, MobileVaultTests, MobileLocalCryptTests, RuntimeChecks):
            suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
        if sorted(test._testMethodName for test in suite) != sorted(EXPECTED_TESTS):
            discovered = {test._testMethodName for test in suite}
            missing = sorted(set(EXPECTED_TESTS) - discovered)
            undeclared = sorted(discovered - set(EXPECTED_TESTS))
            raise RuntimeError(f'Mobile fixture discovery differs from the declared evidence contract: '
                               f'missing={missing}, undeclared={undeclared}.')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        report = dict(schema=1, suite='logistics-mobile-documents', target=args.target,
                      sys_platform=sys.platform, environment=environment(),
                      python=platform.python_version(), machine=platform.machine(),
                      tests_run=result.testsRun, expected_tests=list(EXPECTED_TESTS),
                      failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                      success=result.wasSuccessful() and not result.skipped,
                      source=source, native_picker_tested=False)
        if args.local_source_sha256:
            report['local_source_sha256'] = args.local_source_sha256
        print(PREFIX + json.dumps(report, sort_keys=True), flush=True)
        return 0 if report['success'] else 1
    finally:
        if args.target == 'host':
            faulthandler.cancel_dump_traceback_later()
        sys.meta_path.remove(blocker)


if __name__ == '__main__':
    raise SystemExit(main())
