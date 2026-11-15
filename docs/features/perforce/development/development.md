# Perforce Feature

Perforce integration discovers server settings in local workspaces. On
Linux, the folder actions use those settings to start P4D or open a
console with the corresponding P4 connection.

## Trace console arguments

**Open P4 Console** is declared by
`Python/features/perforce/ui_contributions.py:_get_actions` for an eligible
workspace. The fixtures route explicit server arguments to a stub Bash client
and check platform guards. POSIX cases skip on Windows:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_perforce.py
```

`detection.py` resolves relative paths from the workspace and prefers executable local `p4` over PATH. Optional `server.id` labels the server. Buttons are disabled outside Linux and callbacks recheck the OS. Preserve argument quoting in `actions.py`. P4D uses `-C1 -r <data> -p <port>`. Interactive Bash sets `P4PORT` and forwards explicit `-p` on each call. Numeric ports map to localhost. Check terminal output or `p4 info` for readiness after launch. See [mobile availability](../user_mobile/user_mobile.md).
