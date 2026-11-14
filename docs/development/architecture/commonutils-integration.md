# commonUtils integration and ownership

`Python/commonUtils/` is a separate submodule. Write reusable APIs and their
reference docs there. Keep Logistics navigation, format limits, provider policy,
confirmations, resource paths and saved schemas with their app owners.

| Change | Shared mechanism | Logistics responsibility |
| --- | --- | --- |
| Browser, index, archives and previews | Files and provider contracts, election, snapshot reads | Recognized roots, feature actions, credentials and retained hosts |
| Settings, formats and recovery | INI schema, atomic publication, editors | Keys, defaults, conflict behavior and migrations |
| Background work | Operations, native subscriptions and process progress | Validated inputs, cancellation boundaries, disposal and result handling |
| Mobile control or reader | Native picker, widgets, WebView loading, draw acknowledgements | Route, retained grant, privacy, palette and format adapter |
| Secure storage | Native key storage, verified provider mutations | Key identity, allowed persistence, retention and recovery |

Use canonical, qualified shared imports. Keep Qt/Toga out of portable modules
and place native adapters at their owning boundary. Logistics composes mobile
browsers and adapters, reusing shared layouts and resource contracts. Providers
retain independent access for each adopted reader. Keep format-specific operations
with the feature and native leases with the host that acquired them.
[Resource APIs](../../../Python/commonUtils/docs/development/reference/ui/resource-providers.md)

Inject operations at the narrowest existing port. A reusable directory relocation
or archive member replacement belongs in commonUtils. A copy migration's trigger,
checkpoint order and destination validation belong to Logistics. Use the same
division for native key storage and encrypted record ownership.
For new native UI components, put platform-neutral behavior and device adapters
with the shared owner. Project font, color and E Ink choices through Logistics'
presentation adapter. Preserve the provider's own revision and grant checks.

Use `logistics_build/` for project policy and the standalone manager for
supervision. Review dependency pins with changes to shared contracts and
check `test_release_verification.py` for release pin handling.
