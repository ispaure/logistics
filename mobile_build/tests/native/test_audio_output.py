"""Output consent, cross-scene revocation and Settings contracts (no hardware claims)."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock

from services.audio_output import OutputPolicy, approvals, output
from mobile.audio_output import AudioOutput
from mobile.preferences import Preferences

SPEAKER = output('test', 'speaker', 'Built-in speaker')
CAR = output('test', 'car-address', 'Car', bluetooth=True)
HEADSET = output('test', 'headset-address', 'Headset', bluetooth=True)


class PolicyTests(unittest.TestCase):
    def test_all_route_changes_require_separate_play_and_duplicate_events_do_not(self):
        policy = OutputPolicy()
        approved = {CAR.identity: CAR.label, HEADSET.identity: HEADSET.label}
        for route in [(SPEAKER,), (CAR,), (HEADSET,), (SPEAKER,), None, (CAR,)]:
            self.assertTrue(policy.observe(route))
            self.assertFalse(policy.permitted(approved))
            if route:
                self.assertTrue(policy.request_play(approved))
                self.assertFalse(policy.observe(route))
                self.assertTrue(policy.permitted(approved))
            else:
                self.assertFalse(policy.request_play(approved))

    def test_unknown_identity_and_same_display_name_cannot_inherit_approval(self):
        policy = OutputPolicy()
        approved = {CAR.identity: CAR.label}
        for item in [output('test', '', 'Car', bluetooth=True), output('test', 'impostor', 'Car', bluetooth=True)]:
            policy.observe((item,))
            self.assertFalse(policy.request_play(approved))
        self.assertNotIn('car-address', json.dumps(approved))

    def test_preference_validation_rejects_ambiguous_or_unbounded_approvals(self):
        for raw in ['{}', '[{}]', '[{"id":"name","name":"Car"}]',
                    json.dumps([dict(id=CAR.identity, name='Car')]*2),
                    json.dumps([dict(id=CAR.identity, name='Car\n')])]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                approvals(raw)


class ConsentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.route = (SPEAKER,)
        self.dialog = AsyncMock(return_value=False)
        self.protected = True
        self.privacy = NS(inactive=False, saved_content=None, disposed=False, captured=False,
                          gates=lambda: (NS(locked=False),) if self.protected else (),
                          sensitive=lambda: self.protected)
        self.app = NS(preferences=Preferences(Path(self.temp.name)), active_host=True,
            screen_privacy=self.privacy, main_window=NS(dialog=self.dialog), loop=asyncio.get_running_loop())
        self.native = NS(outputs=lambda: self.route, in_call=lambda: False, dispose=Mock())
        self.owner = AudioOutput(self.app, self.native)
        self.app.audio_output = self.owner
        self.addCleanup(self.owner.dispose)
        self.pause_video = Mock()
        self.pause_speech = Mock()
        self.owner.register('video', self.pause_video)
        self.owner.register('speech', self.pause_speech)

    async def prompt_done(self):
        task = self.owner.prompt
        if task is not None:
            await task

    async def test_before_play_approval_never_resumes_any_player(self):
        self.route = (CAR,)
        self.dialog.return_value = True
        self.assertFalse(self.owner.request_play())
        await self.prompt_done()
        self.assertIn(CAR.identity, self.owner.approved())
        self.assertFalse(self.owner.permitted())
        self.assertTrue(self.owner.request_play())
        self.assertTrue(self.owner.permitted())
        self.assertEqual(Preferences(Path(self.temp.name)).values, self.app.preferences.values)
        self.pause_video.assert_called()
        self.pause_speech.assert_called()

    async def test_decline_cancel_and_unknown_output_never_approve_or_resume(self):
        for decision in [False, None]:
            self.dialog.return_value = decision
            self.route = (CAR,)
            self.assertFalse(self.owner.request_play())
            await self.prompt_done()
            self.assertEqual(self.owner.approved(), {})
            self.assertFalse(self.owner.permitted())
        self.route = None
        self.assertFalse(self.owner.request_play())
        await self.prompt_done()
        self.assertEqual(self.owner.approved(), {})

    async def test_revoke_while_playing_affects_all_scenes_and_players(self):
        other_app = NS(preferences=Preferences(Path(self.temp.name)), active_host=True,
            screen_privacy=self.privacy, main_window=NS(dialog=self.dialog), loop=asyncio.get_running_loop())
        other = AudioOutput(other_app, self.native)
        self.addCleanup(other.dispose)
        pause_other = Mock()
        other.register('other-video', pause_other)
        self.route = (CAR,)
        self.owner.refresh()
        await self.prompt_done()
        self.owner.save({CAR.identity: CAR.label})
        self.assertTrue(self.owner.request_play())
        self.assertTrue(other.request_play())
        self.owner.save({})
        self.assertFalse(self.owner.policy.manual_play)
        self.assertFalse(other.policy.manual_play)
        self.assertEqual(other.approved(), {})
        pause_other.assert_called()
        self.assertFalse(other.request_play())
        await (other.prompt or asyncio.sleep(0))

    async def test_route_auth_and_settings_changes_reject_stale_dialog_decisions(self):
        for change in ['route', 'auth', 'settings']:
            future = asyncio.get_running_loop().create_future()
            async def dialog(*args):
                return await future
            self.app.main_window.dialog = dialog
            self.route = (CAR,)
            self.owner.offer(explicit=True) if self.owner.policy.route == self.route else self.owner.refresh()
            task = self.owner.prompt
            await asyncio.sleep(0)
            if change == 'route':
                self.route = (SPEAKER,)
                self.owner.refresh()
            elif change == 'auth':
                self.owner.invalidate()
            else:
                self.owner.save({})
            future.set_result(True)
            if task is not None:
                await task
            # A fresh prompt may now exist; it is not the stale approval.
            self.assertEqual(self.owner.approved(), {})
            if self.owner.prompt is not None:
                self.owner.prompt.cancel()
                await asyncio.gather(self.owner.prompt, return_exceptions=True)

    async def test_interruption_capture_and_duplicate_events_never_grant_play(self):
        self.assertTrue(self.owner.request_play())
        for _ in range(2):
            self.owner.interrupt(True)
            self.assertFalse(self.owner.request_play())
        self.owner.interrupt(False)
        self.assertFalse(self.owner.permitted())
        self.assertTrue(self.owner.request_play())
        self.owner.capture_changed(True)
        self.assertFalse(self.owner.request_play())
        self.owner.capture_changed(False)
        self.assertFalse(self.owner.permitted())

    async def test_settings_lists_persisted_device_and_remove_revokes_audio(self):
        import toga
        from mobile.settings.audio import controls
        self.owner.save({CAR.identity: CAR.label})
        box = toga.Box()
        rows = controls(self.app, box)
        row = rows.children[0]
        self.assertIn('Car', row.children[0].text)
        self.assertIn(CAR.identity[:8], row.children[0].text)
        row.children[1].on_press()
        self.assertEqual(self.owner.approved(), {})
        self.assertIn('No approved Bluetooth', rows.children[0].text)
        self.assertEqual(Preferences(Path(self.temp.name)).values['approved_bluetooth_devices'], '[]')

    async def test_media_activation_rechecks_output_before_granting_play(self):
        def activate():
            self.route = (CAR,)
            return True
        self.native.prepare = activate
        self.assertFalse(self.owner.request_play())
        await self.prompt_done()
        self.assertFalse(self.owner.permitted())
        self.assertEqual(self.owner.approved(), {})

    async def test_backgrounding_rejects_queued_prompt_without_presenting_it(self):
        self.route = (CAR,)
        self.owner.refresh()
        task = self.owner.prompt
        self.privacy.inactive = True
        self.owner.invalidate(pause=False)
        if task is not None:
            await task
        self.dialog.assert_not_awaited()
        self.assertFalse(self.owner.request_play())
        self.assertIsNone(self.owner.prompt)

    async def test_capture_pause_callback_cannot_reauthorize_playback(self):
        attempts = []
        self.owner.register('reentrant', lambda: attempts.append(self.owner.request_play()))
        self.assertTrue(self.owner.request_play())
        self.owner.capture_changed(True)
        self.assertEqual(attempts, [False])
        self.owner.capture_changed(False)
        self.assertFalse(self.owner.permitted())

    async def test_ordinary_playback_never_reads_approvals_even_with_unknown_output(self):
        self.protected = False
        self.owner.approved = Mock(side_effect=AssertionError('Ordinary playback read the list'))
        for route in [(CAR,), (output('test', '', 'Unreadable Bluetooth', bluetooth=True),), None]:
            self.route = route
            self.assertTrue(self.owner.request_play())
            self.assertTrue(self.owner.permitted())
        self.dialog.assert_not_awaited()
        self.owner.approved.assert_not_called()

    async def test_ordinary_output_switch_does_not_force_separate_play(self):
        self.protected = False
        self.assertTrue(self.owner.request_play())
        self.pause_video.reset_mock()
        self.pause_speech.reset_mock()
        for route in [(CAR,), (HEADSET,), (SPEAKER,)]:
            self.route = route
            self.owner.refresh()
            self.assertTrue(self.owner.permitted())
        self.pause_video.assert_not_called()
        self.pause_speech.assert_not_called()
        self.assertIsNone(self.owner.prompt)

    async def test_ordinary_loss_and_interruptions_still_pause_until_user_play(self):
        self.protected = False
        self.route = (CAR,)
        self.assertTrue(self.owner.request_play())
        self.route = (SPEAKER,)
        self.owner.refresh(lost=True)
        self.assertFalse(self.owner.permitted())
        self.pause_video.assert_called()
        self.pause_speech.assert_called()
        self.route = (CAR,)
        self.owner.refresh()
        self.assertFalse(self.owner.permitted())
        self.assertTrue(self.owner.request_play())
        self.owner.interrupt(True)
        self.owner.interrupt(False)
        self.assertFalse(self.owner.permitted())
        self.dialog.assert_not_awaited()

    async def test_ordinary_playback_ignores_settings_list_removal(self):
        self.protected = False
        self.route = (CAR,)
        self.owner.save({CAR.identity: CAR.label})
        self.assertTrue(self.owner.request_play())
        self.pause_video.reset_mock()
        self.owner.save({})
        self.assertTrue(self.owner.permitted())
        self.pause_video.assert_not_called()

    async def test_retained_protection_still_requires_consent_after_credentials_clear(self):
        self.protected = False
        retained = Mock(spec=['restricted'])
        retained.restricted = True
        self.owner.register(retained, Mock())
        self.route = (CAR,)
        self.assertTrue(self.owner.protected())
        self.assertFalse(self.owner.request_play())
        await self.prompt_done()
        self.owner.unregister(retained)
        self.assertFalse(self.owner.protected())
        self.assertTrue(self.owner.request_play())

    async def test_pending_approval_cannot_apply_after_protection_ends(self):
        future = asyncio.get_running_loop().create_future()
        async def dialog(*args):
            return await future
        self.app.main_window.dialog = dialog
        self.route = (CAR,)
        self.owner.refresh()
        task = self.owner.prompt
        await asyncio.sleep(0)
        self.protected = False
        future.set_result(True)
        await task
        self.assertEqual(self.owner.approved(), {})
        self.assertFalse(self.owner.permitted())
        self.assertTrue(self.owner.request_play())


class SpeechResumeGateTests(unittest.TestCase):
    def test_native_paused_utterance_cannot_bypass_output_revocation(self):
        from features.books.mobile.speech import SpeechSession
        engine = NS(resume_utterance=Mock())
        session = SpeechSession(engine, on_range=Mock(), on_state=Mock())
        session.state = 'paused'
        session.native_paused = True
        session.can_speak = lambda: False
        session.resume()
        engine.resume_utterance.assert_not_called()
        self.assertEqual(session.state, 'paused')

    def test_shared_credential_gate_blocks_plain_speech_until_authorized(self):
        from features.books.mobile.media_controls import SpeechPlayback
        privacy = NS(sensitive=lambda: True, inactive=False, saved_content=object(),
                     captured=False, gates=lambda: (NS(locked=True),))
        app = NS(active_host=True, screen_privacy=privacy,
                 preferences=NS(values={'session_speech_when_locked': 'false'}))
        panel = NS(session=NS(state='paused'))
        playback = SpeechPlayback(panel, app, factory=Mock())
        try:
            self.assertFalse(playback.credential_start())
            app.preferences.values['session_speech_when_locked'] = 'true'
            self.assertTrue(playback.credential_start())
            privacy.captured = True
            self.assertFalse(playback.credential_start())
        finally:
            playback.dispose()


class AppleRouteEventTests(unittest.TestCase):
    def test_loss_reasons_are_distinct_from_ordinary_selection_changes(self):
        import sys
        from unittest.mock import patch
        from mobile.audio_output_native import AppleOutputs
        callbacks = {}
        def observe(name, **kwargs):
            callbacks[name] = kwargs['usingBlock']
            return object()
        center = NS(addObserverForName=Mock(side_effect=observe), removeObserver=Mock())
        classes = {'AVAudioSession': NS(sharedInstance=object()),
                   'NSNotificationCenter': NS(defaultCenter=center),
                   'NSOperationQueue': NS(mainQueue=object())}
        objc = NS(ObjCClass=lambda name: classes[name],
                  Block=lambda callback, *signature: callback, objc_id=object())
        changed = Mock()
        with patch.dict(sys.modules, {'rubicon.objc': objc}), patch('ctypes.CDLL'):
            monitor = AppleOutputs(changed, Mock())
        try:
            callback = callbacks['AVAudioSessionRouteChangeNotification']
            for reason, lost in [(1, False), (2, True), (7, True), (8, False)]:
                for number in [reason, NS(unsignedIntegerValue=lambda: reason)]:
                    callback(NS(userInfo=NS(objectForKey=lambda key: number)))
                    changed.assert_called_with(lost=lost)
        finally:
            monitor.dispose()
