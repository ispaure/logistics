"""Prepare a single-record SSH publication for firmware qualification.

This module performs no I/O. Callers must qualify the firmware and authorize
service interruption before executing a plan. The browser does not enable it.
"""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import PurePosixPath
import re
from shlex import quote
import tarfile
from uuid import uuid4

from .remarkable_mutations import MetadataChange
from .remarkable_ssh import MAX_SIDECAR, UUID

STORE_PATH = '/home/root/.local/share/remarkable/xochitl'
TRANSACTION_ROOT = '/home/root/.local/share/logistics-remarkable-transactions'
FILES = ('payload.tar', 'before', 'after', 'apply.sh', 'restart.sh', 'lease-token',
         'manifest.json', 'original', 'publish', 'outcome', 'outcome.tmp',
         'restart-needed', 'service-state', 'service-state.tmp')


@dataclass(frozen=True)
class MetadataTransaction:
    token: str
    directory: str
    unit: str
    archive: bytes
    launch_command: str
    inspect_command: str
    recovery_command: str
    cleanup_command: str


def _check_file(path, digest):
    path = quote(str(path))
    return f'''[ -f {path} ] && [ ! -L {path} ]
actual=$(sha256sum {path})
[ "${{actual%% *}}" = '{digest}' ]
'''


def prepare_metadata_transaction(change: MetadataChange) -> MetadataTransaction:
    """Build immutable scripts/payload; a detached unit owns publication/restart.

    Metadata alone is atomically replaced. Before/after hashes allow recovery to
    distinguish unchanged, committed and conflicting states without overwriting
    an unexpected edit. An owned lease survives client/unit interruption and is
    released only after services are restored. Recovery never guesses ownership.
    """
    if not isinstance(change, MetadataChange) or not UUID.fullmatch(change.identity):
        raise ValueError('Choose a native metadata change.')
    if (not change.changed or change.operation not in {'rename', 'move', 'trash', 'restore'}
            or any(not isinstance(data, bytes) or len(data) > MAX_SIDECAR for data in (change.before, change.after))):
        raise ValueError('Choose a bounded metadata change that requires publication.')
    guards = {}
    for guard in change.guards:
        if (not UUID.fullmatch(guard.identity) or not re.fullmatch('[0-9a-f]{64}', guard.sha256)
                or guard.identity in guards):
            raise ValueError('Invalid native revision guards.')
        guards[guard.identity] = guard.sha256
    before_hash, after_hash = sha256(change.before).hexdigest(), sha256(change.after).hexdigest()
    if guards.get(change.identity) != before_hash:
        raise ValueError('The publication requires the exact original metadata revision.')
    token = str(uuid4())
    root = PurePosixPath(TRANSACTION_ROOT)
    directory = root / token
    target = PurePosixPath(STORE_PATH) / (change.identity + '.metadata')
    unit = 'logistics-remarkable-' + token
    # Every shell value is generated here or validated as UUID/hex. Document
    # names and metadata stay in tar members and are never shell source.
    prefix = f'''#!/bin/sh
set -eu
umask 077
stage={quote(str(directory))}
root={quote(str(root))}
target={quote(str(target))}
token='{token}'
'''
    apply = prefix + f'''
[ ! -e "$root/active" ] && [ ! -L "$root/active" ]
ln "$stage/lease-token" "$root/active"
[ "$(cat "$root/active")" = "$token" ]
for service in xochitl rm-sync; do
    [ "$(systemctl is-active "$service" || :)" = active ]
done
[ "$(stat -c %d "$stage")" = "$(stat -c %d {quote(STORE_PATH)})" ]
printf '%s\\n' restart > "$stage/restart-needed"
systemctl stop xochitl
for service in xochitl rm-sync; do
    [ "$(systemctl is-active "$service" || :)" = inactive ]
done
'''
    for identity, digest in sorted(guards.items()):
        apply += _check_file(PurePosixPath(STORE_PATH) / (identity + '.metadata'), digest)
    apply += _check_file(directory / 'before', before_hash) + _check_file(directory / 'after', after_hash)
    apply += '''cp -p "$target" "$stage/original"
cp -p "$target" "$stage/publish"
cat "$stage/after" > "$stage/publish"
'''
    apply += _check_file(directory / 'original', before_hash) + _check_file(directory / 'publish', after_hash)
    apply += '''sync
mv -f "$stage/publish" "$target"
sync
'''
    restart = prefix + f'''
# ExecStopPost runs after normal exit, failure, timeout or unit termination.
# A failed lease acquisition must never restart another operation's services.
[ -f "$root/active" ] && [ ! -L "$root/active" ] || exit 0
[ "$(cat "$root/active")" = "$token" ] || exit 0
outcome=conflict
if [ -f "$target" ] && [ ! -L "$target" ]; then
    if actual=$(sha256sum "$target"); then
        case "${{actual%% *}}" in
            {before_hash}) outcome=unchanged ;;
            {after_hash}) outcome=committed ;;
        esac
    fi
fi
# Receipt I/O must not prevent the interface restart, including a full disk.
if [ -f "$stage/restart-needed" ]; then
    timeout 45 systemctl start xochitl
    for service in xochitl rm-sync; do
        [ "$(systemctl is-active "$service" || :)" = active ]
    done
fi
printf '%s\\n' "$outcome" > "$stage/outcome.tmp"
mv "$stage/outcome.tmp" "$stage/outcome"
printf '%s\\n' restored > "$stage/service-state.tmp"
mv "$stage/service-state.tmp" "$stage/service-state"
sync
rm "$root/active"
'''
    manifest = dict(version=1, token=token, identity=change.identity, operation=change.operation,
                    before_sha256=before_hash, after_sha256=after_hash, guards=guards)
    members = {'before': change.before, 'after': change.after, 'apply.sh': apply.encode(),
               'restart.sh': restart.encode(), 'lease-token': (token + '\n').encode(),
               'manifest.json': (json.dumps(manifest, sort_keys=True) + '\n').encode()}
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, data in members.items():
            item = tarfile.TarInfo(name)
            item.size, item.mode = len(data), 0o600
            archive.addfile(item, BytesIO(data))
    payload = buffer.getvalue()
    # Exclusive mkdir and a private root prevent a repeated attempt from
    # replacing an earlier receipt. A failed upload leaves an inspectable stage.
    launch = prefix + '''
if [ ! -e "$root" ]; then mkdir -m 700 "$root"; fi
[ -d "$root" ] && [ ! -L "$root" ]
[ "$(stat -c %u "$root")" = 0 ] && [ "$(stat -c %a "$root")" = 700 ]
mkdir -m 700 "$stage"
cat > "$stage/payload.tar"
'''
    launch += _check_file(directory / 'payload.tar', sha256(payload).hexdigest())
    launch += 'tar -xf "$stage/payload.tar" -C "$stage" ' + ' '.join(members) + '\n'
    launch += _check_file(directory / 'apply.sh', sha256(members['apply.sh']).hexdigest())
    launch += _check_file(directory / 'restart.sh', sha256(members['restart.sh']).hexdigest())
    launch += f'''systemd-run --quiet --unit={unit} --property=Type=exec \\
    --property=RuntimeMaxSec=90 --property=TimeoutStopSec=60 \\
    --property='ExecStopPost=/bin/sh {directory}/restart.sh' /bin/sh "$stage/apply.sh"
'''
    inspect = prefix + f'''systemctl show {unit} --property=ActiveState --property=SubState --property=Result || :
for name in outcome service-state; do
    if [ -f "$stage/$name" ] && [ ! -L "$stage/$name" ]; then
        printf '%s=' "$name"; head -c 32 "$stage/$name"
    fi
done
if [ ! -e "$root/active" ] && [ ! -L "$root/active" ]; then
    printf 'lease=clear\\n'
elif [ -f "$root/active" ] && [ ! -L "$root/active" ] && [ "$(cat "$root/active")" = "$token" ]; then
    printf 'lease=owned\\n'
else
    printf 'lease=foreign\\n'
fi
'''
    recovery = prefix + f'''state=$(systemctl is-active {unit} || :)
case "$state" in inactive|failed|unknown) ;; *) exit 1 ;; esac
'''
    recovery += _check_file(directory / 'restart.sh', sha256(members['restart.sh']).hexdigest())
    recovery += f'''systemd-run --quiet --unit={unit}-recovery --property=Type=exec \\
    --property=RuntimeMaxSec=60 /bin/sh "$stage/restart.sh"
'''
    cleanup = prefix + f'''state=$(systemctl is-active {unit} || :)
case "$state" in inactive|failed|unknown) ;; *) exit 1 ;; esac
state=$(systemctl is-active {unit}-recovery || :)
case "$state" in inactive|failed|unknown) ;; *) exit 1 ;; esac
[ ! -e "$root/active" ] && [ ! -L "$root/active" ]
[ -d "$stage" ] && [ ! -L "$stage" ]
'''
    cleanup += _check_file(directory / 'manifest.json', sha256(members['manifest.json']).hexdigest())
    cleanup += '''[ "$(cat "$stage/service-state")" = restored ]
case "$(cat "$stage/outcome")" in committed|unchanged) ;; *) exit 1 ;; esac
for file in "$stage"/* "$stage"/.[!.]* "$stage"/..?*; do
    [ -e "$file" ] || [ -L "$file" ] || continue
    [ -f "$file" ] && [ ! -L "$file" ]
    case "${file##*/}" in
'''
    cleanup += '        ' + '|'.join(FILES) + ') ;;\n        *) exit 1 ;;\n    esac\ndone\n'
    cleanup += 'rm -f ' + ' '.join('"$stage/' + name + '"' for name in FILES) + '\nrmdir "$stage"\n'
    return MetadataTransaction(token, str(directory), unit, payload, launch, inspect, recovery, cleanup)
