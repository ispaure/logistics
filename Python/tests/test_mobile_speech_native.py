"""Native speech voice policy and late callback delivery without device services."""
import asyncio
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from features.books.mobile.speech_native import NativeSpeech


def voice(name, *, network=False, installed=True, null_features=False):
    return SimpleNamespace(
        getName=lambda: name, isNetworkConnectionRequired=lambda: network,
        getFeatures=lambda: None if null_features else SimpleNamespace(
            toArray=lambda: [] if installed else ['notInstalled']),
        getLocale=lambda: SimpleNamespace(toLanguageTag=lambda: 'en-US'))


class NativeSpeechTests(unittest.TestCase):
    def engine(self):
        engine = NativeSpeech.__new__(NativeSpeech)
        engine.closed, engine.ready, engine.error = False, False, ''
        engine.voices, engine.default_voice = {}, ''
        engine.native = MagicMock()
        engine.native.getVoice.return_value = engine.native.getDefaultVoice.return_value = None
        engine.progress_listener = object()
        return engine

    def test_android_prefers_system_offline_voice_and_handles_null_features(self):
        engine = self.engine()
        other, system = voice('alphabetical-first'), voice('system', null_features=True)
        engine.native.getVoice.return_value = system
        engine.native.getVoices.return_value.toArray.return_value = [
            other, voice('network', network=True), voice('missing', installed=False), system]
        with patch.dict(sys.modules, {'android.media': SimpleNamespace(AudioAttributes=MagicMock())}):
            engine.load_android_voices(0)
        self.assertTrue(engine.ready)
        self.assertEqual(engine.default_voice, 'en-US · system')
        self.assertEqual(set(engine.voices), {'en-US · alphabetical-first', 'en-US · system'})
        engine.native.setAudioAttributes.assert_called_once()
        engine.native.setOnUtteranceProgressListener.assert_called_once_with(engine.progress_listener)

    def test_android_uses_offline_default_when_enumeration_is_empty_or_fails(self):
        for listing in ('empty', 'missing', 'failure'):
            with self.subTest(listing=listing):
                engine = self.engine()
                engine.native.getDefaultVoice.return_value = voice('system-offline')
                if listing == 'failure':
                    engine.native.getVoices.side_effect = RuntimeError('Engine enumeration failed')
                elif listing == 'missing':
                    engine.native.getVoices.return_value = None
                else:
                    engine.native.getVoices.return_value.toArray.return_value = []
                with patch.dict(sys.modules, {'android.media': SimpleNamespace(AudioAttributes=MagicMock())}):
                    engine.load_android_voices(0)
                self.assertTrue(engine.ready)
                self.assertEqual(engine.default_voice, 'en-US · system-offline')

    def test_android_does_not_offer_network_or_uninstalled_defaults(self):
        engine = self.engine()
        engine.native.getVoices.return_value.toArray.return_value = []
        engine.native.getVoice.return_value = voice('network', network=True)
        engine.native.getDefaultVoice.return_value = voice('missing', installed=False)
        with patch.dict(sys.modules, {'android.media': SimpleNamespace(AudioAttributes=MagicMock())}):
            engine.load_android_voices(0)
        self.assertFalse(engine.ready)
        self.assertFalse(engine.voices)
        self.assertIn('install voice data', engine.error)

    def test_closed_android_engine_and_late_native_events_are_ignored(self):
        engine = self.engine()
        engine.loop = asyncio.new_event_loop()
        self.addCleanup(engine.loop.close)
        engine.progress, engine.started = MagicMock(), MagicMock()
        engine.word_range('old', 0, 4)
        engine.begin('old')
        engine.closed = True
        engine.load_android_voices(0)
        engine.loop.run_until_complete(asyncio.sleep(0))
        engine.native.getVoices.assert_not_called()
        engine.progress.assert_not_called()
        engine.started.assert_not_called()
