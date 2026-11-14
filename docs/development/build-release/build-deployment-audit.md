# Build and deployment ownership

| Owner | Responsibility |
| --- | --- |
| Build Deployment Manager | Plan review/execution, locks, leases, artifact hashing, continuation, transport and provider APIs |
| Logistics `logistics_build/` | Adapter, source selection, suites, evidence, guest policy, retention and delivery checks |
| Logistics `mobile_build/` | Briefcase payload, native app/bridge, signing and provisioning, device and tester destination policy |
| commonUtils | Shared portable mechanisms and their API contracts |

Declare project inputs and gates through the manager API. Use its `native_commands`, `dependency_sources`, `guest_workload` and provider clients for reusable mechanics. Run cross-consumer acceptance with explicit repositories and interpreters.

## Current operator paths

Use [the manager](../../user/build-manager.md) for Run checks, Build only and Prepare and deliver. Build only creates an Android test APK or iOS simulator app. See [adapter contracts](build-manager.md) and [specific tooling owners](build-tooling.md).

## Storage lifecycle

`build_retention.py` owns [retention](build-manager.md#automatic-storage-retention). `storage_extras.py` owns explicit path/token adoption and simulator lease recovery. Verify exact ownership and preserve active writers. Collect reports before cleanup. Compiler intermediates can retire independently of held packages and receipts. Keep private SDKs, personal simulators and evidence intact. Portable ownership fixtures and native cleanup evidence verify separate contracts.
