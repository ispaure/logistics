"""Notes-owned inline controls. The host authorizes Play before the DOM plays."""

import asyncio
from html import escape
from json import dumps
from threading import Event

from commonUtils.runtime.operations import OperationCancelled


PREPARING_VIDEO = 'Preparing video…'
PAUSE_VIDEOS = "document.querySelectorAll('video').forEach(video => video.pause())"


async def open_native_video(browser, path, *, pause, close_speech, current, fullscreen=False):
    path = browser.contained(path)
    if browser.host.open_resource is None:
        browser.notice.text = 'Video playback is unavailable in this host.'
        return False
    try:
        if not current():
            return False
        # Leave the source view and its provider in place for the return from playback.
        await pause()
        if not current():
            return False
        close_speech()
        if fullscreen:
            return bool(await browser.host.open_resource(browser.provider, path, fullscreen=True))
        return bool(await browser.host.open_resource(browser.provider, path))
    except (OSError, ValueError) as error:
        if current():
            browser.notice.text = str(error)
        return False


class PageVideos:
    """Playback and audio registration for one admitted HTML version."""

    def __init__(self, browser, web, speech, targets, *, current, in_dom):
        self.browser, self.web, self.speech = browser, web, speech
        self.targets = targets
        self._current, self._in_dom = current, in_dom
        self.task = None
        self.closed = False
        self.audio = browser.host.audio_output()
        if self.audio is not None:
            self.audio.register(self, self.pause)

    def pause(self):
        if not self.closed:
            self._pause_inline()

    def _pause_inline(self):
        return self.web.evaluate_javascript(self._in_dom(
            "document.querySelectorAll('.note-video video').forEach(video => video.pause())"))

    def _pause_for_handoff(self):
        return self.web.evaluate_javascript(self._in_dom(PAUSE_VIDEOS))

    def close(self):
        self.closed = True
        if self.task is not None:
            self.task.cancel()
            self.task = None
            if self.browser.notice.text == PREPARING_VIDEO:
                self.browser.notice.text = ''
        if self.audio is not None:
            self._pause_inline()
            self.audio.unregister(self)
            self.audio = None

    def start(self, key, path, *, inline):
        if self.closed or not self._current(path) or key not in self.targets:
            return
        if self.task is not None and not self.task.done():
            return
        audio = self.audio if inline else None
        if inline:
            if audio is None or not audio.interactive():
                return
            self.speech.close()
            if not audio.request_play():
                return
        self.task = self.browser.host.loop.create_task(self._play(path, key, self.targets[key], audio))

    async def _play(self, document, key, target, audio):
        stopped = Event()

        def current():
            return not self.closed and self._current(document)

        def cancelled():
            return stopped.is_set() or not current()

        if not current():
            return False
        self.browser.notice.text = PREPARING_VIDEO
        try:
            if audio is None:
                path, _ = await asyncio.to_thread(self.browser.library.link, document, target, cancelled=cancelled)
                return current() and await open_native_video(self.browser, path, pause=self._pause_for_handoff,
                    close_speech=self.speech.close, current=current, fullscreen=True)
            url = await asyncio.to_thread(self.browser.library.open_embedded_video, document, target, cancelled=cancelled)
            if not current() or not audio.interactive() or not audio.permitted():
                return False
            if url is None:
                raise ValueError('Video unavailable.')
            await self.web.evaluate_javascript(
                self._in_dom('window.logisticsPlayVideo?.(' + dumps(key) + ',' + dumps(url) + ')'))
            return True
        except OperationCancelled:
            return False
        except (OSError, RuntimeError, ValueError):
            if current():
                self.browser.notice.text = 'Video unavailable.'
            return False
        finally:
            stopped.set()
            if current() and self.browser.notice.text == PREPARING_VIDEO:
                self.browser.notice.text = ''


def video_embed(video, base, key, filename):
    video = video.replace('<video controls ', '<video disablepictureinpicture disableremoteplayback ', 1)
    return (
        f'<span class="note-video" data-key="{key}" data-play="{base}?inline-video={key}">{video}'
        '<span class="note-video-controls">'
        '<button type="button" class="note-video-play" aria-label="Play">'
        '<svg aria-hidden="true" viewBox="0 0 24 24"><path class="play" d="M8 5v14l11-7z"/>'
        '<path class="pause" d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg></button>'
        '<input type="range" min="0" max="1" step="any" value="0" disabled aria-label="Video position">'
        f'<a class="note-video-fullscreen" href="{base}?video={key}" title="{escape(filename, quote=True)}">'
        '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M9 4H4v5h2V6h3zm6 0v2h3v3h2V4z'
        'M4 15v5h5v-2H6v-3zm14 0v3h-3v2h5v-5z"/></svg>Play fullscreen video</a>'
        '</span><span class="note-video-status" role="status" hidden></span></span>'
    )


STYLE = """
.note-video{display:inline-block;max-width:100%;vertical-align:middle;background:#161616;color:#fff;border-radius:12px;overflow:hidden}
.note-video video{display:block;margin:auto;background:#000;pointer-events:none}
.note-video-controls{display:flex;align-items:center;flex-wrap:wrap;gap:6px;padding:4px 8px}
.note-video-controls button,.note-video-controls a{display:inline-flex;align-items:center;justify-content:center;
gap:5px;min-height:44px;border:0;border-radius:22px;font:600 .8rem system-ui;text-decoration:none}
.note-video-controls button{width:44px;background:#fff;color:#161616}
.note-video-controls a{padding:0 10px;color:#fff;background:#303030}
.note-video-controls svg{width:20px;height:20px;fill:currentColor}
.note-video-controls input{flex:1;min-width:42px;max-width:100%;min-height:44px;margin:0;accent-color:#fff}
.note-video-play .pause,.note-video-play[data-playing] .play{display:none}
.note-video-play[data-playing] .pause{display:inline}
.note-video-status{padding:0 10px 6px;font-size:.8rem}
"""


SCRIPT = """
(() => {
  const players = new Map();
  for (const card of document.querySelectorAll('.note-video')) {
    const video = card.querySelector('video');
    const play = card.querySelector('button');
    const seek = card.querySelector('input');
    const status = card.querySelector('[role=status]');
    play.addEventListener('click', () => {
      if (video.paused) location.href = card.dataset.play;
      else video.pause();
    });
    function update() {
      play.toggleAttribute('data-playing', !video.paused);
      play.setAttribute('aria-label', video.paused ? 'Play' : 'Pause');
      seek.disabled = !Number.isFinite(video.duration) || video.duration <= 0;
      if (!seek.disabled && document.activeElement !== seek)
        seek.value = video.currentTime / video.duration;
    }
    seek.addEventListener('change', () => { video.currentTime = seek.value * video.duration; });
    seek.addEventListener('blur', update);
    for (const event of ['play', 'pause', 'ended', 'durationchange', 'timeupdate'])
      video.addEventListener(event, update);
    function failed() {
      status.textContent = 'Inline playback is unavailable. Try fullscreen.';
      status.hidden = false;
    }
    video.addEventListener('error', failed);
    video.addEventListener('playing', () => { status.hidden = true; });
    players.set(card.dataset.key, {
      video,
      start: url => {
        if (video.getAttribute('src') !== url) video.src = url;
        video.play().catch(error => { if (error.name !== 'AbortError') failed(); });
      },
    });
  }
  window.logisticsPlayVideo = (key, url) => {
    const selected = players.get(key);
    if (!selected) return;
    for (const player of players.values()) if (player !== selected) player.video.pause();
    selected.start(url);
  };
})();
"""


def install_controls(html, nonce, *, worker=False):
    if worker:
        html = html.replace("script-src 'unsafe-eval';", f"script-src 'unsafe-eval' 'nonce-{nonce}';", 1)
    else:
        html = html.replace("default-src 'none';", f"default-src 'none'; script-src 'nonce-{nonce}';", 1)
    html = html.replace('</head>', '<style>' + STYLE + '</style></head>', 1)
    return html.replace('</body>', f'<script nonce="{nonce}">{SCRIPT}</script></body>', 1)
