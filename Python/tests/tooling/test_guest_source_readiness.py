"""Real local Git-object repair; no VM, network, installation or runtime edits."""
import json
from pathlib import Path
from shutil import copytree
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import build_manager
from commonUtils.testing.stages import TestStage
from logistics_build import guest_source_readiness as owner
from logistics_build.build_project import LogisticsProject

TEST_STAGE=TestStage.REGRESSION


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
        '-c','commit.gpgsign=false',*args],stderr=subprocess.DEVNULL,text=True).strip()


class GuestSourceReadinessTests(unittest.TestCase):
    repository = 'https://github.com/fixture/manager.git'

    @classmethod
    def setUpClass(cls):
        temporary = TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        shared = root / 'cu-prototype'
        manager = root / 'manager-prototype'
        shared.mkdir()
        manager.mkdir()
        git(shared, 'init', '-q')
        (shared / 'source').write_text('old')
        git(shared, 'add', '.')
        git(shared, 'commit', '-qm', 'old')
        cls.old_cu = git(shared, 'rev-parse', 'HEAD')
        git(manager, 'init', '-q')
        package = manager / 'Python/build_manager'
        package.mkdir(parents=True)
        (package / '__init__.py').write_text('# fixture\n')
        git(manager, 'add', '.')
        git(manager, 'update-index', '--add', '--cacheinfo', '160000,' + cls.old_cu + ',Python/commonUtils')
        git(manager, 'commit', '-qm', 'old')
        cls.old = git(manager, 'rev-parse', 'HEAD')

        # Capture the old object stores before either repository has a new commit.
        cls.old_checkout = root / 'old'
        git(root, 'clone', '-q', str(manager), str(cls.old_checkout))
        git(root, 'clone', '-q', str(shared), str(cls.old_checkout / 'Python/commonUtils'))
        (shared / 'source').write_text('new')
        git(shared, 'add', '.')
        git(shared, 'commit', '-qm', 'new')
        cls.new_cu = git(shared, 'rev-parse', 'HEAD')
        git(manager, 'update-index', '--add', '--cacheinfo', '160000,' + cls.new_cu + ',Python/commonUtils')
        (manager / 'new').write_text('new')
        git(manager, 'add', 'new')
        git(manager, 'commit', '-qm', 'new')
        cls.new = git(manager, 'rev-parse', 'HEAD')
        cls.new_checkout = root / 'new'
        git(root, 'clone', '-q', str(manager), str(cls.new_checkout))
        git(root, 'clone', '-q', str(shared), str(cls.new_checkout / 'Python/commonUtils'))
        for checkout in (cls.old_checkout, cls.new_checkout):
            git(checkout, 'remote', 'set-url', 'origin', cls.repository)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        cache = owner.private(self.root) / 'tooling'
        self.target = cache / self.old
        self.current = cache / self.new
        # Each case can change refs, objects and metadata without touching the
        # templates or any other case. Do not share Git objects via hardlinks.
        copytree(self.old_checkout, self.target)
        copytree(self.new_checkout, self.current)
        self.declared = dict(schema=1, adapter_api=1, repository=self.repository, revision=self.new)
        self.snapshot = self.root / 'snapshot'
        self.snapshot.mkdir()
        (self.snapshot / 'build-manager-dependency.json').write_text(json.dumps(self.declared))
        self.proof = self.target.with_suffix('.ownership.json')
        self.proof.write_text(json.dumps(dict(self.declared, root=str(self.root), revision=self.old)))
        self.enterContext(patch.object(build_manager, '__file__', str(self.current / 'Python/build_manager/__init__.py')))

    def repair(self):return owner.ensure(self.root,self.snapshot,self.target,{})

    def unchanged(self):
        heads = (git(self.target, 'rev-parse', 'HEAD'), git(self.target / 'Python/commonUtils', 'rev-parse', 'HEAD'))
        self.assertEqual(heads, (self.old, self.old_cu))
        self.assertEqual(git(self.target,'status','--porcelain','--untracked-files=all'),'')
        self.assertEqual(git(self.target/'Python/commonUtils','status','--porcelain','--untracked-files=all'),'')

    def test_future_pin_and_missing_cu_repair_exact_objects_without_head_or_fetchhead_changes(self):
        self.assertFalse(owner.available(self.target,self.new));self.assertFalse(owner.available(self.target/'Python/commonUtils',self.new_cu))
        fetchhead=self.target/'.git/FETCH_HEAD';fetchhead.write_text('preserved fixture\n')
        result=self.repair();self.assertEqual(result['status'],'objects-restored');self.assertEqual(result['commonUtils'],self.new_cu)
        self.assertEqual(fetchhead.read_text(),'preserved fixture\n');self.unchanged()
        self.assertEqual(owner.verify(self.target,self.new,pinned_source=True),(self.new,self.new_cu))

    def test_only_missing_cu_is_fetched_and_repeat_readiness_is_read_only(self):
        git(self.target,'fetch','--no-write-fetch-head','--no-tags',self.current.as_uri(),self.new)
        original=owner.subprocess.run;calls=[]
        def record(args,**kwargs):
            if 'fetch' in args:calls.append((args,kwargs))
            return original(args,**kwargs)
        with patch.object(owner.subprocess,'run',side_effect=record):
            self.repair();self.assertEqual(self.repair()['status'],'verified')
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][0][-1],self.new_cu)
        self.assertEqual(calls[0][1]['env']['GIT_ALLOW_PROTOCOL'],'file');self.assertLessEqual(calls[0][1]['timeout'],15);self.unchanged()

    def test_unowned_or_arbitrary_paths_are_never_fetched(self):
        self.proof.unlink()
        original=owner.subprocess.run
        def reject_fetch(args,**kwargs):
            self.assertNotIn('fetch',args);return original(args,**kwargs)
        with patch.object(owner.subprocess,'run',side_effect=reject_fetch),self.assertRaisesRegex(ValueError,'Update project tooling'):self.repair()
        self.unchanged()

    def test_mismatched_installed_candidate_is_never_a_repair_source(self):
        with patch.object(build_manager,'__file__',str(self.target/'Python/build_manager/__init__.py')),self.assertRaises(ValueError):self.repair()
        self.assertFalse(owner.available(self.target,self.new));self.unchanged()

    def test_dirty_cache_is_not_mutated_and_local_worktree_mode_is_preserved(self):
        path=self.target/'new-untracked';path.write_text('keep')
        with self.assertRaises(ValueError):self.repair()
        with patch.object(owner,'installed_source') as installed:
            self.assertEqual(owner.ensure(self.root,self.snapshot,self.target,{'run_overrides':{'testing.manager_source':'working-tree-local'}})['status'],'not-needed')
        installed.assert_not_called();self.assertEqual(path.read_text(),'keep');self.assertFalse(owner.available(self.target,self.new))

    def test_linked_marker_or_checkout_is_not_repaired(self):
        original=self.proof.read_text();self.proof.unlink();outside=self.root/'outside-proof';outside.write_text(original)
        self.proof.symlink_to(outside)
        with self.assertRaises(ValueError):self.repair()
        self.assertFalse(owner.available(self.target,self.new));self.unchanged()

    def test_local_fetch_failure_fails_fast_without_runtime_changes(self):
        original=owner.subprocess.run
        def fail(args,**kwargs):
            if 'fetch' in args:return subprocess.CompletedProcess(args,128,'','private diagnostic not exposed')
            return original(args,**kwargs)
        with patch.object(owner.subprocess,'run',side_effect=fail),self.assertRaisesRegex(ValueError,'clear the explicit'):self.repair()
        self.unchanged()

    def test_vm_source_failure_allows_inventory_but_blocks_guest_start(self):
        project=LogisticsProject(self.root);project.private=self.root/'private'
        source=dict(fingerprint='fixture',selection='fixture',run_overrides={})
        options={'tools.manager_checkout':str(self.target),'vm.fedora_mode':'guest','vm.fedora':'fixture','vm.windows':'fixture'}
        for target in ('linux','windows'):
            with self.subTest(target=target),patch('logistics_build.build_project.materialize') as snapshot,patch.object(owner,'ensure',side_effect=ValueError('blocked')) as ensure,patch('build_manager.parallels.Parallels') as provider:
                with self.assertRaisesRegex(ValueError,'blocked'):
                    project.local_vm_plan('Test',target,dict(source),self.root/'work',options,None)
                provider.return_value.selected.assert_called_once_with('fixture')
                snapshot.assert_called_once_with(self.root,project.private/'snapshots/fixture','fixture',expected=source)
                ensure.assert_called_once_with(self.root,project.private/'snapshots/fixture',str(self.target),source)
                provider.return_value.start.assert_not_called()
                provider.return_value.execute.assert_not_called()
                provider.return_value.run_owned.assert_not_called()

    def test_unavailable_guest_inventory_does_not_materialize_or_repair(self):
        project=LogisticsProject(self.root);project.private=self.root/'private'
        source=dict(fingerprint='fixture',selection='fixture',run_overrides={})
        options={'tools.manager_checkout':str(self.target),'vm.fedora_mode':'guest','vm.fedora':'fixture','vm.windows':'fixture'}
        for target in ('linux','windows'):
            with self.subTest(target=target),patch('logistics_build.build_project.materialize') as snapshot,patch.object(owner,'ensure') as ensure,patch('build_manager.parallels.Parallels') as provider:
                provider.return_value.selected.side_effect=ValueError('Guest unavailable')
                with self.assertRaisesRegex(ValueError,'Guest unavailable'):
                    project.local_vm_plan('Test',target,dict(source),self.root/'work',options,None)
                snapshot.assert_not_called()
                ensure.assert_not_called()
                provider.return_value.start.assert_not_called()
                provider.return_value.execute.assert_not_called()

    def test_transfer_time_rechecks_same_owned_source_and_local_overlay_bypasses_repair(self):
        self.assertEqual(owner.before_transfer(self.snapshot,self.target)['status'],'objects-restored');self.unchanged()
        with patch.object(owner,'ensure') as ensure:
            self.assertEqual(owner.before_transfer(self.snapshot,self.target,working_tree='intentional-overlay')['status'],'not-needed')
        ensure.assert_not_called()

    def test_redirected_gitdir_and_object_pack_are_rejected_without_external_objects(self):
        import shutil
        metadata=self.target/'.git';outside=self.root/'external-git';shutil.move(metadata,outside)
        metadata.symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'metadata|Linked'):self.repair()
        self.assertFalse(owner.available(self.target,self.new))
        metadata.unlink();shutil.move(outside,metadata)
        pack=metadata/'objects/pack';outside_pack=self.root/'external-pack';shutil.move(pack,outside_pack)
        pack.symlink_to(outside_pack,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'object-store'):self.repair()
        self.assertFalse(owner.available(self.target,self.new));self.unchanged()

    def test_git_routing_override_is_rejected_before_any_git_or_fetch(self):
        with patch.dict('os.environ',GIT_OBJECT_DIRECTORY=str(self.root/'external-objects')), \
                patch.object(owner.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'routing/configuration'):self.repair()
        run.assert_not_called();self.unchanged()

    def test_arbitrary_developer_checkout_outside_owned_cache_is_not_repaired(self):
        developer=self.root/'developer';self.target.rename(developer);self.target=developer
        with self.assertRaisesRegex(ValueError,'ownership proof'):self.repair()
        self.assertFalse(owner.available(developer,self.new));self.unchanged()

    def test_failure_names_declared_revision_checkout_and_bounded_reason(self):
        with patch.object(build_manager,'__file__',str(self.target/'Python/build_manager/__init__.py')):
            with self.assertRaises(ValueError) as caught:self.repair()
        text=str(caught.exception)
        self.assertIn(self.new,text);self.assertIn(str(self.target),text);self.assertIn('Imported SDK',text)
        self.assertNotIn('private diagnostic',text)
