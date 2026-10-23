# Mobile build tooling owners

The Briefcase project, generated output paths, native bridge and installed app
identities remain unchanged. Organize tooling by the work a contributor needs
to do; application features stay in `Python/`.

| Work | Owner |
| --- | --- |
| Curate the public Python payload and verify its source identity | `mobile_build/tools.py` |
| Build and link the native bridge; compose generated-project adapters | `mobile_build/cloud_build.py` |
| Configure camera, scenes, privacy manifests and app artwork | `mobile_build/build_support/` |
| Regenerate canonical navigation and folder artwork | `mobile_build/build_support/generate_navigation_icons.py`, `generate_folder_icons.py` |
| User-facing deployment commands | Existing `mobile_build/*.command` launchers |
| Host regression contracts | `mobile_build/tests/` |
| On-device checks and synthetic fixtures | `mobile_build/native_tests/` |

`build_support` edits only generated projects or explicitly requested canonical
artwork. Its imports have no build or deployment side effects. `cloud_build.py`
shows adapter composition explicitly before compiling the bridge. It uses the
same generated workspaces and native resource sources as before.

For normal build commands and platform prerequisites, see the
[mobile handbook](mobile-handbook.md). For signing and distribution, see
[TestFlight](mobile-testflight.md) and [device deployment](mobile-device-deployment.md).
