# Choose rclone download versions

## Rclone download versions

**Settings → rclone** exposes `Python/features/rclone/config.ini`, with one section
per supported operating system and architecture. These values override rclone's
entries in `Python/software_manifest.json`; missing override fields use the manifest.
Other software continues to use the manifest directly.

To select another release, update its version, HTTPS URL, ZIP member, destination
path and both hashes together. `sha256_str` checks the downloaded ZIP;
`installed_sha256_str` checks the executable inside it. Hash verification remains
mandatory. Destination paths must stay inside the configured Software folder.
Saving changes edits configuration only; provisioning still happens through the
existing confirmed download flow when the tool is needed. Invalid metadata is
rejected before it is used.
