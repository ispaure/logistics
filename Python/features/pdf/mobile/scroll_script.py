"""Script for a self-contained PDF scroll surface. Page pixels arrive on demand."""

SHELL = '''<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:;
    script-src 'nonce-pdf-view'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<style>
:root { color-scheme: light dark; }
html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; }
#scroll { position: absolute; inset: 0; overflow: auto; overflow-anchor: none;
    overscroll-behavior: none; -webkit-touch-callout: none; user-select: none; scrollbar-width: none; }
#scroll::-webkit-scrollbar { display: none; }
#pages { position: relative; }
.sheet { position: absolute; overflow: hidden; background: white; color: black; }
.sheet img { display: block; width: 100%; height: 100%; pointer-events: none; }
.sheet button { position: absolute; border: 0; background: transparent; }
#lens { position: absolute; z-index: 2; width: 180px; height: 140px; border-radius: 18px;
    background-color: black; background-repeat: no-repeat; pointer-events: none;
    box-shadow: 0 2px 10px #0009; }
#lens button { pointer-events: auto; position: absolute; left: 0; width: 36px; height: 36px;
    border: 0; border-radius: 50%; background: #222d; color: white; font-size: 20px; }
#lens button + button { bottom: 0; }
</style></head><body>
<div id="scroll" role="region" aria-label="PDF document"><div id="pages"></div></div>
<div id="lens" hidden><button aria-label="Increase magnifier zoom">+</button>
<button aria-label="Decrease magnifier zoom">−</button></div>
<script nonce="pdf-view">
(() => {
    const ratios = PAGE_RATIOS;
    const scroll = document.getElementById('scroll'), pages = document.getElementById('pages');
    const lens = document.getElementById('lens');
    const nodes = new Map(), gap = 10;
    let magnifier = false, magnification = 190, held = false, moved = false, holdTimer, touchOrigin;
    let rows = [], width = 0, height = 0, zoom = 1, revision = 0;
    let action = null, pinch = null;

    function pageAt(y) {
        let lo = 0, hi = rows.length;
        while (lo + 1 < hi) {
            const mid = (lo + hi) >> 1;
            if (rows[mid].top <= y) lo = mid;
            else hi = mid;
        }
        return lo;
    }

    function anchor(y) {
        const page = pageAt(y), row = rows[page];
        return [page, row ? (y - row.top) / row.step : 0];
    }

    function geometry() {
        width = scroll.clientWidth;
        height = scroll.clientHeight;
        const totalWidth = width * zoom;
        let top = 0;
        rows = ratios.map(ratio => {
            const w = Math.min(Math.max(1, width - 2 * gap), Math.max(1, height - gap) * ratio);
            const h = Math.max(1, w / ratio) * zoom;
            const step = Math.ceil(Math.max(1, height / 3, h + gap));
            const row = {top, step, h, w: w * zoom};
            top += step;
            return row;
        });
        pages.style.width = totalWidth + 'px';
        const last = rows[rows.length - 1];
        pages.style.height = Math.max(top, last.top + height) + 'px';
        for (const [index, node] of nodes) place(index, node);
    }

    function place(index, node) {
        const row = rows[index];
        node.style.cssText = 'top:' + row.top + 'px;left:' + (width * zoom - row.w) / 2
            + 'px;width:' + row.w + 'px;height:' + row.h + 'px';
    }

    function seek(page, offset, x, scale, version) {
        if (!scroll.clientWidth || !scroll.clientHeight) return false;
        revision = version;
        zoom = scale;
        geometry();
        scroll.scrollLeft = x * width * zoom - width / 2;
        scroll.scrollTop = Math.round(rows[page].top + offset * rows[page].step);
        reconcile();
        return true;
    }

    function reconcile() {
        if (!rows.length || !height) return [];
        const first = pageAt(scroll.scrollTop);
        const last = pageAt(scroll.scrollTop + height);
        const wanted = [first];
        for (let i = first + 1; i <= last + 1 && i < rows.length; i++) wanted.push(i);
        if (first > 0) wanted.push(first - 1);
        for (const [index, node] of nodes) {
            if (!wanted.includes(index)) {
                if (!lens.hidden) clearLens();
                node.remove();
                nodes.delete(index);
            }
        }
        return wanted;
    }

    function put(index, source, links, version) {
        if (version !== revision || !reconcile().includes(index) || nodes.has(index)) return false;
        const node = document.createElement('div');
        node.className = 'sheet';
        node.dataset.page = index;
        if (source) {
            const image = new Image();
            image.alt = 'Page ' + (index + 1);
            image.src = source;
            node.append(image);
        } else {
            node.textContent = 'Could not render page ' + (index + 1);
        }
        for (const link of links) {
            const button = document.createElement('button');
            const [left, top, right, bottom] = link.rect;
            button.style.cssText = 'left:' + left * 100 + '%;top:' + top * 100 + '%;width:'
                + (right - left) * 100 + '%;height:' + (bottom - top) * 100 + '%';
            button.setAttribute('aria-label', 'Go to page ' + (link.index + 1));
            button.addEventListener('click', event => {
                event.stopPropagation();
                if (acceptedClick(event)) action = {target: link.index, from: index};
            });
            node.append(button);
        }
        place(index, node);
        nodes.set(index, node);
        pages.append(node);
        return true;
    }

    function state() {
        if (!scroll.clientWidth || !scroll.clientHeight) return null;
        if (scroll.clientWidth !== width || scroll.clientHeight !== height) {
            const [page, offset] = anchor(scroll.scrollTop);
            seek(page, offset, width ? (scroll.scrollLeft + width / 2) / (width * zoom) : .5, zoom, revision);
        }
        const wanted = reconcile();
        const [page, offset] = anchor(scroll.scrollTop);
        const result = {page, offset, zoom, x: (scroll.scrollLeft + width / 2) / (width * zoom),
            wanted, missing: wanted.filter(index => !nodes.has(index)), action, revision};
        action = null;
        return result;
    }

    scroll.addEventListener('scroll', reconcile, {passive: true});
    function acceptedClick(event) {
        return !held && !moved && event.pointerType !== 'pen';
    }
    scroll.addEventListener('click', event => { if (acceptedClick(event)) action = {tap: true}; });
    scroll.addEventListener('contextmenu', event => event.preventDefault());

    function fingers(event) {
        const [a, b] = event.touches;
        return {distance: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY),
            x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2};
    }

    function showLens(x, y) {
        const page = pageAt(scroll.scrollTop + y), node = nodes.get(page);
        const image = node?.querySelector('img');
        if (!image) {
            lens.hidden = true;
            return;
        }
        const rect = image.getBoundingClientRect();
        if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
            lens.hidden = true;
            return;
        }
        const factor = magnification / 100;
        lens.style.left = Math.max(0, Math.min(width - 180, x - 90)) + 'px';
        lens.style.top = Math.max(0, y - 176) + 'px';
        lens.style.backgroundImage = 'url("' + image.src + '")';
        lens.style.backgroundSize = (rect.width * factor) + 'px ' + (rect.height * factor) + 'px';
        lens.style.backgroundPosition = (90 - (x - rect.left) * factor) + 'px '
            + (70 - (y - rect.top) * factor) + 'px';
        lens.hidden = false;
    }

    function clearLens() {
        clearTimeout(holdTimer);
        lens.hidden = true;
        lens.style.backgroundImage = '';
    }

    for (const [index, button] of [...lens.children].entries()) {
        button.addEventListener('touchstart', event => {
            event.preventDefault();
            const next = Math.min(300, Math.max(150, magnification + (index ? -10 : 10)));
            action = {magnification: next};
            magnification = next;
            if (touchOrigin) showLens(...touchOrigin);
        }, {passive: false});
    }

    scroll.addEventListener('touchstart', event => {
        if (event.touches.length === 1) {
            held = moved = false;
            const point = event.touches[0];
            touchOrigin = [point.clientX, point.clientY];
            if (magnifier && point.touchType !== 'stylus') {
                holdTimer = setTimeout(() => {
                    showLens(...touchOrigin);
                    held = !lens.hidden;
                }, 400);
            }
        } else {
            moved = true;
            clearLens();
        }
        if (event.touches.length !== 2 || !height) return;
        event.preventDefault();
        const point = fingers(event);
        pinch = {distance: Math.max(1, point.distance), zoom,
            x: (scroll.scrollLeft + point.x) / (width * zoom),
            anchor: anchor(scroll.scrollTop + point.y)};
    }, {passive: false});

    scroll.addEventListener('touchmove', event => {
        if (event.touches.length === 1 && touchOrigin) {
            const point = event.touches[0], x = point.clientX, y = point.clientY;
            if (held) {
                event.preventDefault();
                touchOrigin = [x, y];
                showLens(x, y);
            } else if (Math.hypot(x - touchOrigin[0], y - touchOrigin[1]) > 8) {
                moved = true;
                clearTimeout(holdTimer);
            }
        }
        if (!pinch || event.touches.length !== 2) return;
        event.preventDefault();
        const point = fingers(event), [page, offset] = pinch.anchor;
        zoom = Math.min(6, Math.max(1, pinch.zoom * point.distance / pinch.distance));
        geometry();
        scroll.scrollTop = Math.round(rows[page].top + offset * rows[page].step - point.y);
        scroll.scrollLeft = pinch.x * width * zoom - point.x;
    }, {passive: false});

    function endPinch(event) {
        pinch = null;
        if (event.type === 'touchcancel') moved = true;
        clearLens();
        touchOrigin = null;
        if (held && event.cancelable) event.preventDefault();
    }
    scroll.addEventListener('touchend', endPinch, {passive: false});
    scroll.addEventListener('touchcancel', endPinch);
    window.pdf = {
        seek, put, state,
        magnifier(enabled, percent) {
            magnifier = enabled;
            magnification = percent;
            if (!enabled) clearLens();
        },
        clear(version) {
            revision = version;
            clearLens();
            pages.replaceChildren();
            nodes.clear();
            action = null;
        }
    };
})();
</script></body></html>'''
