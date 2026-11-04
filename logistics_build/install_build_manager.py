"""Explicitly install a reviewed external manager Git checkout in this interpreter."""
import argparse
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import tomllib


READ_BUDGET = 110
READ_TIMEOUT = 45
INSTALL_TIMEOUT = 60


def diagnostic_tail(value):
    """Retain useful complete-line diagnostics without requiring an installed SDK."""
    try:
        text = value.decode(errors='replace') if isinstance(value, bytes) else str(value or '')
        secrets = [item for key,item in os.environ.items()
                   if re.search(r'(?i)token|password|secret|credential|private.?key', key) and len(item) >= 4]
        for secret in secrets:
            text = text.replace(secret, '[redacted]')
        try:
            from commonUtils.runtime.diagnostics.redaction import LineRedactor, redact
        except ImportError:
            # Before commonUtils is initialized, discard URLs and sensitive
            # assignments entirely rather than exposing an unfiltered tail.
            text = re.sub(r'[a-zA-Z][a-zA-Z0-9+.-]{0,31}://[^\s]+', '[url redacted]', text)
            text = re.sub(r'(?is)-----BEGIN [^\r\n]*PRIVATE KEY-----.*?(?:-----END [^\r\n]*PRIVATE KEY-----|$)', '[private key redacted]', text, flags=re.DOTALL)
            text = re.sub(r'(?i)(authorization\s*[=:]\s*(?:(?:bearer|basic)\s+)?|(?:token|password|secret|credential|api[_-]?key)\s*[=:]\s*)[^\s]+', r'\1[redacted]', text)
            text = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})', '[redacted]', text)
        else:
            filter_line = LineRedactor(secrets)
            text = redact(''.join(filter_line(line) for line in text.splitlines(keepends=True)))
        text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text)
        return '\n'.join(text.splitlines()[-8:])[-2048:]
    except Exception:
        return '[diagnostic unavailable]'


def failure_evidence(error, *, attempt, step, retry, classification):
    # Diagnostic formatting/output can never replace the primary Git exception.
    try:
        print(json.dumps(dict(operation='pinned-manager-read', attempt=attempt, step=step,
            exit_code=getattr(error,'returncode',None), retry=retry, classification=classification,
            diagnostic_tail=diagnostic_tail(getattr(error,'stderr',None)))), file=sys.stderr)
    except Exception:
        pass


def transport_reset(error):
    """Retry only the observed read-transport reset, never authentication/pin errors."""
    message = error.stderr or ''
    if isinstance(message, bytes):
        message = message.decode(errors='replace')
    message = message.lower()
    denied = ('authentication failed', 'could not read username', 'repository not found',
              'permission denied', 'http 401', 'http 403', 'not a valid object',
              'not our ref', 'reference is not', 'invalid')
    return error.returncode == 128 and 'connection reset by peer' in message and not any(text in message for text in denied)


def manager_project(root):
    project = root / 'Python' if (root / 'Python/pyproject.toml').is_file() else root
    config = project / 'pyproject.toml'
    if not config.is_file() or tomllib.loads(config.read_text()).get('project', {}).get('name') != 'build-deployment-manager':
        raise ValueError('Select a reviewed build-deployment-manager checkout.')
    return project


def clone_pin(pin, destination):
    """Publish a complete verified pin; every retry owns a fresh disposable sibling."""
    if (not isinstance(pin, dict) or type(pin.get('schema')) is not int or pin['schema'] != 1
            or type(pin.get('adapter_api')) is not int or pin['adapter_api'] != 1
            or not isinstance(pin.get('revision'), str) or not re.fullmatch(r'[0-9a-f]{40}', pin['revision'])
            or not isinstance(pin.get('repository'), str)
            or not re.fullmatch(r'https://github\.com/[\w.-]+/[\w.-]+(?:\.git)?', pin['repository'])):
        raise ValueError('Unsupported manager dependency schema or repository.')
    destination = Path(destination).expanduser().absolute()
    if (destination.exists() or any(path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction())
                                    for path in (destination, *destination.parents))):
        raise ValueError('Choose a new manager setup destination; existing checkouts and links are never changed.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + READ_BUDGET
    environment = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
    def read(arguments):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(arguments, READ_BUDGET)
        return subprocess.run(arguments, check=True, capture_output=True, text=True,
                              timeout=min(READ_TIMEOUT, remaining), env=environment)
    for attempt in (1, 2):
        with TemporaryDirectory(prefix='.' + destination.name + '-clone-', dir=destination.parent) as temporary:
            owner = Path(temporary)
            (owner / '.manager-installer-stage.json').write_text(json.dumps(dict(
                schema=1, destination=str(destination), repository=pin['repository'], revision=pin['revision'])))
            staged = owner / 'checkout'
            step = 'clone'
            try:
                read(['git', 'clone', '--no-checkout', pin['repository'], str(staged)])
                step = 'checkout'
                read(['git', '-C', str(staged), 'checkout', '--detach', pin['revision']])
                step = 'submodules'
                read(['git', '-C', str(staged), 'submodule', 'update', '--init', '--recursive'])
                step = 'verify'
                if read(['git', '-C', str(staged), 'rev-parse', 'HEAD']).stdout.strip() != pin['revision']:
                    raise ValueError('Cloned manager differs from the exact dependency pin.')
                modules = read(['git', '-C', str(staged), 'submodule', 'status', '--recursive']).stdout
                if any(line and line[0] != ' ' for line in modules.splitlines()):
                    raise ValueError('Cloned manager submodules do not match their pins.')
                if read(['git', '-C', str(staged), 'status', '--porcelain', '--untracked-files=all']).stdout.strip():
                    raise ValueError('Cloned manager source is not clean.')
                manager_project(staged)
                if destination.exists() or destination.is_symlink():
                    raise ValueError('Manager destination appeared during setup; preserve it and choose a new destination.')
                staged.rename(destination)
                print(json.dumps(dict(operation='pinned-manager-read', attempt=attempt, status='verified',
                                      revision=pin['revision'])), file=sys.stderr)
                return destination
            except subprocess.CalledProcessError as error:
                retry = step in ('clone', 'submodules') and attempt == 1 and transport_reset(error)
                failure_evidence(error, attempt=attempt, step=step, retry=retry,
                    classification='transport-reset' if transport_reset(error) else 'not-retryable')
                if not retry:
                    raise
            except subprocess.TimeoutExpired as error:
                failure_evidence(error, attempt=attempt, step=step, retry=False, classification='timeout')
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path, nargs='?')
    parser.add_argument('--from-pin', type=Path, metavar='DESTINATION', help='Explicitly clone the pinned manager into a new setup location')
    args = parser.parse_args()
    if args.from_pin:
        pin = json.loads((Path(__file__).resolve().parents[1] / 'build-manager-dependency.json').read_text())
        try:
            args.checkout = clone_pin(pin, args.from_pin)
        except ValueError as error:
            parser.error(str(error))
    if args.checkout is None:
        parser.error('Supply a reviewed manager checkout or --from-pin DESTINATION.')
    root = args.checkout.expanduser().absolute()
    try:
        project = manager_project(root)
    except ValueError as error:
        parser.error(str(error))
    if importlib.util.find_spec('pip'):
        command=[sys.executable,'-m','pip','install','--no-deps','-e',str(project)]
    else:
        # Direct script invocation puts logistics_build/, not its parent, on
        # sys.path. Bootstrap must also work in an interpreter without pip.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from Scripts.development import find_uv
        uv=find_uv()
        if not uv:
            parser.error('This environment has no pip. Install uv, then run this explicit setup again.')
        command=[uv,'pip','install','--python',sys.executable,'--no-deps','-e',str(project)]
    subprocess.run(command,check=True,timeout=INSTALL_TIMEOUT)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError,subprocess.SubprocessError) as error:
        print('External manager setup failed. Check the reviewed checkout, initialized submodule and remote availability of the exact dependency pins: '+str(error),file=sys.stderr)
        raise SystemExit(1)
