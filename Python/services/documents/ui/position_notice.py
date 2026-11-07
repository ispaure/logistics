"""User-visible Qt reader checkpoint outcomes."""


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
