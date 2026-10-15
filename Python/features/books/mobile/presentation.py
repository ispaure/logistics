"""Offline EPUB WebView, safe internal navigation and UTF-16 text anchors."""
import json
from urllib.parse import unquote, urlsplit, parse_qs
from uuid import uuid4
import toga
from toga.style import Pack

# Executed through the native evaluation API, never supplied by the book.
# Book scripts stay stripped and CSP continues to disallow scripts/resources.
SCRIPT = r'''
(() => {
 const options = OPTIONS;
 const marker = document.querySelector('meta[name="logistics-reader-root"]');
 if (!marker || marker.content !== options.root) return;
 if (window.reader && window.reader.dispose) window.reader.dispose();
 let anchor = options.offset, timer = null, restoring = false, selectedCache = null, restoreUntil = 0;
 const nodes = () => {
   const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
   const result = []; let n; while ((n = walk.nextNode())) result.push(n);
   return result;
 };
 const point = (offset, end=false) => {
   const list = nodes(); let left = Math.max(0, offset);
   for (const node of list) {
     if (left < node.length || (end && left === node.length)) return [node, left];
     left -= node.length;
   }
   return list.length ? [list[list.length-1], list[list.length-1].length] : null;
 };
 const notify = (action, value) => {
   window.location.href = options.root + action + '?offset=' + value + '&end=' + (scrollY >= document.documentElement.scrollHeight-innerHeight-2 ? '1' : '0');
 };
 const visible = () => {
   let total = 0;
   for (const node of nodes()) {
     if (!node.length) continue;
     const range = document.createRange(); range.selectNodeContents(node);
     const rects = [...range.getClientRects()];
     if (rects.some(r => r.bottom > 16 && r.top < innerHeight)) {
       let lo = 0, hi = node.length;
       while (lo < hi) {
         const mid = Math.floor((lo+hi)/2);
         range.setStart(node, mid); range.setEnd(node, Math.min(mid+1,node.length));
         if (range.getBoundingClientRect().bottom <= 16) lo = mid+1; else hi = mid;
       }
       return total + lo;
     }
     total += node.length;
   }
   return anchor;
 };
 const seek = (offset, end=null) => {
   const p = point(offset); if (!p) return;
   selectedCache = end !== null ? {start:offset,end} : null;
   restoring = true; restoreUntil=performance.now()+500; anchor = Math.max(0, offset);
   const r = document.createRange(); r.setStart(...p); r.collapse(true);
   scrollTo(0, Math.max(0, scrollY + r.getBoundingClientRect().top - 16));
   const selection = getSelection(); selection.removeAllRanges();
   if (end !== null) {const q=point(end,true); if(q){r.setEnd(...q);selection.addRange(r);}}
   requestAnimationFrame(() => {restoring=false;});
 };
 const changed = () => {
   if (restoring || performance.now()<restoreUntil) return;
   clearTimeout(timer);
   timer = setTimeout(() => {anchor=visible();notify('position',anchor);},150);
 };
 const selectedRange = () => {
     const s = getSelection();
     if (!s || !s.rangeCount || s.isCollapsed) return null;
     const r = s.getRangeAt(0), before = document.createRange();
     if (!document.body.contains(r.commonAncestorContainer)) return null;
     before.selectNodeContents(document.body); before.setEnd(r.startContainer,r.startOffset);
     const start = before.toString().length;
     return {start, end:start+r.toString().length};
 };
 const clearSelectionCache = () => {selectedCache=null;restoreUntil=0;restoring=false;};
 const rememberSelection = () => {const range=selectedRange();if(range) selectedCache=range;};
 const resized = () => {const range=selectedRange() || selectedCache; if(range) seek(range.start,range.end); else seek(anchor);};
 window.reader = {
   selection: () => selectedRange() || selectedCache,
   seek,
   turn: direction => {
     selectedCache=null;restoreUntil=0;restoring=false;getSelection().removeAllRanges();
     const max = Math.max(0,document.documentElement.scrollHeight-innerHeight);
     if ((direction>0 && scrollY>=max-2) || (direction<0 && scrollY<=2)) {
       notify(direction>0?'next':'previous',visible()); return;
     }
     scrollBy(0,direction*Math.max(80,innerHeight-32));
     anchor=visible();notify('position',anchor);
   },
   dispose: () => {clearTimeout(timer);removeEventListener('scroll',changed);removeEventListener('resize',resized);document.removeEventListener('selectionchange',rememberSelection);removeEventListener('pointerdown',clearSelectionCache);removeEventListener('keydown',clearSelectionCache);selectedCache=null;}
 };
 addEventListener('scroll',changed,{passive:true});addEventListener('resize',resized);
 document.addEventListener('selectionchange',rememberSelection);addEventListener('pointerdown',clearSelectionCache);addEventListener('keydown',clearSelectionCache);
 // Images can settle after WebView load. Reapply the initial anchor then.
 Promise.all([...document.images].map(i => i.complete ? Promise.resolve() : new Promise(r => {
   i.addEventListener('load',r,{once:true});i.addEventListener('error',r,{once:true});
 }))).then(() => seek(options.offset));
 seek(options.offset);
 requestAnimationFrame(() => notify('position',anchor));
})();
'''


class ChapterBridge:
    def __init__(self, view, *, root, offset=0, on_event=None, on_link=None):
        self.view, self.root, self.offset = view, root, offset
        self.on_event, self.on_link = on_event, on_link
        self.ready = False
        self.closed = False
        self.at_end = False

    def loaded(self, widget, **kwargs):
        if self.closed:
            return
        self.ready = True
        options = json.dumps(dict(root=self.root, offset=self.offset))
        self.view.evaluate_javascript(SCRIPT.replace('OPTIONS', options, 1))

    def navigation(self, widget, url, **kwargs):
        if self.closed:
            return False
        if url.startswith(self.root):
            action = url[len(self.root):].split('?', 1)[0]
            try:
                offset = int(parse_qs(urlsplit(url).query)['offset'][0])
            except (KeyError, ValueError, IndexError):
                return False
            if action in {'position', 'next', 'previous'} and 0 <= offset <= 16 * 1024 * 1024:
                self.offset = offset
                self.at_end = parse_qs(urlsplit(url).query).get('end', ['0'])[0] == '1'
                if self.on_event:
                    self.on_event(action, offset)
        elif url.startswith('reader-link:') and self.on_link:
            self.on_link(unquote(url[len('reader-link:'):]))
        return False

    def seek(self, offset, end=None):
        if self.closed:
            return
        self.offset = offset
        if self.ready:
            self.view.evaluate_javascript(f'window.reader && window.reader.seek({int(offset)}, {json.dumps(end)})')

    def turn(self, direction):
        if not self.ready:
            return False
        self.view.evaluate_javascript(f'window.reader && window.reader.turn({1 if direction > 0 else -1})')
        return True

    def dispose(self):
        if self.closed:
            return
        self.closed = True
        self.ready = False
        self.on_event = self.on_link = None
        self.view.evaluate_javascript('window.reader && window.reader.dispose()')


def chapter_view(content, view=None, *, offset=0, on_event=None, on_link=None):
    if view is None:
        view = toga.WebView(style=Pack(flex=1))
    previous = getattr(view, '_chapter_bridge', None)
    if previous:
        previous.dispose()
    root = 'https://logistics.invalid/' + uuid4().hex + '/'
    bridge = ChapterBridge(view, root=root, offset=offset, on_event=on_event, on_link=on_link)
    view._chapter_bridge = bridge
    view.on_navigation_starting = bridge.navigation
    view.on_webview_load = bridge.loaded
    content = content.replace('</head>', '<meta name="logistics-reader-root" content="' + root + '"></head>', 1)
    view.set_content(root, content)
    return view


async def watch_width(*, alive, width, view):
    """Keep rich content inside its current pane despite native minimum-size hints."""
    import asyncio
    while alive():
        widget = view()
        available = max(1, int(width()))
        if widget.style.width != available:
            widget.style.width = available
        await asyncio.sleep(.3)


def pane_width(widget, fallback, margin=0):
    """Measure the native pane, avoiding feedback from content's minimum width."""
    container = getattr(widget._impl, 'container', None)
    available = getattr(container, 'width', 0) or fallback
    parent = getattr(container, 'native_parent', None)
    if parent is not None:
        # Android's cached container width can retain its pre-mount minimum.
        available = container.scale_out(parent.getWidth()) or fallback
    return max(1, min(available, fallback) - margin)


async def speech_source(view, chapter, offset):
    """Read the native DOM selection without trusting arbitrary book callbacks."""
    selected = await view.evaluate_javascript('JSON.stringify(window.reader && window.reader.selection ? window.reader.selection() : null)')
    value = json.loads(selected) if isinstance(selected, str) else None
    if (isinstance(value, dict) and type(value.get('start')) is int and type(value.get('end')) is int
            and 0 <= value['start'] < value['end'] <= chapter.length):
        return chapter, value['start'], value['end']
    return chapter, offset, None
