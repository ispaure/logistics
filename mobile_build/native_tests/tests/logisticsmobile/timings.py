"""Monotonic native-suite diagnostics; assertions and scheduling stay unchanged."""
from contextlib import contextmanager, nullcontext
import json
from pathlib import Path
import time


class SuiteTimings:
    def __init__(self, path, *, clock=time.perf_counter, emit=print):
        self.path, self.clock, self.emit = Path(path), clock, emit
        self.started = self.previous_case = clock()
        self.active, self.records, self.checkpoints = [], [], []
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def section(self, name, **details):
        row = dict(name=name, details=details, started_s=self.clock() - self.started,
                   parent=self.active[-1]['name'] if self.active else None, status='running')
        self.active.append(row)
        self.records.append(row)
        child_seconds = 0
        try:
            yield
        except BaseException as error:
            row['status'] = type(error).__name__
            raise
        else:
            row['status'] = 'ok'
        finally:
            row['elapsed_s'] = self.clock() - self.started - row['started_s']
            child_seconds = row.pop('_child_seconds', 0)
            row['self_s'] = max(0, row['elapsed_s'] - child_seconds)
            self.active.pop()
            if self.active:
                parent = self.active[-1]
                parent['_child_seconds'] = parent.get('_child_seconds', 0) + row['elapsed_s']
            self.emit('LOGISTICS_NATIVE_TIMING=' + json.dumps(row), flush=True)
            # Keep completed measurements and the active outer sections even if
            # a later UIKit/WebKit crash cannot produce the final suite report.
            self.write()

    def checkpoint(self, case):
        now = self.clock()
        self.checkpoints.append(dict(case=case, since_previous_case_s=now - self.previous_case))
        self.previous_case = now
        self.write()

    def summary(self):
        groups = {}
        for row in self.records:
            if 'elapsed_s' not in row:
                continue
            # Orientation/cycle samples aggregate by panel; full events remain
            # in the cache/log without inflating the chunked acceptance report.
            key = (row['name'], row['details'].get('panel', ''))
            group = groups.setdefault(key, dict(name=key[0], panel=key[1], count=0,
                elapsed_s=0, self_s=0, max_s=0, failures=0))
            group['count'] += 1
            group['elapsed_s'] += row['elapsed_s']
            group['self_s'] += row['self_s']
            group['max_s'] = max(group['max_s'], row['elapsed_s'])
            group['failures'] += row['status'] != 'ok'
        return dict(elapsed_s=self.clock() - self.started, sections=list(groups.values()),
                    checkpoints=self.checkpoints,
                    note='Nested elapsed totals overlap. Checkpoints measure time since the previous successful case.')

    def write(self):
        value = dict(summary=self.summary(), records=[{k: v for k, v in row.items()
            if not k.startswith('_')} for row in self.records])
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value) + '\n')
        temporary.replace(self.path)


def section(app, name, **details):
    timer = getattr(app, '_native_suite_timings', None)
    return timer.section(name, **details) if timer is not None else nullcontext()


async def measure(app, name, operation, **details):
    with section(app, name, **details):
        return await operation
