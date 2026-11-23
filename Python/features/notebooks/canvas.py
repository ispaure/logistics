"""Compose offline notebook assets for desktop and native mobile WebViews."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from functools import cache
import json
from commonUtils.ui.native.web_dropdown import DROPDOWN_CSS, DROPDOWN_SCRIPT
from .assets import asset
from .bridge import MAX_COMMAND
from .icons import ICON_SCRIPT
from .protocol import canvas_state_json
from .templates import CATALOG, FORM_TEMPLATES, background


@cache
def _template_artwork_json():
    return json.dumps({name: (background(name), background(name, 'move') if name in FORM_TEMPLATES else None)
                       for name in CATALOG})


def editor_html(state, bridge, *, console_bridge=False, desktop=False, mobile=False, stylesheet='', paper_preview=None):
    if paper_preview is None:
        from .preferences import paper_preview_enabled
        paper_preview = paper_preview_enabled()
    if desktop and mobile:
        raise ValueError('Choose one notebook presentation.')
    from services.appearance_palette import css_variables
    style = css_variables() + '\n' + asset('base.css')
    chrome = asset('controls.html')
    presentation = ''
    if desktop:
        style += '\n' + asset('desktop.css')
        chrome = asset('desktop.html')
        presentation = asset('desktop.js')
    elif mobile:
        style += '\n' + asset('mobile.css')
        presentation = asset('mobile.js')
    style += '\n' + asset('theme.css') + '\n' + DROPDOWN_CSS + '\n' + stylesheet
    presentation = DROPDOWN_SCRIPT + '\n' + presentation
    setup = """'use strict';
let state=__STATE__,bridge=__BRIDGE__,seq=0,queue=[],busy=false,mode='ink',
    active=null,points=[],selected=new Set(),start=null,last=null,pan=null,pageSwipe=false,
    pendingInk=null,continuousInk=false,deferredUpdate=null;
const $=id=>document.getElementById(id),canvas=$('paper'),ctx=canvas.getContext('2d');
const canvasPixelLimit=__CANVAS_PIXEL_LIMIT__;
const templateArtwork=__TEMPLATE_ARTWORK__;
"""
    # Publish the page and draft together. An independent front buffer can show
    # the cleared preview before the replacement stroke reaches the display.
    # The page, live preview and mask each own a backing bitmap. CSS zoom must
    # not multiply all three without bound. Desktop gets a larger screen budget;
    # neither budget changes native ink geometry or exported document quality.
    setup = setup.replace('__CANVAS_PIXEL_LIMIT__', str((8 if mobile else 16) * 1024 * 1024))
    setup = setup.replace('__TEMPLATE_ARTWORK__', _template_artwork_json())
    engine = setup + ICON_SCRIPT + '\n' + '\n'.join(asset(name) for name in (
        'drawing.js', 'queue.js', 'viewport.js', 'palm.js', 'input.js', 'zoom.js', 'images.js', 'selection.js', 'links.js', 'touch_navigation.js', 'boot.js'))
    engine = engine.replace('__MAX_COMMAND__', str(MAX_COMMAND)).replace(
        '__SEND_COMMAND__', 'console.info(command)' if console_bridge else 'location.href=command')
    # Substitute code first and user-controlled values last. Marker-like titles
    # remain data, never another pass through template expansion.
    engine = engine.replace('__BRIDGE__', json.dumps(bridge))
    # Compose before inserting state to protect titles containing template markers.
    template = asset('document.html').replace('__STYLE__', style).replace('__CHROME__', chrome)
    classes = ['notebook-desktop' if desktop else 'notebook-mobile'] if desktop or mobile else []
    if paper_preview:
        classes.append('muted-paper-preview')
    template = template.replace('__PRESENTATION_CLASS__', ' '.join(classes))
    template = template.replace('__ENGINE__', engine).replace(
        '__PRESENTATION__', '<script>\n' + presentation + '\n</script>')
    if state is None:
        if not desktop:
            raise ValueError('Only the desktop canvas receives injected state.')
        return template.replace('__STATE__', 'globalThis.__notebookInitialState').replace(
            'const canvasPixelLimit=', 'delete globalThis.__notebookInitialState;\nconst canvasPixelLimit=', 1)
    return template.replace('__STATE__', canvas_state_json(state).replace('<', '\\u003c'))
