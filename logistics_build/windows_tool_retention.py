"""Expire abandoned disposable Logistics tool installations in a selected Windows VM."""

from contextlib import contextmanager
import hashlib
import json
import re
import subprocess
import time
from uuid import uuid4

from build_manager.locking import workspace_lock
from build_manager.profiles import save_json
from build_manager.registry import config_directory
from build_manager.retention import linked
from build_manager.windows_guest import REMOVE
from logistics_build.build_retention import WINDOWS_TOOL_MAX_AGE


TOOL_PATHS = ('environment', 'cache', 'python', 'tools', 'downloads')

# Use the transport's token checks, extended paths and stage leases for removal.
# Preserve the namespace and anything a failed run might still need to collect.
PRUNE = r'''
$tokens=@($p.tokens)
$paths=@($p.paths)
$parent=Join-Path ([Environment]::GetFolderPath('CommonDocuments')) 'bm'
$removed=@()
$errors=@()
function HasPin([string]$root) {
 $pending=New-Object 'System.Collections.Generic.Stack[string]'
 $pending.Push(('\\?\'+$root))
 while ($pending.Count) {
  foreach ($item in [IO.Directory]::EnumerateFileSystemEntries($pending.Pop())) {
   if ([IO.Path]::GetFileName($item) -ieq '.keep') { return $true }
   $attributes=[IO.File]::GetAttributes($item)
   if (($attributes -band [IO.FileAttributes]::Directory) -and
       !($attributes -band [IO.FileAttributes]::ReparsePoint)) { $pending.Push($item) }
  }
 }
 return $false
}
try { $folder=Get-Item -LiteralPath $parent -Force } catch [System.Management.Automation.ItemNotFoundException] {
 @{removed=$tokens;errors=@()}|ConvertTo-Json -Compress
 return
}
for ($ancestor=$folder; $null -ne $ancestor; $ancestor=$ancestor.Parent) {
 if (!($ancestor.Attributes -band [IO.FileAttributes]::Directory) -or
     ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
  throw 'Unsafe Windows workspace namespace'
 }
}
foreach ($token in $tokens) {
 try {
  if ($token -cnotmatch '^[a-f0-9]{32}$') { throw 'Invalid disposable workspace token' }
  $workspace=Join-Path $parent $token
  try { $directory=Get-Item -LiteralPath $workspace -Force } catch [System.Management.Automation.ItemNotFoundException] {
   $removed+=$token
   continue
  }
  if (!$directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint)) { continue }
  if (Test-Path -LiteralPath (Join-Path $workspace 'active.json')) { continue }
  $marker=Get-Item -LiteralPath (Join-Path $workspace '.manager-owned.json') -Force
  if ($marker.PSIsContainer -or ($marker.Attributes -band [IO.FileAttributes]::ReparsePoint)) { continue }
  if (HasPin $workspace) { continue }
  $p=@{workspace=$workspace;token=$token;paths=$paths}
  & {
''' + REMOVE + r'''
  }
  $removed+=$token
 } catch {
  $errors+=($token+': '+$_.Exception.Message)
 }
}
@{removed=$removed;errors=$errors}|ConvertTo-Json -Depth 3 -Compress
'''


class WindowsToolRetention:
    """Keep preparation intents after the host attempt itself becomes eligible for pruning."""

    def __init__(self, client, vm):
        self.client = client
        self.vm = vm
        self.vm_key = vm.strip('{}').lower()
        key = hashlib.sha256(self.vm_key.encode()).hexdigest()
        self.root = config_directory() / 'guest-workspace-retention' / 'Logistics' / key

    @contextmanager
    def lease(self):
        if any(linked(path) for path in (self.root, *self.root.parents)):
            raise ValueError('Windows tool retention refuses linked receipt paths.')
        with workspace_lock(self.root / '.lock'):
            yield self

    @contextmanager
    def preparation(self, evidence):
        # Manager writes the guest token here before provisioning the guest.
        receipt = self.root / (uuid4().hex + '.json')
        try:
            yield receipt
        finally:
            if receipt.is_file():
                save_json(evidence, json.loads(receipt.read_text(encoding='utf-8')))
            else:
                self.discard(receipt)

    def prune(self, *, preserve=None):
        cutoff = time.time() - WINDOWS_TOOL_MAX_AGE
        candidates = {}
        try:
            for path in self.root.glob('*.json'):
                try:
                    if linked(path) or not path.is_file() or path.stat().st_mtime > cutoff:
                        continue
                    record = json.loads(path.read_text(encoding='utf-8'))
                    token = record.get('token')
                    if (record.get('vm', '').strip('{}').lower() == self.vm_key
                            and record.get('status') in ('preparing', 'prepared', 'failed')
                            and record.get('tests_run') is False
                            and isinstance(token, str) and re.fullmatch(r'[a-f0-9]{32}', token)
                            and token != preserve):
                        candidates[token] = path
                except (OSError, ValueError, AttributeError) as error:
                    print(f'Windows tool retention could not read {path.name}: {error}', flush=True)
            if not candidates:
                return
            result = json.loads(self.client.powershell(self.vm, PRUNE,
                                dict(tokens=sorted(candidates), paths=TOOL_PATHS), timeout=180))
            removed, errors = result['removed'], result['errors']
            if (not isinstance(removed, list) or not isinstance(errors, list)
                    or any(not isinstance(token, str) or token not in candidates for token in removed)):
                raise ValueError('Invalid disposable Windows cleanup response.')
            for token in set(removed):
                self.discard(candidates[token])
            if removed:
                print(f'Windows tool retention retired {len(set(removed))} expired preparation records.', flush=True)
            for error in errors:
                print(f'Windows tool retention will retry: {error}', flush=True)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as error:
            print(f'Windows tool retention incomplete: {error}', flush=True)

    @staticmethod
    def discard(receipt):
        # A cleanup receipt survives any interruption before guest deletion succeeds.
        receipt.with_name(receipt.name + '.prepare.lock').unlink(missing_ok=True)
        receipt.unlink(missing_ok=True)
