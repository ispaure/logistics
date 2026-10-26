"""Compose offline notebook assets for desktop and native mobile WebViews."""
import json
from .assets import asset
from .bridge import MAX_COMMAND
from .icons import ICON_SCRIPT


def editor_html(state, bridge, *, console_bridge=False, desktop=False, mobile=False):
    if desktop and mobile:
        raise ValueError('Choose one notebook presentation.')
    style = asset('base.css')
    chrome = asset('controls.html')
    presentation = ''
    if desktop:
        style += '\n' + asset('desktop.css')
        chrome = asset('desktop.html')
        presentation = ICON_SCRIPT + '\n' + asset('desktop.js')
    elif mobile:
        style += '\n' + asset('mobile.css')
        presentation = ICON_SCRIPT + '\n' + asset('mobile.js')
    setup = """'use strict';
let state=__STATE__,bridge=__BRIDGE__,seq=0,queue=[],busy=false,mode='ink',
    active=null,points=[],selected=new Set(),start=null,last=null,pan=null,
    pendingInk=null,continuousInk=false,deferredUpdate=null;
const $=id=>document.getElementById(id),canvas=$('paper'),ctx=canvas.getContext('2d');
"""
    engine = setup + '\n'.join(asset(name) for name in (
        'drawing.js', 'queue.js', 'viewport.js', 'input.js', 'boot.js'))
    engine = engine.replace('__MAX_COMMAND__', str(MAX_COMMAND)).replace(
        '__SEND_COMMAND__', 'console.info(command)' if console_bridge else 'location.href=command')
    # Substitute code first and user-controlled values last. Marker-like titles
    # remain data, never another pass through template expansion.
    engine = engine.replace('__BRIDGE__', json.dumps(bridge))
    # Compose before inserting state to protect titles containing template markers.
    template = asset('document.html').replace('__STYLE__', style).replace('__CHROME__', chrome)
    template = template.replace('__ENGINE__', engine).replace(
        '__PRESENTATION__', '<script>\n' + presentation + '\n</script>')
    return template.replace('__STATE__', json.dumps(state, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c'))
