# Cross-platform archive checks

`.github/workflows/archive-platform-checks.yml` runs on macOS, Ubuntu and Windows,
plus an official Fedora 43 container hosted on Ubuntu. It checks the same committed
commonUtils submodule that Logistics uses. Jobs continue independently on failure.
Each job runs all commonUtils tests, all Logistics tests and a full historical
compression comparison, then uploads JSON summaries and logs for 14 days.

From a normal recursive clone, use the project's Python 3.12.2 environment:

```sh
python Python/tests/run_platform_checks.py
```

Add `--install` to install the pinned project dependencies into that interpreter
first. Use a virtual environment. Python 3.12.2 is required by the current project;
Fedora's newer system Python is not the test interpreter. The script uses native
path separators and Qt's offscreen backend automatically. Its default report and
fixture directory is `test-results/`, which is ignored by Git. A second run should
use a new `--results-dir` or remove the previous disposable reports first.

The historical comparison requires the Git history for Logistics
`43e777cafe8c5bd45fece1538ba32ee75ca2db91` and commonUtils
`70117045020ee9a8f78c9e6ba3be47a9c7cd2ca6`. CI fetches the latter explicitly.
Shallow clones may need to fetch those commits before running locally.
The comparison can also run by itself:

```sh
python Python/tests/compare_comic_zip_versions.py
```

It exports pristine baseline code into disposable folders and compares 24 complete
compression runs: four input layouts, two retention/animation policies, and three
versions (old plain, current plain, current AES-256). Extraction, sanitization,
staged outputs and final decrypted entries must match by exact names, sizes and
SHA-256 hashes. Logs use a frozen clock. The old helper's explicit AES extraction
must match plain extraction; the old comic compressor's unsupported encrypted run
must fail without changing its input. No existing library files are touched.

Comparisons happen within each OS and installed encoder environment. Byte equality
between different OS encoder builds is not required. These headless checks cover
archive placement and Qt logic, not desktop interaction, actual FUSE/rclone mounts,
network credentials or external RAR extractors. The Fedora container tests Fedora
userspace with an Ubuntu host kernel; a local Fedora run is still useful for the
real desktop and mounted-storage environment.

The first Windows run exposed a pre-existing archive flush bug: Windows rejects
`fsync` on the legacy compressor's read-only descriptor. Current archive creation
and comic rewrites flush a writable staging handle before restoring permissions.
For historical Windows parity only, the comparison harness changes the legacy
staged ZIP's flush-open mode from `rb` to `r+b` in memory; entry placement, content,
encoders and retention policy remain untouched. Each trace records this adjustment.
A separate completely pristine Windows baseline run must reproduce the flush
failure, preserve its input and produce the same staged result. Other operating
systems use the pristine baseline without this adjustment. The JSON comparison
records both outcomes so this boundary is visible rather than a skipped test.

Fixtures use the native long form of the OS temporary directory, because Qt
expands Windows 8.3 aliases. Permission-preservation tests compare against the
mode actually supported by the host filesystem rather than requiring POSIX bits
on Windows.

Fixtures close SQLite connections explicitly and use legal native filenames and
paths. Tests that execute a POSIX shell or require POSIX executable permission
bits run only on POSIX hosts; archive and password checks run on every platform.
