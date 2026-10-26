"""Failure-only WebKit isolation; never used as native acceptance evidence."""
import json
from pathlib import Path
from uuid import uuid4

from .web_checks import native_state, wait_for_text


async def diagnose_preview(app, original):
    """Check a fresh view on the failed host without retrying the failed case."""
    import toga
    from toga.style import Pack
    from services.documents.mobile_views import retire_webview

    report = dict(original=native_state(original), probes=[])
    destination = Path(app.paths.cache) / 'logistics-preview-diagnostics.json'
    parent = original.parent
    try:
        if parent is None:
            raise RuntimeError('Failed preview has no parent for a diagnostic sibling.')
        # These contain only fixed synthetic fixture text, never user content.
        for root in (None, 'https://logistics.invalid/' + uuid4().hex + '/'):
            probe = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False,
                                 style=Pack(flex=1))
            row = dict(root=root, rendered=False)
            report['probes'].append(row)
            try:
                parent.add(probe)
                probe.set_content(root, '<html><body>WebKit isolation fixture</body></html>')
                await wait_for_text(probe, 'WebKit isolation fixture')
                row['rendered'] = True
            except Exception as error:
                row['error'] = str(error)
            finally:
                row['native'] = native_state(probe)
                try:
                    parent.remove(probe)
                finally:
                    retire_webview(probe)
    except Exception as error:
        report['diagnostic_error'] = str(error)
    finally:
        destination.write_text(json.dumps(report, indent=2))
        print('LOGISTICS_PREVIEW_DIAGNOSTICS=' + json.dumps(report), flush=True)
