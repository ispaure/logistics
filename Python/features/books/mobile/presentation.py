"""Offline EPUB WebView, safe internal navigation and UTF-16 text anchors."""
import json
from urllib.parse import unquote, urlsplit, parse_qs
from uuid import uuid4
import toga
from commonUtils.ui.native.inline_html import set_inline_html
from toga.style import Pack

# Executed through the native evaluation API, never supplied by the book.
# Book scripts stay stripped and CSP continues to disallow scripts/resources.
SCRIPT = r'''
(() => {
 const options = OPTIONS;
 const marker = document.querySelector('meta[name="logistics-reader-root"]');
 if (!marker || marker.content !== options.root) return;
 if (window.reader && window.reader.dispose) window.reader.dispose();
 const pages = document.createElement('div');
 while(document.body.firstChild) pages.appendChild(document.body.firstChild);
 const viewport=document.createElement('div');viewport.appendChild(pages);document.body.appendChild(viewport);
 Object.assign(viewport.style,{overflow:'hidden',position:'relative',width:'100%'});
 document.documentElement.style.overflow='hidden';
 Object.assign(document.body.style,{overflow:'hidden',height:'100vh',boxSizing:'border-box'});
 Object.assign(pages.style,{columnFill:'auto',columnGap:'0px',position:'relative'});
 let motionEnabled=options.motion!==false;
 let page=0, pageWidth=1, pageCount=1, columns=1, stride=1, viewportWidth=1, geometry=null, touch=null, disposed=false, pageAnimation=null;
 const stopMotion=()=>{if(pageAnimation){pageAnimation.cancel();pageAnimation=null;}};
 const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
 const motionChanged=()=>{if(!motionEnabled || reducedMotion.matches || document.getElementById('logistics-eink'))stopMotion();};
 reducedMotion.addEventListener('change',motionChanged);
 const contrastObserver=new MutationObserver(motionChanged);
 contrastObserver.observe(document.head,{childList:true,subtree:true});
 const originalMaxWidth=getComputedStyle(document.body).maxWidth;
 const lastPage=()=>Math.floor((pageCount-1)/columns)*columns;
 const layout=()=>{
   stopMotion();
   const css=getComputedStyle(document.body);
   const padLeft=parseFloat(css.paddingLeft), padRight=parseFloat(css.paddingRight);
   const height=Math.max(1,innerHeight-parseFloat(css.paddingTop)-parseFloat(css.paddingBottom));
   // A fold is measured in this WebView's coordinates, not the whole window.
   const folded=geometry && geometry.seam>0 && geometry.seam<1;
   columns=(folded || (innerWidth>=700 && innerHeight>=480 && innerWidth>innerHeight))?2:1;
   document.body.style.maxWidth=columns===2?'none':originalMaxWidth;
   let gap=0, origin=padLeft;
   if(columns===2){
     const center=folded?geometry.seam*innerWidth:innerWidth/2;
     const crease=folded?geometry.gap*innerWidth:0;
     gap=crease+padLeft+padRight;
     const maximum=parseFloat(originalMaxWidth);
     pageWidth=Math.max(1,Math.min(center-crease/2-padLeft-padRight,
       innerWidth-center-crease/2-padLeft-padRight,
       Number.isFinite(maximum)?maximum-padLeft-padRight:Infinity));
     origin=center-gap/2-pageWidth;
   } else pageWidth=Math.max(1,document.body.clientWidth-padLeft-padRight);
   stride=pageWidth+gap;viewportWidth=columns*pageWidth+(columns-1)*gap;
   viewport.style.marginLeft=(origin-padLeft)+'px';viewport.style.width=viewportWidth+'px';
   pages.style.width=viewportWidth+'px';pages.style.columnWidth=pageWidth+'px';
   pages.style.columnGap=gap+'px';pages.style.columnCount=String(columns);
   pages.style.height=height+'px';viewport.style.height=pages.style.height;
   for(const image of pages.querySelectorAll('img')) Object.assign(image.style,{maxHeight:pages.style.height,maxWidth:'100%',objectFit:'contain',breakInside:'avoid'});
   pageCount=Math.max(1,Math.ceil((pages.scrollWidth+gap-1)/stride));
 };
 const place=value=>{stopMotion();page=Math.max(0,Math.min(lastPage(),Math.floor(value/columns)*columns));pages.style.transform='translateX('+(-page*stride)+'px)';scrollTo(0,0);};
 layout();
 let anchor = options.offset, selectedCache = null, speechRange = null;
 // Inert chapter text is immutable for this bridge's lifetime. Index once.
 let textNodes = [], textEnds = [], textStarts = new WeakMap();
 const walk = document.createTreeWalker(pages, NodeFilter.SHOW_TEXT);
 let node, length = 0;
 while ((node = walk.nextNode())) {
   textStarts.set(node, length); length += node.length;
   textNodes.push(node); textEnds.push(length);
 }
 const point = (offset, end=false) => {
   const value = Math.max(0, offset);
   let lo=0, hi=textEnds.length;
   while(lo<hi) {
     const mid=(lo+hi)>>>1;
     if(end ? textEnds[mid]<value : textEnds[mid]<=value) lo=mid+1; else hi=mid;
   }
   if(lo<textNodes.length) return [textNodes[lo], value-(lo ? textEnds[lo-1] : 0)];
   return textNodes.length ? [textNodes.at(-1), textNodes.at(-1).length] : null;
 };
 const notify = (action, value) => {
   window.location.href = options.root + action + '?offset=' + value + '&end=' + (page===lastPage() ? '1' : '0');
 };
 const visible = () => {
   if(pageAnimation && pageAnimation.playState==='running')return anchor;
   let total = 0;
   const left=viewport.getBoundingClientRect().left, right=left+viewportWidth;
   for (const node of textNodes) {
     if (!node.length) continue;
     const range = document.createRange(); range.selectNodeContents(node);
     const rects = [...range.getClientRects()];
     if (rects.some(r => r.right > left+1 && r.left < right-1 && r.bottom > 0 && r.top < innerHeight)) {
       let lo = 0, hi = node.length;
       while (lo < hi) {
         const mid = Math.floor((lo+hi)/2);
         range.setStart(node, mid); range.setEnd(node, Math.min(mid+1,node.length));
         if (range.getBoundingClientRect().right <= left+1) lo = mid+1; else hi = mid;
       }
       return total + lo;
     }
     total += node.length;
   }
   return anchor;
 };
 const seek = (offset, end=null) => {
   stopMotion();
   const p = point(offset); if (!p) return;
   selectedCache = end !== null ? {start:offset,end} : null;
   anchor = Math.max(0, offset);
   const r = document.createRange(); r.setStart(...p); r.collapse(true);
   const left=viewport.getBoundingClientRect().left;
   place(Math.floor((r.getBoundingClientRect().left-left+page*stride+.5)/stride));
   const selection = getSelection(); selection.removeAllRanges();
   if (end !== null) {const q=point(end,true); if(q){r.setEnd(...q);selection.addRange(r);}}
 };
 const selectedRange = () => {
     const s = getSelection();
     if (!s || !s.rangeCount || s.isCollapsed) return null;
     const r = s.getRangeAt(0), before = document.createRange();
     if(speechRange && r.startContainer===speechRange.startContainer && r.startOffset===speechRange.startOffset &&
        r.endContainer===speechRange.endContainer && r.endOffset===speechRange.endOffset) return null;
     if (!document.body.contains(r.commonAncestorContainer)) return null;
     before.selectNodeContents(document.body); before.setEnd(r.startContainer,r.startOffset);
     const start = textStarts.has(r.startContainer) ? textStarts.get(r.startContainer)+r.startOffset : before.toString().length;
     return {start, end:start+r.toString().length};
 };
 const clearSelectionCache = () => {selectedCache=null;};
 const rememberSelection = () => {const range=selectedRange();if(range) selectedCache=range;};
 const resized = () => {const range=selectedRange() || selectedCache;layout();if(range) seek(range.start,range.end); else seek(anchor);notify('position',anchor);};
 const touchStart=e=>{const t=e.touches.length===1?e.touches[0]:null;touch=t?{x:t.clientX,y:t.clientY}:null;};
 // Two-finger movement belongs to the host's text-size pinch recognizer.
 const touchMove=e=>{if(e.touches.length===1 && !selectedRange()) e.preventDefault();};
 const touchEnd=e=>{
   if(!touch || selectedRange()) return;
   const t=e.changedTouches[0], dx=t.clientX-touch.x,dy=t.clientY-touch.y;touch=null;
   if(Math.abs(dx)>45 && Math.abs(dx)>Math.abs(dy)*1.3) window.reader.turn(dx<0?1:-1);
 };
 const wheel=e=>{e.preventDefault();};
 const key=e=>{if(['ArrowLeft','ArrowRight','PageUp','PageDown',' '].includes(e.key)){
   e.preventDefault();window.reader.turn(['ArrowLeft','PageUp'].includes(e.key)?-1:1);
 }};
 document.addEventListener('touchstart',touchStart,{passive:true});
 document.addEventListener('touchmove',touchMove,{passive:false});
 document.addEventListener('touchend',touchEnd);
 document.addEventListener('wheel',wheel,{passive:false});document.addEventListener('keydown',key);
 window.reader = {
   speechSource: () => ({selection:selectedRange() || selectedCache, offset:visible()}),
   selection: () => selectedRange() || selectedCache,
   highlight: (start, end) => {
     if (window.CSS && CSS.highlights) {
       const previous=CSS.highlights.get('logistics-speech');
       if(previous) previous.clear();
       CSS.highlights.delete('logistics-speech');
     }
     if (start < 0) {getSelection().removeAllRanges();selectedCache=null;speechRange=null;return;}
     seek(start);
     const p=point(start), q=point(end,true);if(!p || !q)return;
     const r=document.createRange();r.setStart(...p);r.setEnd(...q);
     if(window.CSS && CSS.highlights && window.Highlight) {
       if(!document.getElementById('logistics-speech-style')) {
         const style=document.createElement('style');style.id='logistics-speech-style';
         style.textContent='::highlight(logistics-speech){background:#ffcf40;color:#151515}';
         document.head.appendChild(style);
       }
       CSS.highlights.set('logistics-speech',new Highlight(r));
     } else {speechRange=r;getSelection().addRange(r);}
   },
   setMotion: value => {motionEnabled=!!value;motionChanged();},
   setGeometry: value => {if(JSON.stringify(value)!==JSON.stringify(geometry)){geometry=value;resized();}},
   pagination: () => ({index:page,count:pageCount,width:pageWidth,columns,stride,
     left:viewport.getBoundingClientRect().left,gap:stride-pageWidth,anchor}),
   seek,
   turn: direction => {
     selectedCache=null;getSelection().removeAllRanges();
     if ((direction>0 && page===lastPage()) || (direction<0 && page===0)) {
       notify(direction>0?'next':'previous',visible()); return;
     }
     const previous=page;
     place(page+(direction>0?columns:-columns));
     // Measure the destination before starting visual motion so saved passage
     // anchors never describe an interpolated position between two pages.
     anchor=visible();notify('position',anchor);
     if(motionEnabled && !document.getElementById('logistics-eink') && !reducedMotion.matches){
       pageAnimation=pages.animate([{transform:'translateX('+(-previous*stride)+'px)'},
         {transform:'translateX('+(-page*stride)+'px)'}],{duration:220,easing:'ease-out'});
     }
   },
   dispose: () => {disposed=true;stopMotion();contrastObserver.disconnect();reducedMotion.removeEventListener('change',motionChanged);textNodes=[];textEnds=[];textStarts=new WeakMap();if(viewport.isConnected){while(pages.firstChild) viewport.before(pages.firstChild);viewport.remove();}document.removeEventListener('touchstart',touchStart);document.removeEventListener('touchmove',touchMove);document.removeEventListener('touchend',touchEnd);document.removeEventListener('wheel',wheel);document.removeEventListener('keydown',key);removeEventListener('resize',resized);document.removeEventListener('selectionchange',rememberSelection);removeEventListener('pointerdown',clearSelectionCache);removeEventListener('keydown',clearSelectionCache);selectedCache=null;}
 };
 addEventListener('resize',resized);
 document.addEventListener('selectionchange',rememberSelection);addEventListener('pointerdown',clearSelectionCache);addEventListener('keydown',clearSelectionCache);
 // Images can settle after WebView load. Reapply the initial anchor then.
 Promise.all([...document.images].map(i => i.complete ? Promise.resolve() : new Promise(r => {
   i.addEventListener('load',r,{once:true});i.addEventListener('error',r,{once:true});
 }))).then(() => {if(!disposed){layout();seek(options.offset);}});
 seek(options.offset);
 requestAnimationFrame(() => {if(!disposed) notify('position',anchor);});
})();
'''


class ChapterBridge:
    def __init__(self, view, *, root, offset=0, on_event=None, on_link=None, motion_enabled=True):
        self.view, self.root, self.offset = view, root, offset
        self.motion_enabled = bool(motion_enabled)
        self.on_event, self.on_link = on_event, on_link
        self.ready = False
        self.closed = False
        self.at_end = False
        self.geometry_provider = None
        self.geometry = None

    def loaded(self, widget, **kwargs):
        if self.closed:
            return
        self.ready = True
        options = json.dumps(dict(root=self.root, offset=self.offset, motion=self.motion_enabled))
        self.view.evaluate_javascript(SCRIPT.replace('OPTIONS', options, 1))
        self.refresh_geometry(force=True)

    def refresh_geometry(self, *, force=False):
        if self.closed or self.geometry_provider is None:
            return
        geometry = self.geometry_provider()
        if force or geometry != self.geometry:
            self.geometry = geometry
            if self.ready:
                self.view.evaluate_javascript('window.reader && window.reader.setGeometry(' +
                                              json.dumps(geometry) + ')')

    def set_motion_enabled(self, enabled):
        enabled = bool(enabled)
        if self.motion_enabled != enabled:
            self.motion_enabled = enabled
            if self.ready and not self.closed:
                self.view.evaluate_javascript('window.reader && window.reader.setMotion(' +
                                              json.dumps(enabled) + ')')

    def navigation(self, widget, url, **kwargs):
        if self.closed:
            return False
        # WKWebView requests its internal blank bootstrap before committing
        # loadHTMLString's base URL. Keep that inert navigation alive only
        # while the new trusted chapter is loading.
        if url == 'about:blank' and not self.ready:
            return True
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

    def highlight(self, start, end):
        if not self.closed and self.ready:
            if start >= 0:
                self.offset = start
            self.view.evaluate_javascript(
                f'window.reader && window.reader.highlight({int(start)}, {int(end)})')

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


def chapter_view(content, view=None, *, offset=0, on_event=None, on_link=None, motion_enabled=True):
    if view is None:
        view = toga.WebView(style=Pack(flex=1))
    view.page_swipes_at_edges = True
    impl = getattr(view, '_impl', None)
    native = getattr(impl, 'native', None)
    from toga.platform import get_factory
    backend = get_factory().WebView.__module__ if native is not None else ''
    if backend.startswith('toga_iOS.'):
        native.scrollView.scrollEnabled = False
        native.scrollView.bounces = False
    elif backend.startswith('toga_android.'):
        native.setVerticalScrollBarEnabled(False)
        native.setHorizontalScrollBarEnabled(False)
        native.setOverScrollMode(2)
    previous = getattr(view, '_chapter_bridge', None)
    if previous:
        previous.dispose()
    root = 'https://logistics.invalid/' + uuid4().hex + '/'
    bridge = ChapterBridge(view, root=root, offset=offset, on_event=on_event, on_link=on_link, motion_enabled=motion_enabled)
    view._chapter_bridge = bridge
    view.on_navigation_starting = bridge.navigation
    view.on_webview_load = bridge.loaded
    content = content.replace('</head>', '<meta name="logistics-reader-root" content="' + root + '"></head>', 1)
    set_inline_html(view, root, content)
    return view


async def watch_width(*, alive, width, view, changed):
    """Keep rich content inside its current pane despite native minimum-size hints."""
    while alive():
        await changed()
        if not alive():
            return
        widget = view()
        available = max(1, int(width()))
        if widget.style.width != available:
            widget.style.width = available


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
    selected = await view.evaluate_javascript('JSON.stringify(window.reader && window.reader.speechSource ? window.reader.speechSource() : null)')
    value = json.loads(selected) if isinstance(selected, str) else None
    if isinstance(value, dict) and 'selection' in value:
        visible = value.get('offset')
        if type(visible) is int and 0 <= visible <= chapter.length:
            offset = visible
        value = value['selection']
    if (isinstance(value, dict) and type(value.get('start')) is int and type(value.get('end')) is int
            and 0 <= value['start'] < value['end'] <= chapter.length):
        return chapter, value['start'], value['end']
    return chapter, offset, None
