"""Native streamed chat, transcript layout and credential exclusion."""
from .web_checks import wait_for_text


async def exercise_chat(app, passed):
    from logisticsmobile.chat_fixture import fixture_server
    with fixture_server() as (url, started, release, requests):
        app.show_chat()
        app.chat_url.value = url
        app.chat_key.value = 'synthetic-native-key'
        await app.refresh_chat_models()
        assert app.chat_model.value == 'fixture-model', app.chat_status.value
        app.chat_prompt.value = 'Native chat fixture'
        await app.send_chat()
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
