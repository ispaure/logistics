"""Path-free completion copy and notification policy shared by both hosts."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.runtime.notifications import Completion

# Allow the person to navigate away before reporting an outcome separately
# from the progress view. Routine copies and immediate errors stay in context.
TRANSFER_NOTICE_SECONDS = 30


def start_transfer_notice():
    return Completion(TRANSFER_NOTICE_SECONDS)


def transfer_notice(completion, outcome, *, observed, details, locked=False):
    if locked:
        title = 'Transfer needs attention'
        message = 'Unlock in Logistics to review the transfer.'
    elif outcome == 'failure':
        title = 'Transfer needs attention'
        message = f'Open {details} to review what changed before retrying.'
    else:
        title = 'Transfer complete'
        message = f'Open {details} for details.'
    return completion.finish('transfer', title, message, outcome=outcome, observed=observed)
