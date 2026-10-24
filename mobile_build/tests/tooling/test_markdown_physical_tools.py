"""Physical Markdown QA must never inherit main-app storage privileges."""
import unittest

from mobile_build.validation.markdown_physical_tools import BUNDLE, qa_entitlements


class MarkdownProvisioningTests(unittest.TestCase):
    def profile(self, identifier='TEAM.*', **entitlements):
        return dict(ProvisionedDevices=['synthetic-device'], Entitlements={
            'application-identifier': identifier,
            'keychain-access-groups': ['TEAM.*'], **entitlements})

    def test_wildcard_profile_is_narrowed_without_mutating_the_profile(self):
        profile = self.profile()
        actual = qa_entitlements(profile, 'synthetic-device')
        self.assertEqual(actual['application-identifier'], 'TEAM.' + BUNDLE)
        self.assertEqual(actual['keychain-access-groups'], ['TEAM.' + BUNDLE])
        self.assertEqual(profile['Entitlements']['keychain-access-groups'], ['TEAM.*'])

    def test_main_identity_shared_group_and_unprovisioned_device_are_rejected(self):
        for profile, udid in ((self.profile('TEAM.io.github.ispaure.logisticsmobile'), 'synthetic-device'),
                             (self.profile(**{'com.apple.security.application-groups':
                                 ['group.io.github.ispaure.logisticsmobile']}), 'synthetic-device'),
                             (self.profile(), 'another-device')):
            with self.subTest(profile=profile, udid=udid), self.assertRaises(ValueError):
                qa_entitlements(profile, udid)

    def test_exact_qa_profile_is_accepted(self):
        actual = qa_entitlements(self.profile('TEAM.' + BUNDLE), 'synthetic-device')
        self.assertEqual(actual['application-identifier'], 'TEAM.' + BUNDLE)
