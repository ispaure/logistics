# Perforce Feature

## Try a console label change

On Linux desktop, enable **Perforce Server** and select a disposable local Workspaces folder with the [three Perforce keys](../user/user.md) in `remoteConfig.ini`. In `Python/features/perforce/ui_contributions.py:_get_actions`, change **Open P4 Console** to **Open Perforce Console**, keeping the port. Update the console fixture and run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_perforce.py
```

Expect the new label and explicit server arguments reaching the stub Bash client. POSIX cases skip on Windows.

`detection.py` resolves relative paths from the workspace and prefers executable local `p4` over PATH. Optional `server.id` labels the server. Buttons are disabled outside Linux and callbacks recheck the OS. Preserve argument quoting in `actions.py`. P4D uses `-C1 -r <data> -p <port>`. Interactive Bash sets `P4PORT` and forwards explicit `-p` on each call. Numeric ports map to localhost. Check terminal output or `p4 info` for readiness after launch. See [mobile availability](../user_mobile/user_mobile.md).
