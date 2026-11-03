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
        function read(kind, path, origin) {
            if (pending.size >= 128) throw Error('Too many pending data view reads.');
            return new Promise((resolve, reject) => {
                const id = ++serial;
                pending.set(id, {resolve, reject});
                postMessage({type: 'read', id, kind, path, origin});
            });
        }
        const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
        async function execute(code, dv, input) {
            return await new AsyncFunction('dv', 'dataview', 'input', code)(dv, dv, input);
        }
        async function run(scripts) {
            const results = [];
            for (const code of scripts) {
                let output = [], depth = 0;
                function emit(value) {
                    emitted += value.length;
                    if (emitted > 524288) throw Error('Data view output exceeds its limit.');
                    output.push(value);
                }
                const api = {
                    io: {load: async (path, origin) => (await read('load', path, origin)) ?? undefined},
                    paragraph: value => emit(literal(value) + '\n\n'),
                    span: value => emit(literal(value)),
                    header: (level, value) => {
                        if (!Number.isInteger(level) || level < 1 || level > 6) throw Error('Heading level must be 1–6.');
                        emit('#'.repeat(level) + ' ' + literal(value) + '\n\n');
                    },
                    list: values => emit(Array.from(values, value => '- ' + literal(value)).join('\n') + '\n\n'),
                    table: (headers, rows) => {
                        const head = Array.from(headers);
                        if (!head.length) throw Error('A table needs at least one column.');
                        const line = cells => '| ' + cells.map(literal).join(' | ') + ' |';
                        emit([line(head), '| ' + head.map(() => '---').join(' | ') + ' |',
                            ...Array.from(rows, row => line(Array.from(row)))].join('\n') + '\n\n');
                    },
                    view: async (path, input) => {
                        if (++depth > 16) { --depth; throw Error('Custom view nesting exceeds 16.'); }
                        try { const file = await read('view', path); await execute(file.code, dv, input); }
                        finally { --depth; }
                    }
                };
                // Unknown API calls fail visibly rather than silently producing empty data.
                const dv = new Proxy(api, {get(target, key) {
                    if (!(key in target)) throw Error('Unsupported Dataview API: dv.' + String(key));
                    return target[key];
                }});
                try { await execute(code, dv); }
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
