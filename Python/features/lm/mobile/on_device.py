"""Explicit, local-only model dispatch; importing this module loads no native APIs."""
import json
import sys
from threading import Event
from time import monotonic

from features.lm.mobile.transport import ChatCancelled, ChatClient, MAX_REPLY

MODELS = {'apple': 'Apple Intelligence (on device)', 'nano': 'Gemini Nano (on device)'}
PROVIDERS = {'OpenAI-compatible server': 'server', **{name: key for key, name in MODELS.items()}}


def platform_provider():
    return {'ios': 'apple', 'android': 'nano'}.get(sys.platform)


def configured(profile):
    return bool(profile.get('model') and (profile.get('base_url') or profile.get('provider') in MODELS))


def client_for(profile, api_key=''):
    provider = profile.get('provider', 'server')
    if provider == 'server':
        return ChatClient(profile['base_url'], api_key)
    if provider not in MODELS:
        raise ValueError('Unknown chat provider.')
    return OnDeviceClient(provider)


class AppleBridge:
    def __init__(self):
        from rubicon.objc import ObjCClass
        self.native = ObjCClass('LogisticsFoundationChat').alloc().init()

    def status(self):
        return str(self.native.availability())

    def start(self, payload):
        self.native.startRequest(json.dumps(payload, ensure_ascii=False))

    def snapshot(self):
        return json.loads(str(self.native.snapshot()))

    def cancel(self):
        self.native.cancel()

    def close(self):
        self.cancel()


class NanoBridge:
    def __init__(self):
        from java import jclass
        if jclass('android.os.Build$VERSION').SDK_INT < 26:
            raise ValueError('Gemini Nano requires Android 8 or later on a supported device.')
        self.jclass = jclass
        self.model = jclass('com.google.mlkit.genai.prompt.Generation').INSTANCE.getClient()
        self.native = jclass('com.google.mlkit.genai.prompt.java.GenerativeModelFutures').from_(self.model)
        self.future = None

    def status(self):
        status = self.native.checkStatus()
        try:
            code = status.get(15, self.jclass('java.util.concurrent.TimeUnit').SECONDS)
        finally:
            status.cancel(True)
        flags = self.jclass('com.google.mlkit.genai.common.FeatureStatus')
        if code == flags.AVAILABLE:
            return 'available'
        if code == flags.DOWNLOADABLE:
            return 'downloadable'
        if code == flags.DOWNLOADING:
            return 'Android is downloading Gemini Nano. Check again when it finishes.'
        return 'Gemini Nano is not supported or ready on this device.'

    def prepare(self, cancelled):
        from java import dynamic_proxy
        completed = Event()
        failed = Event()
        callback_type = self.jclass('com.google.mlkit.genai.common.DownloadCallback')
        class Callback(dynamic_proxy(callback_type)):
            def onDownloadStarted(self, size):
                pass
            def onDownloadProgress(self, size):
                pass
            def onDownloadCompleted(self):
                completed.set()
            def onDownloadFailed(self, error):
                failed.set()
                completed.set()
        callback = Callback()
        self.future = self.native.download(callback)
        deadline = monotonic() + 600
        while not completed.wait(.1):
            if cancelled.is_set():
                raise ChatCancelled('Model preparation cancelled; Android may finish its system download in the background.')
            if monotonic() >= deadline:
                raise TimeoutError('Model preparation exceeded ten minutes. Check Android/AICore and try again.')
        if failed.is_set():
            raise ValueError('Android could not download Gemini Nano. Check your network and AICore, then try again.')

    def start(self, payload):
        # The Prompt API takes a text prompt. Preserve role boundaries as JSON;
        # the saved conversation remains authoritative across stateless requests.
        prompt = ('Continue this conversation with the next assistant reply. '
                  'The following JSON contains the system instructions and conversation turns:\n'
                  + json.dumps(payload['messages'], ensure_ascii=False))
        part = self.jclass('com.google.mlkit.genai.prompt.TextPart')(prompt)
        builder = self.jclass('com.google.mlkit.genai.prompt.GenerateContentRequest$Builder')(part)
        builder.setMaxOutputTokens(payload['max_tokens'])
        self.future = self.native.generateContent(builder.build())

    def snapshot(self):
        if not self.future.isDone():
            return dict(text='', done=False)
        try:
            result = self.future.get()
        except Exception as error:
            raise ValueError('Gemini Nano could not complete the reply. Check AICore, model availability, context length or the on-device usage quota.') from error
        return dict(text=str(result.getCandidates().get(0).getText()), done=True)

    def cancel(self):
        if self.future is not None:
            self.future.cancel(True)

    def close(self):
        self.cancel()
        self.model.close()


def native_bridge(provider):
    if platform_provider() != provider:
        raise ValueError('This on-device model is unavailable on this platform.')
    try:
        return AppleBridge() if provider == 'apple' else NanoBridge()
    except ValueError:
        raise
    except Exception as error:
        raise ValueError('The on-device AI integration is unavailable in this build.') from error


class OnDeviceClient:
    def __init__(self, provider):
        self.provider = provider
        self.cancelled = Event()

    def cancel(self):
        # Native calls belong to the worker. Its short poll interrupts inference.
        self.cancelled.set()

    def check(self):
        if self.cancelled.is_set():
            raise ChatCancelled('Request cancelled.')

    def models(self):
        self.check()
        bridge = native_bridge(self.provider)
        try:
            status = bridge.status()
            self.check()
            if status == 'downloadable':
                bridge.prepare(self.cancelled)
                self.check()
                status = bridge.status()
            if status != 'available':
                raise ValueError(status)
            return [MODELS[self.provider]]
        finally:
            bridge.close()

    def stream(self, payload, fragment):
        self.check()
        bridge = native_bridge(self.provider)
        try:
            status = bridge.status()
            self.check()
            if status == 'downloadable':
                raise ValueError('Prepare Gemini Nano in Chat settings before sending.')
            if status != 'available':
                raise ValueError(status)
            bridge.start(payload)
            previous = ''
            deadline = monotonic() + 600
            while True:
                self.check()
                if monotonic() >= deadline:
                    raise TimeoutError('On-device generation exceeded ten minutes.')
                snapshot = bridge.snapshot()
                text = snapshot.get('text', '')
                if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_REPLY:
                    raise ValueError('Reply exceeds the mobile 256 KiB limit.')
                if not text.startswith(previous):
                    raise ValueError('The on-device model revised an already displayed reply; partial text was preserved.')
                self.check()
                if text != previous:
                    fragment(text[len(previous):])
                    previous = text
                if snapshot.get('error'):
                    raise ValueError(snapshot['error'])
                if snapshot.get('done'):
                    if not text:
                        raise ValueError('The on-device model returned no reply.')
                    return 'stop'
                self.cancelled.wait(.05)
        except Exception:
            self.check()
            raise
        finally:
            bridge.close()
