"""Real Git conflicts: raw stage inputs, safe saving and optional staging."""
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from features.git.repository import Repository, initialize
from features.git.runner import GitError
from commonUtils.persistence.text import FileConflictError


@unittest.skipUnless(shutil.which('git'), 'Git required')
class GitMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.repo=Repository(initialize(Path(self.temp.name)/'repo'))
        for key,value in [('user.name','Test'),('user.email','test@example.invalid'),('commit.gpgsign','false'),
                          ('core.autocrlf','false'),('core.hooksPath',str(Path(self.temp.name)/'hooks'))]:
            self.repo.run(['config',key,value])
        self.repo.run(['symbolic-ref','HEAD','refs/heads/main'])
        self.path=self.repo.path/'[literal].txt'
        self.commit('base\n'); self.repo.create_branch('incoming'); self.commit('incoming\n')
        self.repo.switch('main'); self.commit('local\n')
        with self.assertRaises(GitError): self.repo.merge('incoming')

    def commit(self,text):
        self.path.write_text(text,encoding='utf-8',newline='')
        self.repo.stage([self.path.name]); self.repo.commit('Change')

    def test_comparison_reads_actual_index_head_and_worktree_versions(self):
        self.path.write_text('resolved\n'); self.repo.stage([self.path.name])
        self.assertEqual(self.repo.comparison_inputs(self.path.name,staged=True),('local\n','resolved\n'))
        self.path.write_text('working\n')
        self.assertEqual(self.repo.comparison_inputs(self.path.name),('resolved\n','working\n'))
        self.path.unlink()
        self.assertEqual(self.repo.comparison_inputs(self.path.name),('resolved\n',''))

    def test_read_save_and_stage(self):
        inputs=self.repo.conflict_inputs(self.path.name)
        self.assertEqual((inputs.base,inputs.left,inputs.right),('base\n','local\n','incoming\n'))
        self.repo.save_conflict(inputs,'😀 result\n',stage=True)
        self.assertEqual(self.path.read_text(),'😀 result\n')
        self.assertFalse(any(change.conflict for change in self.repo.status().changes))

    def test_save_without_stage_and_preserve_line_endings(self):
        self.path.write_bytes(self.path.read_bytes().replace(b'\n',b'\r\n'))
        inputs=self.repo.conflict_inputs(self.path.name)
        self.repo.save_conflict(inputs,'result\n')
        self.assertEqual(self.path.read_bytes(),b'result\r\n')
        self.assertTrue(any(change.conflict for change in self.repo.status().changes))

    def test_stale_disk_and_index_are_rejected(self):
        inputs=self.repo.conflict_inputs(self.path.name)
        self.path.write_text('external\n')
        with self.assertRaises(FileConflictError): self.repo.save_conflict(inputs,'result\n',stage=True)
        self.assertEqual(self.path.read_text(),'external\n')
        inputs=self.repo.conflict_inputs(self.path.name)
        self.repo.stage([self.path.name])
        with self.assertRaises(GitError): self.repo.save_conflict(inputs,'result\n')
        self.assertEqual(self.path.read_text(),'external\n')

    def test_symlink_replacement_and_conversion_filter_are_rejected(self):
        inputs=self.repo.conflict_inputs(self.path.name)
        outside=Path(self.temp.name)/'outside'; outside.write_bytes(self.path.read_bytes())
        self.path.unlink(); self.path.symlink_to(outside)
        with self.assertRaises(GitError): self.repo.save_conflict(inputs,'result\n')
        self.assertEqual(outside.read_bytes(),inputs.working.original)
        self.path.unlink(); self.path.write_bytes(inputs.working.original)
        (self.repo.path/'.gitattributes').write_text('*.txt filter=custom\n')
        with self.assertRaisesRegex(GitError,'conversion'): self.repo.conflict_inputs(self.path.name)

    def test_missing_worktree_is_not_permission_to_overwrite_a_new_file(self):
        self.path.unlink(); inputs=self.repo.conflict_inputs(self.path.name)
        self.path.write_text('new file\n')
        with self.assertRaises(FileConflictError): self.repo.save_conflict(inputs,'result\n')
        self.assertEqual(self.path.read_text(),'new file\n')
