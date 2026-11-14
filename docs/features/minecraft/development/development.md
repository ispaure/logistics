# Minecraft feature

## Try a Linux launch check

In a disposable desktop Workspaces folder, create a subfolder with empty `server.properties` and `bedrock_server` files. On Linux, changing the binary from mode 0644 to 0755 enables **Launch Server** after refreshing. Leave it unpressed. Temporarily change `os.X_OK` to `os.R_OK` in `Python/features/minecraft/server.py:MinecraftServer.__get_disk_app`. Run from the repo root on POSIX.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_minecraft_platforms.py
```

Expect the Linux permission fixture to fail with the temporary change and both tests to pass after restoring `os.X_OK`.

`detection.get_servers()` scans local Workspaces one to three levels deep for regular `server.properties`. Private LocalCrypt copies skip local discovery. Legacy `get_minecraft_server_lst()` looks at immediate children, skips `*Backups` and accepts missing markers. `get_contributions()` remains a compatibility entry point.

Either Bedrock filename classifies a server. Windows and Linux have adapters for their own binary. Java uses the configured `[LaunchScript]` with the server folder as its working directory. See [launch and wiki settings](../user/user.md#configure-launching) and [mobile availability](../user_mobile/user_mobile.md).
