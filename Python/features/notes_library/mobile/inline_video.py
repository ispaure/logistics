"""Notes-owned inline controls. The host authorizes Play before the DOM plays."""

from html import escape


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
      start: () => video.play().catch(error => { if (error.name !== 'AbortError') failed(); }),
    });
  }
  window.logisticsPlayVideo = key => {
    const selected = players.get(key);
    if (!selected) return;
    for (const player of players.values()) if (player !== selected) player.video.pause();
    selected.start();
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
