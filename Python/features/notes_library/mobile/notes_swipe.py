"""Document swipes leave tables, selection, pinch zoom and vertical scroll alone."""
import json


def document_swipes(base):
    return r"""(function(){
      window.notesDrawersBase=BASE;
      if(window.notesDrawersInstalled)return; window.notesDrawersInstalled=true;
      let start=null;
      const zoomed=()=>window.visualViewport && window.visualViewport.scale>1.01;
      document.addEventListener('touchstart', e=>{
        start=null;
        if(e.touches.length!==1 || zoomed() || String(getSelection()))return;
        let t=e.touches[0], el=e.target;
        while(el && el!==document.body){
          if(el.scrollWidth>el.clientWidth+2 || el.isContentEditable ||
             /^(TABLE|INPUT|TEXTAREA|SELECT|BUTTON|AUDIO|VIDEO)$/.test(el.tagName) ||
             (el.classList && el.classList.contains('table-scroll')))return;
          el=el.parentElement;
        }
        start={x:t.clientX,y:t.clientY,time:Date.now()};
      },{passive:true});
      document.addEventListener('touchmove',e=>{
        if(e.touches.length!==1 || zoomed())start=null;
        if(start){
          const t=e.touches[0],dx=t.clientX-start.x,dy=t.clientY-start.y;
          if(Math.abs(dy)>10 && Math.abs(dx)<Math.abs(dy)*2)start=null;
        }
      },{passive:true});
      document.addEventListener('touchcancel',()=>start=null,{passive:true});
      document.addEventListener('touchend',e=>{
        const s=start; start=null;
        if(!s || e.touches.length || !e.changedTouches.length || zoomed() || String(getSelection()))return;
        const t=e.changedTouches[0],dx=t.clientX-s.x,dy=t.clientY-s.y;
        if(Math.abs(dx)<60 || Math.abs(dx)<Math.abs(dy)*2 || Date.now()-s.time>800)return;
        location.href=window.notesDrawersBase+(dx>0?'?drawer=files':'?drawer=links');
      },{passive:true});
    })();""".replace('BASE', json.dumps(base))
