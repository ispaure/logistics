"""Offline conversation presentation; no server, widget or storage ownership."""
from html import escape
import json
import math
import unicodedata

from .preview import markdown_body
from .palette import css_variables


def composer_height(text, width, font_size=16):
    """Conservative wrapped-line estimate, bounded so replies retain space."""
    columns = max(8, int(max(1, width - 24) / (font_size * .65)))
    lines = sum(max(1, math.ceil(sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1
                                    for c in line) / columns)) for line in text.split('\n'))
    return min(120, max(52, int(lines * font_size * 1.4 + 20)))


def transcript_entries(messages, previous=()):
    entries = []
    for index, entry in enumerate(messages):
        role, status = entry['role'], entry['status']
        label = 'You' if role == 'user' else role.title()
        if status != 'complete':
            label += ' · ' + status.title()
        if (index < len(previous) and previous[index]['label'] == label
                and previous[index]['text'] == entry['content']):
            entries.append(previous[index])
            continue
        content = (f'<p class="plain">{escape(entry["content"])}</p>' if role == 'user'
                   else markdown_body(entry['content']))
        if not content:
            content = '<p class="muted">Waiting for a reply…</p>' if status == 'streaming' else ''
        entries.append(dict(role='user' if role == 'user' else 'assistant',
                            label=label, html=content, text=entry['content']))
    return entries


def transcript_document():
    """Only trusted app code is evaluated later; message HTML is always inert."""
    return '''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<style>
''' + css_variables() + '''
:root { --ink:var(--text); --user:var(--hover); --line:var(--border) }
* { box-sizing:border-box } body { margin:0; padding:12px 8px 20px; background:var(--surface); color:var(--ink); font:16px/1.5 system-ui; overflow-wrap:anywhere }
main { max-width:780px; margin:auto } article { margin:0 0 16px; padding:12px 16px; border:1px solid var(--line); border-radius:16px } article.user { margin-left:28px; background:var(--user) }
.role { color:var(--muted); font-size:.75em; margin-bottom:6px } .user .role { color:var(--ink) }
p { margin:0 0 12px } p:last-child { margin-bottom:0 } .plain { white-space:pre-wrap }
ul,ol { padding-left:24px; margin:8px 0 16px } li { margin-bottom:6px }
pre { padding:12px; background:var(--user); border-radius:8px; white-space:pre-wrap; overflow-wrap:anywhere } code { font-family:monospace }
h1,h2,h3,h4,h5,h6 { font-size:1.15em; margin:16px 0 8px } .muted { color:var(--muted) }
.copy { min-height:44px; min-width:44px; padding:8px 0; border:0; background:transparent; color:var(--muted); font:inherit; font-size:.75em }
button { touch-action:manipulation } button:focus-visible { outline:2px solid var(--accent) }
#latest { position:fixed; bottom:10px; left:50%; transform:translateX(-50%); padding:10px 16px; min-height:44px; border:1px solid var(--line); border-radius:24px; background:var(--surface); color:var(--ink); font:inherit; font-size:.8em }
#empty { padding:36px 12px } #empty h1 { font-size:1.25em; margin:0 0 8px } #copy-status { position:fixed; bottom:0; background:var(--surface); color:var(--ink); font-size:.8em }
</style></head><body><main id="messages" aria-label="Conversation"></main>
<section id="empty"><h1>Start a conversation</h1><p class="muted" id="hint">Write a message below.</p></section>
<button id="latest" hidden>Latest message ↓</button><div id="copy-status" role="status"></div></body></html>'''


def transcript_update(key, entries, font_size, *, configured, force_latest=False, start=0):
    """Patch changed message nodes, retaining selection and a reader's scroll."""
    payload = json.dumps(dict(key=key, entries=entries, start=start, count=start + len(entries),
                              font_size=int(font_size), configured=configured,
                              force_latest=force_latest), ensure_ascii=True)
    return '''(() => {
const data = ''' + payload + ''';
const root = document.getElementById('messages');
if (!root) return false;
const latest = document.getElementById('latest');
const bottom = () => window.scrollTo(0, document.documentElement.scrollHeight);
const nearBottom = () => document.documentElement.scrollHeight - window.innerHeight - window.scrollY < 80;
if (!window.chatView) {
 window.chatView = { key:null, entries:[] };
 latest.addEventListener('click', bottom);
 window.addEventListener('scroll', () => { latest.hidden = nearBottom(); }, {passive:true});
}
const state = window.chatView;
const changed = state.key !== data.key;
const follow = changed || data.force_latest || nearBottom();
if (changed) { root.replaceChildren(); state.entries = []; window.scrollTo(0,0); }
document.body.style.fontSize = data.font_size + 'px';
document.getElementById('empty').hidden = data.count !== 0;
document.getElementById('hint').textContent = data.configured ? 'Write a message below.' : 'Choose Server & model settings from the conversation menu (•••) to get started.';
data.entries.forEach((entry, offset) => {
 const index = data.start + offset;
 const previous = state.entries[index];
 if (previous && JSON.stringify(previous) === JSON.stringify(entry)) return;
 let article = root.children[index];
 if (!article) { article = document.createElement('article'); root.append(article); }
 article.className = entry.role;
 const label = document.createElement('div'); label.className = 'role'; label.textContent = entry.label;
 const content = document.createElement('div'); content.innerHTML = entry.html;
 article.replaceChildren(label, content);
 if (entry.role === 'assistant' && entry.text) {
  const copy = document.createElement('button'); copy.className = 'copy'; copy.textContent = 'Copy';
  copy.setAttribute('aria-label', 'Copy assistant message');
  copy.onclick = () => {
   const selection = window.getSelection(); const range = document.createRange(); range.selectNodeContents(content);
   selection.removeAllRanges(); selection.addRange(range);
   let copied = false;
   try { copied = document.execCommand('copy'); } catch (_) {}
   if (copied) selection.removeAllRanges();
   const notice = document.getElementById('copy-status');
   notice.textContent = copied ? 'Copied' : 'Text selected. Use the system Copy command.';
   clearTimeout(state.copyTimer); state.copyTimer = setTimeout(() => {notice.textContent = '';}, 3000);
  };
  article.append(copy);
 }
});
while (root.children.length > data.count) root.lastChild.remove();
state.key = data.key;
state.entries.splice(data.start, state.entries.length - data.start, ...data.entries);
if (follow) bottom();
latest.hidden = nearBottom();
return true;
})()'''


def navigation_clearance(viewport_top, viewport_bottom, bar_top, bar_height):
    """Keep the composer twelve points above a visible bar in its viewport."""
    if bar_height <= 0 or bar_top >= viewport_bottom or bar_top + bar_height <= viewport_top:
        return 12
    return max(12, int(viewport_bottom - max(viewport_top, bar_top)) + 12)
