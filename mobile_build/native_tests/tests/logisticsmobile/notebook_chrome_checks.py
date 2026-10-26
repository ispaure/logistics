"""Browser assertions for compact notebook chrome and painted ink swatches."""

CHROME_CHECKS = r'''(()=>{
function require(value,message){if(!value)throw Error(message)}
const dock=document.querySelector('.mobile-dock').getBoundingClientRect();
const back=document.querySelector('header button').getBoundingClientRect();
const more=document.querySelector('header button[aria-label="Notebook actions"]').getBoundingClientRect();
require(dock.top<=(innerWidth<420?112:60),'Drawing buttons are not at the top');
require(state.native_close||back.left<20&&back.top<20,'Back button moved from its existing corner');
require(dock.bottom<=back.top||dock.top>=back.bottom||dock.right<=back.left||dock.left>=back.right,'Tools overlap Back');
require(dock.bottom<=more.top||dock.top>=more.bottom||dock.right<=more.left||dock.left>=more.right,'Tools overlap notebook actions');
document.getElementById('brushToggle').click();
document.querySelector('[data-tool="12"]').click();
document.querySelector('[data-color="6"]').click();
const blue=()=>getComputedStyle(document.querySelector('.swatch[data-color="6"] circle')).fill;
require(blue()==='rgb(78, 105, 201)','Writing blue does not match the notebook palette');
const selected=document.querySelector('.brush-card[aria-pressed="true"]');
require(selected.dataset.tool==='12','Current brush not identified');
require(getComputedStyle(selected.querySelector('span')).backgroundColor==='rgba(0, 0, 0, 0)','Selected brush label has an opaque contrast-mode background');
require(getComputedStyle(selected).backgroundColor!==getComputedStyle(document.querySelector('.brush-card[data-tool="17"]')).backgroundColor,'Current brush is not visually distinguished');
const bounds=document.querySelector('.swatch[data-color="6"] svg').getBoundingClientRect();
require(bounds.width>=24&&bounds.height>=24,'Ink color disc collapsed');
const saved=$('grayscale').checked;$('grayscale').checked=true;$('grayscale').dispatchEvent(new Event('change'));
require(blue()==='rgb(78, 105, 201)','Document grayscale preview removed palette colors');
$('grayscale').checked=saved;$('grayscale').dispatchEvent(new Event('change'));
document.querySelector('[data-tool="18"]').click();
require(blue()==='rgb(190, 234, 254)','Highlighter blue does not use its native palette');
const colors=[...document.querySelectorAll('.swatch')].map(b=>({name:b.getAttribute('aria-label'),fill:getComputedStyle(b.querySelector('circle')).fill}));
require(colors.length===6&&colors.every(c=>c.fill!=='none'&&c.fill!=='rgba(0, 0, 0, 0)'),'Highlighter swatches were not painted');
document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));
document.querySelector('header button[aria-label="Notebook actions"]').click();
const shortcuts=[...document.querySelectorAll('.sheet-shortcuts svg')].map(svg=>{let r=svg.getBoundingClientRect();return {width:r.width,height:r.height}});
require(shortcuts.length===2&&shortcuts.every(r=>r.width<=24&&r.height<=24&&r.width>0),'Pages/Layers shortcut icons are oversized');
document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));
return JSON.stringify({top_toolbar:true,back_preserved:true,selected_brush:true,painted_swatches:colors,compact_shortcuts:shortcuts});
})()'''
