"""Session-owned offline speech for rendered Markdown; no plaintext cache."""
import json
from weakref import WeakSet

from commonUtils.formats.markdown.speech import RenderedRun, prepare_rendered

from features.books.mobile.speech_view import ReadAloudPanel
from .control_icons import icon_button


SOURCE_SCRIPT = r'''
((useSelection,key) => {
 const selection=getSelection(), selected=useSelection && selection && !selection.isCollapsed && selection.rangeCount ? selection.getRangeAt(0) : null;
 const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT), entries=[], runs=[], cues=new Set();
 const blocks='p,div,li,pre,summary,h1,h2,h3,h4,h5,h6,td,th,caption,figcaption,blockquote,aside';
 const hidden='script,style,noscript,template,[aria-hidden=true],.image-alt,.footnote-ref,.footnote-backref,.line-number,.math-source,[data-speech-skip]';
 let position=0, node, previous=null, previousCell=null, previousRow=null, breakLine=false;
 while((node=walker.nextNode())) {
   const parent=node.parentElement;
   if(!parent || parent.closest(hidden) || !parent.getClientRects().length)continue;
   const details=parent.closest('details:not([open])');
   if(details && !details.querySelector(':scope > summary')?.contains(parent))continue;
   const visibility=getComputedStyle(parent).visibility;
   if(visibility==='hidden' || visibility==='collapse')continue;
   if(selected && !selected.intersectsNode(node))continue;
   const left=selected && selected.startContainer===node ? selected.startOffset : 0;
   const right=selected && selected.endContainer===node ? selected.endOffset : node.length;
   if(right<=left)continue;
   const block=parent.closest(blocks), cell=parent.closest('td,th'), row=cell && cell.parentElement;
   const literal=parent.closest('pre');
   let text=node.data.slice(left,right);
   if(!literal && !text.trim() && previous!==block)continue;
   if(!text.trim() && !literal && !parent.matches('a,em,strong,code,span,td,th,li,p'))continue;
   let boundary=block!==previous ? (row && row===previousRow && cell!==previousCell ? 'cell' : row ? 'row' : 'block') : '';
   const prior=node.previousSibling;
   if(!boundary && ((prior && prior.nodeName==='BR') || breakLine))boundary='line';
   breakLine=false;
   previous=block; previousCell=cell; previousRow=row;
   const cueOwner=parent.closest('li,.markdown-footnote');
   let cue='';
   if(cueOwner?.matches('[data-speech-task],.markdown-footnote') && text.trim() && !cues.has(cueOwner)) {
     cues.add(cueOwner);
     cue=cueOwner.dataset.speechTask || 'Footnote';
   }
   if(!literal)text=text.replace(/[\t\n\r]/g,' ');
   // Layout whitespace after a BR/block is not part of visible selected text.
   const ignored=!literal && boundary ? text.length-text.trimStart().length : 0;
   if(ignored)text=text.slice(ignored);
   entries.push({node,left:left+ignored,right,start:position,end:position+text.length});
   let start=position;
   if(literal) {
     for(const line of text.split('\n')) {
       if(line)runs.push([line,start,boundary,cue]);
       start+=line.length+1; boundary='line'; cue='';
     }
     breakLine=text.endsWith('\n');
   } else {
     runs.push([text,start,boundary,cue]);
   }
   position+=text.length;
 }
 window[key]={entries};
 return JSON.stringify(runs);
})(SELECTION,KEY)
'''

HIGHLIGHT_SCRIPT = r'''
((start,end) => {
 if(window.CSS && CSS.highlights) {
   const previous=CSS.highlights.get('logistics-speech');
   if(previous)previous.clear();
   CSS.highlights.delete('logistics-speech');
 }
 const state=window[KEY];
 if(start<0) {
   if(state?.fallbackRange) {
     const selection=getSelection();
     if(selection.rangeCount && selection.getRangeAt(0)===state.fallbackRange)selection.removeAllRanges();
     state.fallbackRange=null;
   }
   return;
 }
 if(!state)return;
 const a=state.entries.find(e=>e.start<=start && e.end>start);
 const b=state.entries.find(e=>e.start<end && e.end>=end);
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
   window.logisticsSpeechHighlightKey=KEY;
 } else {
   const s=getSelection();s.removeAllRanges();s.addRange(range);
   state.fallbackRange=range;
 }
 const rect=range.getBoundingClientRect();
 if(rect.top<0 || rect.bottom>innerHeight)a.node.parentElement.scrollIntoView({block:'center'});
})(START,END)
'''

async def prepare_view(web, *, selection=True, key='logisticsSpeech'):
    source = SOURCE_SCRIPT.replace('SELECTION', json.dumps(selection)).replace('KEY', json.dumps(key))
    value = await web.evaluate_javascript(source)
    runs = json.loads(value) if isinstance(value, str) else []
    return prepare_rendered(RenderedRun(*run) for run in runs)


def highlight_view(web, prepared, start, end, *, key='logisticsSpeech'):
    mapped = prepared.source_range(start, end) if start >= 0 and prepared is not None else None
    left, right = mapped or (-1, -1)
    script = HIGHLIGHT_SCRIPT.replace('START', str(left)).replace('END', str(right))
    web.evaluate_javascript(script.replace('KEY', json.dumps(key)))


def clear_view(web, *, key='logisticsSpeech'):
    key = json.dumps(key)
    web.evaluate_javascript(
        f'delete window[{key}];'
        f'if(window.logisticsSpeechHighlightKey==={key}){{'
        "window.CSS?.highlights?.delete('logistics-speech');delete window.logisticsSpeechHighlightKey;}"
    )


class MarkdownSpeechPanel(ReadAloudPanel):
    def state(self, state, message):
        if state == 'speaking':
            message = 'Reading Markdown aloud'
        elif message.startswith('Finished'):
            message = 'Finished reading Markdown.'
        super().state(state, message)
        if message == 'Finished reading Markdown.':
            self.retire_source()

    def stop_playback(self, widget=None, **kwargs):
        super().stop_playback(widget, **kwargs)
        self.retire_source()


class MarkdownSpeech:
    def __init__(self, app, web, container, *, privacy_gate=lambda: None, valid=lambda: True, document_title=lambda: ''):
        self.app, self.web, self.container = app, web, container
        self.privacy_gate, self.valid = privacy_gate, valid
        self.document_title = document_title
        self.panel = None
        self.highlight_active = False
        self.prepared = self.view_key = None
        self.button = icon_button('speaker', 'Read aloud', on_press=self.show)
        if not hasattr(app, '_markdown_speech'):
            app._markdown_speech = WeakSet()
        app._markdown_speech.add(self)

    def show(self, widget=None, **kwargs):
        if self.panel is not None and not self.panel.closed:
            self.panel.toggle_over(self.container, anchor=self.button)
            return
        stop_markdown_speech(self.app)
        self.panel = MarkdownSpeechPanel(loop=self.app.loop, source=self.source,
            on_range=self.highlight, close=self.close, app=self.app, privacy_gate=self.privacy_gate, valid=self.valid,
            document_title=self.document_title)
        self.panel.retire_source = self._retire_source
        self.panel.show_over(self.container, anchor=self.button)

    async def source(self):
        self._retire_source()
        panel = self.panel
        generation = panel.session.generation
        key = f'logisticsSpeech-{id(self)}-{generation}'
        self.view_key = key
        prepared = await prepare_view(self.web, key=key)
        if self.panel is not panel or panel.session.generation != generation or self.view_key != key:
            clear_view(self.web, key=key)
            return prepare_rendered(()), 0, None
        self.prepared = prepared
        return prepared, 0, None

    def _retire_source(self):
        if self.view_key is not None:
            clear_view(self.web, key=self.view_key)
            self.prepared = self.view_key = None

    def highlight(self, start, end):
        if start < 0 and not self.highlight_active:
            return
        self.highlight_active = start >= 0
        if self.view_key and self.valid() and not getattr(getattr(self.app, 'screen_privacy', None), 'inactive', False):
            highlight_view(self.web, self.prepared, start, end, key=self.view_key)

    def close(self, widget=None, **kwargs):
        if self.panel is not None:
            self.panel.dispose()
            if self.panel in self.container.children:
                self.container.remove(self.panel)
            self.panel = None
            self._retire_source()


def stop_markdown_speech(app, *, keep=None):
    for speech in tuple(getattr(app, '_markdown_speech', ())):
        if speech.panel is not keep:
            speech.close()
