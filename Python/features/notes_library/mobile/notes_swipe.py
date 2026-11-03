"""Document-edge swipes leave tables, selection, pinch zoom and vertical scroll alone."""
import json


def document_swipes(base):
    return r"""(function(){
      if(window.notesDrawersInstalled)return; window.notesDrawersInstalled=true;
      let start=null;
      document.addEventListener('touchstart', e=>{
        start=null;
        if(e.touches.length!==1 || (window.visualViewport && window.visualViewport.scale>1.01))return;
        let t=e.touches[0], el=e.target;
        while(el && el!==document.body){
          if(el.scrollWidth>el.clientWidth+2 || el.isContentEditable)return;
          el=el.parentElement;
        }
        if(t.clientX<48 || t.clientX>innerWidth-48)
          start={x:t.clientX,y:t.clientY,time:Date.now()};
      },{passive:true});
      document.addEventListener('touchcancel',()=>start=null,{passive:true});
      document.addEventListener('touchend',e=>{
        const s=start; start=null;
        if(!s || !e.changedTouches.length || String(getSelection()))return;
        const t=e.changedTouches[0],dx=t.clientX-s.x,dy=t.clientY-s.y;
        if(Math.abs(dx)<60 || Math.abs(dx)<Math.abs(dy)*2 || Date.now()-s.time>800)return;
        if(dx>0 && s.x<48) location.href=BASE+'?drawer=files';
        if(dx<0 && s.x>innerWidth-48) location.href=BASE+'?drawer=links';
      },{passive:true});
    })();""".replace('BASE', json.dumps(base))
