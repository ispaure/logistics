"""rclone JSON stats and built-in retry messages mapped to shared process updates."""
import json
import re
from commonUtils.ui.process_runner import ProcessUpdate
from commonUtils.filesystem import format_size


class RcloneProgressParser:
    def __init__(self):
        self.attempt = 1

    def __call__(self, line):
        try:
            record = json.loads(line)
        except ValueError:
            record = {'msg': line}
        if not isinstance(record, dict):
            return None
        message = str(record.get('msg', ''))
        match = re.search(r'Attempt (\d+)/(\d+) (failed|succeeded)', message)
        if match:
            attempt, maximum = int(match[1]), int(match[2])
            retrying = match[3] == 'failed' and attempt < maximum
            self.attempt = attempt + 1 if retrying else attempt
            return ProcessUpdate(message=message, state='retrying' if retrying else 'running', attempt=self.attempt)
        stats = record.get('stats')
        if isinstance(stats, dict):
            done, total = stats.get('bytes', 0), stats.get('totalBytes', 0)
            speed = stats.get('speed', 0)
            eta = stats.get('eta')
            message = (f'{format_size(done)} / {format_size(total)} · {format_size(speed)}/s · '
                       f'{stats.get("transfers", 0)} / {stats.get("totalTransfers", 0)} files'
                       + (f' · ETA {eta}s' if eta is not None else '')
                       + (f' · {stats["errors"]} errors' if stats.get('errors') else ''))
            if not total:
                done, total = stats.get('checks', 0) + stats.get('transfers', 0), stats.get('totalChecks', 0) + stats.get('totalTransfers', 0)
            return ProcessUpdate(done, total, message, attempt=self.attempt)
        if message:
            return ProcessUpdate(message=message, attempt=self.attempt)
        return None
