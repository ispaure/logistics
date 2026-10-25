"""Sequential phase execution, dependency gates, bounded waits and process cleanup."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Queue
import signal
import shutil
import subprocess
from threading import Event, Thread
import time

from .locking import workspace_lock
from .redaction import Redactor


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def stop_process(process):
    if os.name == 'nt':
        process.kill_tree()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)


class Executor:
    def __init__(self, *, cancelled=None, event=None):
        self.cancelled = cancelled if cancelled is not None else Event()
        self.event = event or (lambda value: None)

    def run(self, plan, output, *, confirmed=False):
        if plan.effect in {'deploy', 'upload', 'publish'} and not confirmed:
            raise ValueError('This operation requires explicit confirmation after reviewing the plan.')
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        report = dict(schema=1, project=plan.project, operation=plan.operation,
                      plan_identity=plan.identity, source=plan.source, backend=plan.backend,
                      started_at=timestamp(), status='queued', phases=[])
        def save():
            temporary = output / 'result.tmp'
            temporary.write_text(json.dumps(report, indent=2) + '\n')
            temporary.replace(output / 'result.json')
        save()
        started = time.monotonic()
        try:
            with workspace_lock(Path(plan.workspace) / 'operation.lock'):
                report['status'] = 'running'
                save()
                states = {}
                for phase in plan.phases:
                    blocked = any(states[name] != 'passed' for name in phase.dependencies)
                    if (self.cancelled.is_set() or blocked) and not phase.always:
                        row = dict(id=phase.id, required=phase.required, status='skipped',
                                   reason='cancelled' if self.cancelled.is_set() else 'dependency did not pass', seconds=0)
                    else:
                        row = self.run_phase(phase, output, plan.secret_environment)
                    states[phase.id] = row['status']
                    report['phases'].append(row)
                    self.event(dict(type='phase', **row))
                    save()
                report['status'] = ('cancelled' if self.cancelled.is_set() else
                    'failed' if any(row['required'] and row['status'] != 'passed' for row in report['phases']) else 'passed')
                report.update(finished_at=timestamp(), seconds=time.monotonic() - started)
                save()
        except (OSError, RuntimeError) as error:
            report.update(status='failed', error=Redactor()(str(error)), finished_at=timestamp(),
                          seconds=time.monotonic() - started)
            save()
        self.event(dict(type='finished', status=report['status'], seconds=report['seconds']))
        return report

    def run_phase(self, phase, output, secret_environment):
        row = dict(id=phase.id, required=phase.required, kind=phase.kind,
                   started_at=timestamp(), status='running', log=phase.id + '.log')
        self.event(dict(type='phase', **row))
        started = time.monotonic()
        environment = dict(os.environ, **phase.environment)
        redact = Redactor(environment.get(name) for name in secret_environment)
        messages = Queue(maxsize=128)
        process = None
        tail = []
        try:
            if os.name == 'nt':
                from .windows_process import WindowsProcess
                process = WindowsProcess(list(phase.argv), cwd=phase.cwd, env=environment)
            else:
                process = subprocess.Popen(list(phase.argv), cwd=phase.cwd, env=environment,
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            def read():
                try:
                    while chunk := process.stdout.readline(16384):
                        messages.put(chunk)
                finally:
                    messages.put(None)
            reader = Thread(target=read, daemon=True)
            reader.start()
            finished = False
            # Preserve the child's CRLF rather than translating it a second
            # time on Windows (which would produce CRCRLF/blank log lines).
            with (output / row['log']).open('w', encoding='utf-8', newline='') as stream:
                while not finished or process.poll() is None:
                    if self.cancelled.is_set() and not phase.always:
                        row['status'] = 'cancelled'
                        stop_process(process)
                    elif time.monotonic() - started >= phase.timeout:
                        row['status'] = 'timeout'
                        stop_process(process)
                    if finished:
                        time.sleep(.05)
                        continue
                    try:
                        message = messages.get(timeout=.05)
                    except Empty:
                        continue
                    if message is None:
                        finished = True
                        continue
                    line = redact(message.decode('utf-8', errors='replace'))
                    stream.write(line)
                    stream.flush()
                    tail = (tail + line.splitlines())[-6:]
                    self.event(dict(type='output', phase=phase.id, text=line))
            reader.join(timeout=5)
            process.wait(timeout=5)
            row['exit_code'] = process.returncode
            if row['status'] == 'running':
                row['status'] = 'passed' if process.returncode == 0 else 'failed'
            if row['status'] == 'passed' and phase.artifacts:
                row['artifacts'] = []
                directory = output / 'artifacts'
                directory.mkdir(exist_ok=True)
                for index, value in enumerate(phase.artifacts):
                    source = Path(value)
                    if not source.is_file():
                        raise RuntimeError('Expected prepared artifact/report is missing: ' + source.name)
                    destination = directory / f'{phase.id}-{index}{source.suffix}'
                    shutil.copyfile(source, destination)
                    row['artifacts'].append(dict(path=str(destination), sha256=hashlib.sha256(destination.read_bytes()).hexdigest()))
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            row.update(status='failed', error=redact(str(error)))
        finally:
            if process is not None:
                stop_process(process)
                process.stdout.close()
                if os.name == 'nt':
                    process.close()
        row.update(seconds=time.monotonic() - started, finished_at=timestamp())
        if row['status'] != 'passed':
            row['summary'] = '\n'.join(tail)
        return row
