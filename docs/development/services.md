# Logistics host services

These modules own application policy and orchestration. Reusable filesystem,
configuration, persistence and UI machinery lives in the separate commonUtils
repository; its API documentation stays there.

| Domain | Modules to inspect |
| --- | --- |
| Folder sources, identities and safety | `folder_sources.py`, `folder_entries.py`, `folder_policy.py`, `folder_safety.py`, `identifiers.py` |
| Directory index host lifetime | `indexing.py` |
| Document opening, private views and metadata | `editor_resources.py`, `reader_resources.py`, `private_views.py`, `document_metadata.py`, `zip_passwords.py`, `password_prompt.py` |
| Local storage/preferences policy | `local_storage.py`, `preferences.py` |
| Software provisioning, updates and build identity | `software.py`, `updates.py`, `build_version.py` |
| Optional external host activation | `ally_integration.py` |

Start with the [developer index](development.md) and the relevant
feature README before changing a service. Feature-specific commands and state
belong to the feature. A host service may compose feature adapters to open a
document or resolve a provider; portable format modules should not import the
desktop shell to obtain that policy.

The existing module paths stay stable during feature/controller cleanup. Add a
domain package when several modules need a shared lifecycle or contract, rather
than moving every service merely to rename its container. Tests remain in
`Python/tests/`, located by domain (`test_folder_sources_ui.py`,
`test_editor_resource_picker.py`, `test_document_workspace.py`,
`test_local_crypt.py`, `test_software.py`, `test_updates.py`).
