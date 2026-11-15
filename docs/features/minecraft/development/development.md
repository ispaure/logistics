# Minecraft feature

Minecraft integration discovers local server folders and offers launch actions
for their configured Java or platform-specific Bedrock executable. Discovery
and launch eligibility must remain separate from starting a server.

## Follow launch eligibility

`Python/features/minecraft/server.py:MinecraftServer.__get_disk_app` checks
the platform binary and permissions. On Linux, a readable but nonexecutable
`bedrock_server` must not enable launch. The platform fixtures use disposable
server markers and executables without starting a real server:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_minecraft_platforms.py
```

`detection.get_servers()` scans local Workspaces one to three levels deep for regular `server.properties`. Private LocalCrypt copies skip local discovery. Legacy `get_minecraft_server_lst()` looks at immediate children, skips `*Backups` and accepts missing markers. `get_contributions()` remains a compatibility entry point.

Either Bedrock filename classifies a server. Windows and Linux have adapters for their own binary. Java uses the configured `[LaunchScript]` with the server folder as its working directory. See [launch and wiki settings](../user/user.md#configure-launching) and [mobile availability](../user_mobile/user_mobile.md).
