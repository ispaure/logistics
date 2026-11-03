"""Shared browser-worker runtime. Only structured messages reach native code."""

SCRIPT = r'''
(() => {
    window.logisticsDataView?.stop();
    const scripts = DATAVIEW_SCRIPTS;
    const state = {requests: [], results: [], done: false};
    function workerMain() {
        let serial = 0, pending = new Map(), emitted = 0;
        const text = value => value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
        const literal = value => text(value).replace(/\\/g, '\\\\').replace(/[\x00-\x1f]/g, ' ')
            .replace(/[|`*_{}\[\]<>()#!+\-.]/g, '\\$&');
        function read(kind, path, origin, metadata = false) {
            if (pending.size >= 128) throw Error('Too many pending data view reads.');
            return new Promise((resolve, reject) => {
                const id = ++serial;
                pending.set(id, {resolve, reject});
                postMessage({type: 'read', id, kind, path, origin, metadata});
            });
        }
        const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
        async function execute(code, dv, app, input) {
            return await new AsyncFunction('dv', 'dataview', 'app', 'input', code)(dv, dv, app, input);
        }
        async function run(scripts) {
            const results = [];
            let index;
            try { index = await read('index', undefined, undefined, true); }
            catch (error) {
                postMessage({type: 'done', results: scripts.map(() => 'Data view error: ' + literal(error.message))});
                return;
            }
            for (const code of scripts) {
                let output = [], depth = 0, nodes = 0, written = 0;
                const links = new WeakSet();
                const app = {vault: {getMarkdownFiles: () => index.pages.map(page => ({
                    path: page.file.path, basename: page.file.name,
                    name: page.file.path.split('/').pop(), extension: page.file.path.split('.').pop(),
                    stat: {size: page.file.size}
                }))}};
                const cell = value => value && typeof value === 'object' && links.has(value)
                    ? render({tag: 'a', _text: value.display, children: [], dataset: {}, href: value.path})
                    : literal(value);
                function emit(value) {
                    written += value.length;
                    if (emitted + written > 524288) throw Error('Data view output exceeds its limit.');
                    api.container.children.push(value);
                }
                // A small detached element tree: scripts never receive the browser DOM.
                function element(tag, options = {}, parent = null) {
                    if (!['ul', 'ol', 'li', 'a', 'p', 'span', 'div'].includes(tag))
                        throw Error('Unsupported data view element: ' + tag);
                    if (++nodes > 10000) throw Error('Data view elements exceed 10,000.');
                    const node = {tag, children: [], dataset: {},
                        _text: text(options.text), className: text(options.cls), href: text(options.href),
                        get textContent() { return this._text + this.children.map(child =>
                            typeof child === 'string' ? child : child.textContent).join(''); },
                        set textContent(value) { this._text = text(value); this.children.length = 0; },
                        createEl: (name, opts) => element(name, opts, node),
                        remove: () => {
                            const siblings = parent ? parent.children : output;
                            const position = siblings.indexOf(node);
                            if (position >= 0) siblings.splice(position, 1);
                        }};
                    if (parent) parent.children.push(node);
                    else output.push(node);
                    return node;
                }
                function render(node, indent = 0, marker = '- ') {
                    if (typeof node === 'string') return node;
                    const content = literal(node._text);
                    if (node.tag === 'ul' || node.tag === 'ol')
                        return node.children.map((child, index) => render(child, indent,
                            node.tag === 'ol' ? (index + 1) + '. ' : '- ')).join('') + (indent ? '' : '\n');
                    if (node.tag === 'li') {
                        const inline = node.children.filter(child => !['ul', 'ol'].includes(child.tag));
                        const nested = node.children.filter(child => ['ul', 'ol'].includes(child.tag));
                        return ' '.repeat(indent) + marker + content + inline.map(child => render(child, indent)).join('')
                            + '\n' + nested.map(child => render(child, indent + 4)).join('');
                    }
                    const children = node.children.map(child => render(child, indent)).join('');
                    if (node.tag === 'a') {
                        const path = node.dataset.href || node.href;
                        // Only library paths become links. Authored HTML remains literal.
                        if (!path || /[\\\x00-\x1f]/.test(path) || /^(?:\/|[a-z][a-z0-9+.-]*:)/i.test(path)
                                || path.split('/').some(part => part.startsWith('.')))
                            throw Error('Data view links require paths inside this Notes Library.');
                        const base = index.current.file.folder.split('/').filter(Boolean);
                        const parts = path.split('/');
                        while (base.length && parts.length && base[0] === parts[0]) { base.shift(); parts.shift(); }
                        const target = [...base.map(() => '..'), ...parts].map(encodeURIComponent).join('/');
                        return '[' + content + children + '](<' + target + '>)';
                    }
                    return content + children + (['p', 'div'].includes(node.tag) ? '\n\n' : '');
                }
                const api = {
                    app,
                    fileLink: (path, embed = false, display) => {
                        if (typeof path !== 'string' || embed) throw Error('Data views support non-embedded file links only.');
                        const link = {path, display: display == null ? path.split('/').pop().replace(/\.(md|markdown)$/i, '') : text(display)};
                        links.add(link);
                        return link;
                    },
                    current: () => index.current,
                    pages: source => {
                        let pages = index.pages;
                        if (source != null && source !== '') {
                            if (typeof source !== 'string' || !/^"[^"\x00-\x1f]*"$/.test(source))
                                throw Error('Unsupported Dataview page source: use a quoted folder path.');
                            const folder = source.slice(1, -1).replace(/\/+$/, '');
                            if (folder.startsWith('/') || folder.includes('\\') || folder.split('/').some(part => part.startsWith('.')))
                                throw Error('Data view page sources require library folder paths.');
                            pages = pages.filter(page => !folder || page.file.folder === folder || page.file.folder.startsWith(folder + '/'));
                        }
                        return {array: () => pages.slice(), [Symbol.iterator]: () => pages[Symbol.iterator]()};
                    },
                    container: element('div'),
                    io: {load: async (path, origin) => (await read('load', path, origin)) ?? undefined},
                    paragraph: value => emit(cell(value) + '\n\n'),
                    span: value => emit(cell(value)),
                    header: (level, value) => {
                        if (!Number.isInteger(level) || level < 1 || level > 6) throw Error('Heading level must be 1–6.');
                        emit('#'.repeat(level) + ' ' + literal(value) + '\n\n');
                    },
                    list: values => emit(Array.from(values, value => '- ' + cell(value)).join('\n') + '\n\n'),
                    table: (headers, rows) => {
                        const head = Array.from(headers);
                        if (!head.length) throw Error('A table needs at least one column.');
                        const line = cells => '| ' + cells.map(cell).join(' | ') + ' |';
                        emit([line(head), '| ' + head.map(() => '---').join(' | ') + ' |',
                            ...Array.from(rows, row => line(Array.from(row)))].join('\n') + '\n\n');
                    },
                    view: async (path, input) => {
                        if (++depth > 16) { --depth; throw Error('Custom view nesting exceeds 16.'); }
                        try { const file = await read('view', path); await execute(file.code, dv, app, input); }
                        finally { --depth; }
                    }
                };
                // Unknown API calls fail visibly rather than silently producing empty data.
                const dv = new Proxy(api, {get(target, key) {
                    if (!(key in target)) throw Error('Unsupported Dataview API: dv.' + String(key));
                    return target[key];
                }});
                try {
                    await execute(code, dv, app);
                    output = output.map(value => render(value));
                    emitted += output.reduce((total, value) => total + value.length, 0);
                    if (emitted > 524288) throw Error('Data view output exceeds its limit.');
                }
                catch (error) { output = ['Data view error: ' + literal(error?.message || error) + '\n']; }
                results.push(output.join(''));
            }
            postMessage({type: 'done', results});
        }
        onmessage = event => {
            const message = event.data;
            if (message.type === 'start') { run(message.scripts); return; }
            const request = pending.get(message.id);
            if (!request) return;
            pending.delete(message.id);
            if (message.error) request.reject(Error(message.error));
            else request.resolve(message.value);
        };
    }
    const url = URL.createObjectURL(new Blob(['(' + workerMain.toString() + ')()'], {type: 'text/javascript'}));
    let worker;
    try { worker = new Worker(url); }
    catch (error) {
        URL.revokeObjectURL(url);
        window.logisticsDataView = {
            poll: () => JSON.stringify({requests: [], done: true,
                results: scripts.map(() => 'Data view error: JavaScript workers are unavailable.')}),
            stop: () => {}, reply: () => {}
        };
        return;
    }
    URL.revokeObjectURL(url);
    let timer;
    function finish(results) {
        if (state.done) return;
        clearTimeout(timer);
        worker.terminate();
        state.results = results;
        state.requests = [];
        state.done = true;
    }
    worker.onmessage = event => {
        const message = event.data;
        if (message.type === 'read') state.requests.push(message);
        else if (message.type === 'done') finish(message.results);
    };
    worker.onerror = () => finish(scripts.map(() => 'Data view error: JavaScript worker failed.'));
    timer = setTimeout(() => finish(scripts.map(() => 'Data view error: execution exceeded 30 seconds.')), 30000);
    window.logisticsDataView = {
        poll: () => {
            const requests = state.requests.splice(0);
            return JSON.stringify({requests, done: state.done, results: state.results});
        },
        reply: message => { if (!state.done) worker.postMessage(message); },
        stop: () => { clearTimeout(timer); worker.terminate(); state.requests = []; state.results = []; }
    };
    worker.postMessage({type: 'start', scripts});
})();
'''

POLL = 'window.logisticsDataView?.poll() || null'
STOP = 'window.logisticsDataView?.stop(); delete window.logisticsDataView;'


def worker_policy(html):
    """Permit only the disposable worker; network and authored HTML stay inert."""
    return html.replace("default-src 'none';", "default-src 'none'; worker-src blob:; script-src 'unsafe-eval';", 1)
