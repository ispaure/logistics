#!/bin/bash
# Double-click in Finder, or run from Terminal. Requires git and python3.
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if python3 - "$SCRIPT_DIR" <<'PY'
import datetime
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import zipfile


def git(repo, *args, data=None):
    return subprocess.run(
        ["git", "-C", str(repo), *args], input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout


def ignored(repo, names):
    if not names:
        return set()
    result = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "--no-index", "-z", "--stdin"],
        input=b"\0".join(os.fsencode(name) for name in names) + b"\0",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError("Could not check Git ignore rules")
    return {os.fsdecode(name) for name in result.stdout.split(b"\0") if name}


def files(repo, prefix=Path()):
    names = sorted({os.fsdecode(name) for name in git(
        repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z",
    ).split(b"\0") if name})
    excluded = ignored(repo, names)
    for name in names:
        relative = prefix / name
        # Never follow links into private folders or include Git metadata.
        if name in excluded or ".git" in relative.parts:
            continue
        path = repo / name
        if any(parent.is_symlink() for parent in [path, *path.parents]):
            continue
        if path.is_dir():
            # git ls-files reports initialized submodules as directory entries.
            if (path / ".git").exists():
                yield from files(path, relative)
        elif path.is_file():
            yield relative


# Defense in depth for recognizable secrets accidentally left outside ignore rules.
# Only filenames are reported, never matched secret values.
SECRET = re.compile(
    rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
    rb"|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"
    rb"|\bgh[pousr]_[A-Za-z0-9]{36,}\b"
    rb"|\bgithub_pat_[A-Za-z0-9_]{60,}\b"
    rb"|\bxox[baprs]-[A-Za-z0-9-]{20,}\b"
    rb"|\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{40,}\b"
)


def main():
    destination = Path(sys.argv[1]).resolve()
    root = Path(os.fsdecode(git(destination, "rev-parse", "--show-toplevel")).strip())
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M")
    output = destination / f"{root.name}-snapshot-{timestamp}.zip"
    if output.exists():
        raise RuntimeError(f"Snapshot already exists: {output.name}. Retry next minute.")
    candidates = sorted(set(files(root)))
    # Apply the outer repository's rules to submodule contents as well.
    excluded = ignored(root, [str(path) for path in candidates])
    descriptor, temporary = tempfile.mkstemp(prefix=".snapshot-", suffix=".tmp", dir=destination)
    os.close(descriptor)
    count = 0
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for relative in candidates:
                path = root / relative
                if str(relative) in excluded or path == output or path == Path(temporary):
                    continue
                # Refuse symlink replacements between discovery and reading.
                with open(path, "rb", opener=lambda name, flags: os.open(name, flags | os.O_NOFOLLOW)) as source:
                    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                        continue
                    content = source.read()
                if SECRET.search(content):
                    raise RuntimeError(f"Possible secret in {relative}; exclude or sanitize it first.")
                info = zipfile.ZipInfo.from_file(path, arcname=str(relative))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content)
                count += 1
        # Create without overwriting an existing snapshot, including concurrent runs.
        os.link(temporary, output)
        print(f"Created {output}\n{count} files, {output.stat().st_size / 1048576:.1f} MB")
        print("Includes current edits and untracked files allowed by Git ignore rules.")
        print("Secret checks cover common formats; review the ZIP before uploading.")
    finally:
        Path(temporary).unlink(missing_ok=True)


try:
    main()
except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
    print(f"Snapshot failed: {error}", file=sys.stderr)
    sys.exit(1)
PY
then
    RESULT=0
else
    RESULT=$?
fi
if [ -t 0 ]; then
    read -r -p "Press Return to close... " _
fi
exit "$RESULT"
