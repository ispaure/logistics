"""Project policy for execution choices, run notes and release names."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from build_manager import Phase,Plan
from build_manager.journeys import validate_plan
from Scripts import manager_journeys,release_naming
import test_manager_journeys as fixtures


class RunRequestTests(unittest.TestCase):
    setUp=fixtures.JourneyAdapterTests.setUp
    make=fixtures.JourneyAdapterTests.make

    def test_run_notes_and_groups_are_captured_without_changing_defaults(self):
        self.values['testflight.what_to_test']='Saved notes'
        overrides={'testflight.what_to_test':'Try the new editor café','testflight.external_group':'Internal QA'}
        with patch('Scripts.build_project.manager_settings.settings',side_effect=lambda root,overrides=None:(dict(self.values,**(overrides or {})),{})):
            plan=self.make(platforms=['ios'],destinations=['testflight'],run_overrides=overrides)
        self.assertEqual(self.values['testflight.what_to_test'],'Saved notes')
        self.assertEqual(plan.source['run_overrides'],overrides)
        self.assertEqual(plan.source['effective_settings']['values']['testflight.what_to_test'],overrides['testflight.what_to_test'])
        self.assertIn('Internal QA',plan.journey['destinations']['testflight']['identity'])
        for phase in plan.phases:
            if 'LOGISTICS_MANAGER_PROFILE' in phase.environment:
                import json
                saved=json.loads(Path(phase.environment['LOGISTICS_MANAGER_PROFILE']).read_text())
                self.assertEqual(saved['values']['testflight.what_to_test'],overrides['testflight.what_to_test'])
        with self.assertRaises(ValueError):manager_journeys.run_values({'auth.key_reference':'arbitrary'})

    def test_mixed_local_and_github_validation_uses_explicit_dispatch_gates(self):
        original=self.project._make_plan
        def branch(operation,target,backend,**options):
            if backend!='GitHub':return original(operation,target,backend,**options)
            source=options['_context'].source(self.project,options['revision'])
            phase=Phase('hosted-checks',(sys.executable,'-c','pass'),str(self.root),effect='dispatch',kind='validation-dispatch')
            return Plan('Logistics','Test',source,(phase,),str(self.root/target),backend='GitHub',effect='dispatch')
        with patch.object(self.project,'_make_plan',side_effect=branch):
            plan=self.make('validate',platforms=['macos','ios'],destinations=[],backends={'macos':'GitHub','ios':'This Mac — iOS Simulators'})
        validate_plan(plan)
        self.assertEqual(plan.journey['executions']['macos']['backend'],'GitHub')
        self.assertTrue(plan.journey['executions']['macos']['steps'])
        self.assertEqual(plan.journey['executions']['ios']['steps'],[])
        self.assertFalse(any(phase.effect in {'publish','upload','deploy'} for phase in plan.phases))

    def test_tester_delivery_does_not_silently_replace_hosted_validation_with_local(self):
        with self.assertRaisesRegex(ValueError,'local native validation'):
            self.make(platforms=['ios'],destinations=['testflight'],backends={'ios':'GitHub'})

    def test_automatic_tag_uses_project_version_and_never_creates_a_tag(self):
        with patch('Scripts.release_naming.subprocess.check_output',return_value='v1.2.3-alpha.2\nv1.2.3-alpha.9\n') as read:
            self.assertEqual(release_naming.suggest_tag(self.root,'1.2.3'),'v1.2.3-alpha.10')
        self.assertEqual(read.call_args.args[0][:3],['git','tag','--list'])


class SourceReleaseVersionTests(unittest.TestCase):
    def test_source_release_uses_metadata_at_exact_commit_independently_of_mobile_version(self):
        commit = 'a' * 40
        with patch('Scripts.release_naming.subprocess.check_output', return_value='[project]\nversion="0.1.15"\n') as read:
            self.assertEqual(release_naming.source_version(Path('.'), commit), '0.1.15')
        self.assertEqual(read.call_args.args[0], ['git', 'show', commit + ':Python/pyproject.toml'])
        with self.assertRaisesRegex(ValueError, 'resolved source commit'):
            release_naming.source_version(Path('.'), 'working-tree')
