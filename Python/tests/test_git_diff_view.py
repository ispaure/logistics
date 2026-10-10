"""Diff presentation retains content while hiding patch transport metadata."""
import unittest
from features.git.diff_view import present_diff


class DiffViewTests(unittest.TestCase):
    def test_multiple_hunks_keep_positions_content_and_newline_notice(self):
        patch = ('diff --git a/file b/file\nindex 123..456 100644\n--- a/file\n+++ b/file\n'
                 '@@ -8,2 +9,2 @@ function\n context\n-old\n+new\n'
                 '@@ -30 +31,2 @@\n-old again\n+new again\n+extra\n\\ No newline at end of file\n')
        view = present_diff(patch)
        self.assertEqual(len(view.hunks), 2)
        self.assertEqual((view.added, view.removed), (3, 2))
        self.assertEqual([(line.old, line.new) for line in view.lines if line.text == ' context'], [('8', '9')])
        self.assertIn('No newline at end of file', view.text)
        self.assertIn('Original 30 → New 31–32', view.text)
        for header in ('diff --git', 'index 123', '--- a/file', '+++ b/file', '@@'):
            self.assertNotIn(header, view.text)

    def test_added_deleted_binary_and_mode_only_files_have_friendly_details(self):
        for header, label in (('new file mode 100644', 'Added file'),
                              ('deleted file mode 100644', 'Deleted file'),
                              ('old mode 100644\nnew mode 100755', 'File permissions changed'),
                              ('Binary files a/file and b/file differ', 'Binary file changed')):
            with self.subTest(header=header):
                view = present_diff('diff --git a/file b/file\n' + header + '\n')
                self.assertIn(label, view.text)
                self.assertNotIn('diff --git', view.text)

    def test_patch_like_file_contents_and_truncation_are_preserved(self):
        patch = ('diff --git a/file b/file\nnew file mode 100644\n--- /dev/null\n+++ b/file\n'
                 '@@ -0,0 +1,3 @@\n+++ real code\n+diff --git content\n+@@ content\n[Diff truncated to 1 MiB]')
        view = present_diff(patch)
        self.assertEqual(view.added, 3)
        self.assertIn('+++ real code', view.text)
        self.assertEqual(view.lines[1].new, '1')
        self.assertIn('truncated', view.summary)

    def test_raw_patch_retains_exact_text_and_same_line_positions(self):
        patch = 'diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -2 +2 @@\n-before\n+after\n'
        view = present_diff(patch)
        self.assertEqual(view.raw_text, patch)
        self.assertEqual([(line.old, line.new, line.kind) for line in view.raw_lines if line.kind == 'remove'], [('2', '', 'remove')])
        self.assertEqual([(line.old, line.new, line.kind) for line in view.raw_lines if line.kind == 'add'], [('', '2', 'add')])

    def test_multiple_files_and_combined_merge_diffs_remain_identifiable(self):
        patch = ('diff --git a/first b/first\n--- a/first\n+++ b/first\n@@ -1 +1 @@\n-a\n+b\n'
                 'diff --git a/second b/second\n--- a/second\n+++ b/second\n@@ -1 +1 @@\n-c\n+d\n')
        view = present_diff(patch)
        self.assertIn('first', view.hunks[0][1])
        self.assertIn('second', view.hunks[1][1])
        combined = 'diff --cc file\nindex 123,456..789\n@@@ -1,1 -1,1 +1,2 @@@\n++conflict\n'
        view = present_diff(combined)
        self.assertIn('Combined merge diff', view.text)
        self.assertEqual(view.raw_text, combined)

    def test_incomplete_hunks_show_notice_instead_of_claiming_complete_review(self):
        view = present_diff('diff --git a/a b/a\n@@ -1,4 +1,4 @@\n context\n[Diff truncated]')
        self.assertIn('Incomplete patch', view.summary)
