"""Native streamed chat, transcript layout and credential exclusion."""
import contextlib
import sys
import threading
import traceback

from .web_checks import wait_for_text


@contextlib.contextmanager
def chat_watchdog():
    """Retain Python stacks when a native bridge call blocks the event loop."""
    stopped = threading.Event()

    def diagnose():
        for attempt in range(3):
            if stopped.wait(45):
                return
            print(f'LOGISTICS_NATIVE_CHAT_STACKS={attempt + 1}', flush=True)
            names = {thread.ident: thread.name for thread in threading.enumerate()}
            for ident, frame in sys._current_frames().items():
                print(f'LOGISTICS_NATIVE_THREAD={names.get(ident, ident)}\n'
                      + ''.join(traceback.format_stack(frame)), flush=True)

    threading.Thread(target=diagnose, name='native-chat-watchdog', daemon=True).start()
    try:
        yield
    finally:
        stopped.set()


async def exercise_chat(app, passed):
    from logisticsmobile.chat_fixture import fixture_server
    with fixture_server() as (url, started, release, requests), chat_watchdog():
        print('LOGISTICS_NATIVE_CHAT=initialize', flush=True)
        app.show_chat()
        print('LOGISTICS_NATIVE_CHAT=configure', flush=True)
        app.chat_url.value = url
        app.chat_key.value = 'synthetic-native-key'
        print('LOGISTICS_NATIVE_CHAT=connect', flush=True)
        await app.refresh_chat_models()
        print('LOGISTICS_NATIVE_CHAT=connected', flush=True)
        assert app.chat_model.value == 'fixture-model', app.chat_status.value
        app.chat_prompt.value = 'Native chat fixture'
        print('LOGISTICS_NATIVE_CHAT=send', flush=True)
        await app.send_chat()
        print('LOGISTICS_NATIVE_CHAT=verify', flush=True)
        assert app.chat_current['messages'][-1]['status'] == 'complete', app.chat_status.value
        assert app.chat_current['messages'][-1]['content'] == 'Native fixture reply'
        await wait_for_text(app.chat_transcript, 'Native fixture reply')
        assert await app.chat_transcript.evaluate_javascript(
            'document.querySelectorAll("article.user").length >= 1 && '
            'document.querySelectorAll("article.assistant").length >= 1 && '
            'document.documentElement.scrollWidth <= innerWidth')
        assert app.chat_send.accessible_name == 'Send' and app.chat_send.enabled
        assert not app.chat_status_box.children
        assert 'synthetic-native-key' not in app.chat_store.path(app.chat_current['id']).read_text()
        assert 'synthetic-native-key' not in (app.chat_store.root / 'profile.json').read_text()
    passed.append('native_lm_chat')
