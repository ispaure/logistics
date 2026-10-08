# Archives

This feature contributes **Archives → Create encrypted ZIP…** to all Logistics
file browsers, including the Debug tab browser and comic library. The Features
tab enables/disables its action using the existing unified `Feature` API. Comics
password support belongs to Comics and does not depend on this action being enabled.

## Using this feature

Open **Debug → Open File Browser…**, select files/folders, then right-click
and choose **Archives → Create encrypted ZIP…**. The same action is available
in feature-hosted browsers while Archives is enabled.

See [shared setup and resource paths](../../../CONFIGURATION.md) and the
[Logistics feature index](../../../README.md#features) for application-wide setup.

## Password configuration

Place this in `remoteConfig.ini` beside a file or inside a selected folder:

```ini
[LogisticsZIP]
archive_password = change-me
```

`services.zip_passwords.configured_password` walks ancestors. The nearest INI
containing `[LogisticsZIP]` wins. Other sections do not stop the search; an empty
or missing `archive_password` in that section stops inheritance. Interpolation is
disabled, so percent signs work. `[DEFAULT]` passwords are ignored; the password
must be an explicit key in `[LogisticsZIP]`. INI syntax trims surrounding whitespace; use a
password without leading/trailing whitespace. The INI stores plaintext: keep real
passwords out of Git and limit access to the configuration.

## Creation and verification

Creation uses the configured password, or asks for a nonempty password and matching
confirmation when any selected item has no configured password. The entered password
is not saved to the INI. A ZIP has one password: conflicting configured passwords,
or an entered fallback different from a selected item's configured password, require
separate ZIPs. Sources are never deleted and existing outputs are never overwritten.
A single file `Comic.cbz` suggests `Comic.zip` beside the source, containing the
original `Comic.cbz`; a folder `Books` suggests `Books.zip` beside that folder.
Multiple selections suggest `Selection.zip`.
Selected folders keep their own root directories. Unsafe paths, symbolic links,
colliding names and outputs inside sources are rejected. Files are AES-256 encrypted,
verified by decrypted hashes before publication. Filenames are visible without a
password. Creating ZIPs is distinct from comic image recompression and does not
change input bytes.

Reusable ZIP operations live in [commonUtils](../../commonUtils/ZIP_ARCHIVES.md).

The destination must be outside selected folders even when reached through a
symbolic-link alias. Existing destinations created by another operation during
verification are retained, and source changes abort publication. Ordinary empty
directories have no secret payload and may have unencrypted directory headers;
their names are visible like all ZIP member names.

## Progress and cancellation

ZIP creation uses the shared background progress widget. The dialog reports
assessment, source hashing, streaming creation and verification. **Cancel ZIP
creation**, Escape or closing the dialog requests cancellation between chunks,
including while verifying. Temporary archives are discarded; sources and existing
destinations are retained. Cancellation is checked once more before publication.
The dialog stays alive until its worker has stopped; failures and cancellation
leave it open with an explanation. Completion after publication remains success.
