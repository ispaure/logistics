"""Session-owned offline speech for rendered Markdown; no plaintext cache."""
import json
from types import SimpleNamespace
from weakref import WeakSet

from features.books.mobile.speech_view import ReadAloudPanel
from .control_icons import icon_button


SOURCE_SCRIPT = r'''
(() => {
 const selection=getSelection(), selected=selection && !selection.isCollapsed && selection.rangeCount ? selection.getRangeAt(0) : null;
 const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT), entries=[];
 let text='', node, block=null;
 while((node=walker.nextNode())) {
   const parent=node.parentElement;
   if(!parent || parent.closest('script,style,noscript') || !parent.getClientRects().length)continue;
   if(selected && !selected.intersectsNode(node))continue;
   let left=selected && selected.startContainer===node ? selected.startOffset : 0;
   let right=selected && selected.endContainer===node ? selected.endOffset : node.length;
   if(right<=left)continue;
   const nextBlock=parent.closest('p,div,li,pre,h1,h2,h3,h4,h5,h6,td,th,blockquote');
   if(text && nextBlock!==block)text+='\n';
   block=nextBlock;
   const start=text.length; text+=node.data.slice(left,right);
   entries.push({node,left,right,start,end:text.length});
 }
 window.logisticsSpeech={entries};
 return JSON.stringify(text);
})()
'''

HIGHLIGHT_SCRIPT = r'''
((start,end) => {
 if(window.CSS && CSS.highlights)CSS.highlights.delete('logistics-speech');
 const state=window.logisticsSpeech;
 if(start<0) {getSelection().removeAllRanges();return;}
 if(!state)return;
 const a=state.entries.find(e=>e.end>start), b=state.entries.find(e=>e.end>=end);
 if(!a || !b || !a.node.isConnected || !b.node.isConnected)return;
 const range=document.createRange();
 range.setStart(a.node,a.left+Math.max(0,start-a.start));
 range.setEnd(b.node,b.left+Math.min(b.right-b.left,end-b.start));
 if(window.CSS && CSS.highlights && window.Highlight) {
   if(!document.getElementById('logistics-speech-style')) {
     const style=document.createElement('style');style.id='logistics-speech-style';
     style.textContent='::highlight(logistics-speech){background:#ffcf40;color:#151515}';
     document.head.appendChild(style);
   }
   CSS.highlights.set('logistics-speech',new Highlight(range));
 } else {const s=getSelection();s.removeAllRanges();s.addRange(range);}
 const rect=range.getBoundingClientRect();
 if(rect.top<0 || rect.bottom>innerHeight)a.node.parentElement.scrollIntoView({block:'center'});
})(START,END)
'''

class MarkdownSpeechPanel(ReadAloudPanel):
    def state(self, state, message):
        if state == 'speaking':
            message = 'Reading Markdown aloud'
        elif message.startswith('Finished'):
            message = 'Finished reading Markdown.'
        super().state(state, message)


class MarkdownSpeech:
    def __init__(self, app, web, container, *, privacy_gate=lambda: None, valid=lambda: True):
        self.app, self.web, self.container = app, web, container
        self.privacy_gate, self.valid = privacy_gate, valid
        self.panel = None
        self.generation = 0
        self.highlight_active = self.source_ready = False
        self.button = icon_button('speaker', 'Read aloud', on_press=self.show)
        if not hasattr(app, '_markdown_speech'):
            app._markdown_speech = WeakSet()
        app._markdown_speech.add(self)

    def show(self, widget=None, **kwargs):
        stop_markdown_speech(self.app)
        self.panel = MarkdownSpeechPanel(loop=self.app.loop, source=self.source,
            on_range=self.highlight, close=self.close, app=self.app, privacy_gate=self.privacy_gate, valid=self.valid)
        self.panel.show_over(self.container)

    async def source(self):
        generation = self.generation
        # Read rendered text, including tables and code, rather than Markdown
        # punctuation or image data. Native selection wins when it is nonempty.
        value = await self.web.evaluate_javascript(SOURCE_SCRIPT)
        text = json.loads(value) if isinstance(value, str) else ''
        if generation != self.generation or not isinstance(text, str):
            text = ''
        else:
            self.source_ready = True
        return SimpleNamespace(text=text), 0, None

    def highlight(self, start, end):
        if start < 0 and not self.highlight_active:
            return
        self.highlight_active = start >= 0
        if self.valid() and not getattr(getattr(self.app, 'screen_privacy', None), 'inactive', False):
            self.web.evaluate_javascript(HIGHLIGHT_SCRIPT.replace('START', str(int(start))).replace('END', str(int(end))))

    def close(self, widget=None, **kwargs):
        self.generation += 1
        if self.panel is not None:
            self.panel.dispose()
            if self.panel in self.container.children:
                self.container.remove(self.panel)
            self.panel = None
            if self.source_ready:
                self.web.evaluate_javascript('delete window.logisticsSpeech')
                self.source_ready = False


def stop_markdown_speech(app, *, keep=None):
    for speech in tuple(getattr(app, '_markdown_speech', ())):
        if speech.panel is not keep:
            speech.close()
