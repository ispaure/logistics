"""User-visible Qt reader checkpoint outcomes."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"


def position_notice(progress, status):
    if status in {'fenced', 'stale'}:
        return ''
    if status == 'locked' or progress.locked_state:
        return 'Saved reader history is locked. Use Reader History to migrate it with the previous ZIP password.'
    if status == 'write-failed':
        return 'Could not save reading progress. The last saved position is retained.'
    if status == 'session-only':
        return 'Reading progress is available for this session.'
    if status == 'error':
        return 'Saved reading progress could not be read.'
    return ''
