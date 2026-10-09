"""Structured rclone JSON statistics mapped to shared process updates.

Stats follow https://rclone.org/docs/#use-json-log and the core/stats schema.
Terminal text is retained as diagnostics; transfer counters never parse that text.
"""
import json
import math
import re
from commonUtils.ui.process_runner import ProcessUpdate


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


class RcloneProgressParser:
    def __init__(self):
        self.reset()

    def reset(self):
        self.attempt = 1
        self.metrics = {}
        self.error_records = 0
        self.warning_records = 0

    def _update(self, message, state='running'):
        done, total = self.metrics.get('bytes'), self.metrics.get('total_bytes')
        basis = 'bytes'
        if not total:
            done = (self.metrics.get('checks') or 0) + (self.metrics.get('files') or 0)
            total = (self.metrics.get('total_checks') or 0) + (self.metrics.get('total_files') or 0)
            basis = 'items'
        if done is None:
            total = 0
        self.metrics['progress_basis'] = basis
        return ProcessUpdate(done or 0, total or 0, message, state, self.attempt, dict(self.metrics))

    def __call__(self, line):
        try:
            record = json.loads(line)
        except ValueError:
            record = {'msg': line}
        if not isinstance(record, dict):
            return None
        message = str(record.get('msg', ''))
        stats = record.get('stats')
        level = str(record.get('level', '')).casefold()
        if not isinstance(stats, dict):
            if level in ('error', 'critical', 'alert', 'emergency'):
                self.error_records += 1
                self.metrics['last_error'] = message
                if self.metrics.get('errors') is None:
                    self.metrics['reported_errors'] = self.error_records
            elif level in ('warning', 'warn'):
                self.warning_records += 1
            self.metrics['warnings'] = self.warning_records
        match = re.search(r'Attempt (\d+)/(\d+) (failed|succeeded)', message)
        if match:
            attempt, maximum = int(match[1]), int(match[2])
            retrying = match[3] == 'failed' and attempt < maximum
            self.attempt = attempt + 1 if retrying else attempt
            if retrying:
                self.metrics.update(active_transfers=(), speed=None, eta=None)
            return self._update(message, 'retrying' if retrying else 'running')
        if isinstance(stats, dict):
            mapping = {'bytes': 'bytes', 'total_bytes': 'totalBytes', 'speed': 'speed', 'eta': 'eta',
                       'files': 'transfers', 'total_files': 'totalTransfers', 'checks': 'checks',
                       'total_checks': 'totalChecks', 'errors': 'errors', 'elapsed': 'elapsedTime',
                       'deleted': 'deletes', 'renamed': 'renames', 'listed': 'listed'}
            self.metrics.update({target: _number(stats.get(source)) for target, source in mapping.items()})
            self.metrics['warnings'] = self.warning_records
            if stats.get('lastError'):
                self.metrics['last_error'] = str(stats['lastError'])
            transfers = stats.get('transferring')
            self.metrics['active_transfers'] = tuple({
                'name': str(item.get('name', '')),
                'bytes': _number(item.get('bytes')), 'total_bytes': _number(item.get('size')),
                'speed': _number(item.get('speedAvg')) if _number(item.get('speedAvg')) is not None else _number(item.get('speed')),
                'eta': _number(item.get('eta')), 'percentage': _number(item.get('percentage')),
            } for item in transfers if isinstance(item, dict)) if isinstance(transfers, list) else None
            message = 'Transferring…' if self.metrics.get('total_bytes') else 'Checking / discovering files…'
            return self._update(message)
        if message:
            return self._update(message)
        return None
