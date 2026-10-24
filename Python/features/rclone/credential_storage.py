"""Consistent credential retention choices across desktop and mobile."""

SESSION_TITLE = 'Session-Only'
PERSISTENT_TITLE = 'Persistent credential storage'
SESSION_DESCRIPTION = (
    'Keep unlocked credentials in memory until you lock them or exit Logistics. '
    'Unlock the ZIP again next time; no passwords are saved. '
    'For crypt remotes, this also enables encrypted LocalCrypt copies.')
PERSISTENT_DESCRIPTION = (
    'Save credentials on this device so the remotes remain available after restarting Logistics. '
    'The saved credentials are not protected by the ZIP password. '
    'Use Forget Credentials to remove saved access.')
SAVED_COPY_NOTE = (
    'A saved copy already exists for this package. Session-Only does not delete it. '
    'Forget the package to remove saved access.')
SHARED_NOTE = (
    'Both choices let you connect to Cloud. Your password-protected ZIP is kept in either case. '
    'Regular Local files remain readable after locking.')
