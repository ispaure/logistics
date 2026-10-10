"""Validated feature preferences and command-scoped Git defaults."""
from copy import deepcopy
from pathlib import Path
import re

DEFAULTS = {
    'project_folder': '', 'restore_windows': True, 'auto_refresh': True,
    'fetch_updates': False, 'fetch_minutes': 10, 'confirm_switch': False,
    'confirm_stage': False, 'terminal': 'System default',
    'select_all_commit': False, 'push_after_commit': False, 'fixed_commit_font': False,
    'commit_guide': 72, 'commit_template': '', 'diff_font': '', 'diff_limit_kb': 1024,
    'diff_ignore_patterns': '', 'wrap_diff': False, 'diff_colors': {},
    'pull_strategy': 'ff-only', 'no_ff': False, 'stage_double_click': False,
    'recursive_submodules': True, 'check_submodules': True, 'push_tags': False,
    'global_ignore': '', 'author_date': False, 'ssl_verify': True,
    'keep_backups': True, 'full_output': False, 'allow_force_push': False,
    'debug_menu': False, 'gpg_program': '', 'default_usernames': {},
    'accounts': [], 'custom_actions': [], 'external_diff': '', 'external_merge': '',
}


def validate_options(values):
    if not isinstance(values, dict): raise ValueError('Git options must be an object.')
    result = deepcopy(DEFAULTS)
    for key, value in values.items():
        if key not in DEFAULTS: continue
        default = DEFAULTS[key]
        if type(value) is not type(default): raise ValueError(f'Invalid Git preference: {key}')
        result[key] = deepcopy(value)
    for key, low, high in [('fetch_minutes', 1, 1440), ('commit_guide', 20, 200), ('diff_limit_kb', 16, 16384)]:
        if not low <= result[key] <= high: raise ValueError(f'{key} is outside the supported range.')
    if result['pull_strategy'] not in ('ff-only', 'merge', 'rebase'): raise ValueError('Invalid pull strategy.')
    if result['terminal'] not in ('System default', 'Terminal', 'iTerm'): raise ValueError('Invalid terminal.')
    for host, username in result['default_usernames'].items(): validate_account({'host': host, 'username': username, 'protocol': 'https'})
    for account in result['accounts']: validate_account(account)
    shortcuts = set()
    for action in result['custom_actions']:
        if not isinstance(action, dict) or set(action) != {'caption', 'program', 'arguments', 'shortcut'}:
            raise ValueError('Invalid custom action.')
        if not all(isinstance(action[key], str) for key in ('caption', 'program', 'shortcut')) or not action['caption'].strip() or not action['program'].strip():
            raise ValueError('Custom actions need a caption and program.')
        if not isinstance(action['arguments'], list) or not all(isinstance(arg, str) and '\0' not in arg for arg in action['arguments']):
            raise ValueError('Custom action arguments must be a JSON list of strings.')
        shortcut = action['shortcut'].strip()
        if shortcut and shortcut in shortcuts: raise ValueError('Custom action shortcuts must be unique.')
        shortcuts.add(shortcut)
    for kind, colors in result['diff_colors'].items():
        if kind not in ('add', 'remove') or not isinstance(colors, list) or len(colors) != 2 or not all(re.fullmatch(r'#[0-9a-fA-F]{6}', color) for color in colors):
            raise ValueError('Invalid diff colors.')
    return result


def validate_account(account):
    if not isinstance(account, dict): raise ValueError('Invalid account.')
    host, user = account.get('host', ''), account.get('username', '')
    if not isinstance(host, str) or len(host) > 255 or not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?(?::[0-9]{1,5})?', host):
        raise ValueError('Enter a host name, without a URL or path.')
    if not isinstance(user, str) or not user or len(user) > 256 or any(ord(c) < 32 for c in user): raise ValueError('Enter a username without control characters (up to 256 characters).')
    if account.get('protocol') not in ('https', 'ssh'): raise ValueError('Choose HTTPS or SSH.')
    if 'helper' in account and account['helper'] not in ('osxkeychain', 'libsecret', 'manager'): raise ValueError('Unsupported credential helper.')
    if 'default' in account and not isinstance(account['default'], bool): raise ValueError('Invalid account default.')
    if 'provider' in account and not isinstance(account['provider'], str): raise ValueError('Invalid provider.')
    if set(account) - {'host', 'username', 'protocol', 'provider', 'default', 'helper'}: raise ValueError('Secrets cannot be saved in account preferences.')


def git_defaults(options):
    values = {}
    if options['global_ignore']: values['core.excludesFile'] = str(Path(options['global_ignore']).expanduser())
    if options['gpg_program']: values['gpg.program'] = options['gpg_program']
    if not options['ssl_verify']: values['http.sslVerify'] = 'false'
    for host, username in options['default_usernames'].items(): values[f'credential.https://{host}.username'] = username
    for account in options['accounts']:
        if account.get('default') and account['protocol'] == 'https':
            values[f'credential.https://{account["host"]}.username'] = account['username']
            helper = account.get('helper')
            if helper in ('osxkeychain', 'manager', 'libsecret'):
                values[f'credential.https://{account["host"]}.helper'] = ['', helper]
                if helper == 'manager':
                    from .accounts import credential_store
                    values['credential.credentialStore'] = credential_store()
    return values
