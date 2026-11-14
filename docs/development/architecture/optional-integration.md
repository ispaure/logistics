# Optional external feature integration

This page documents only the Logistics side of an optional local integration.
The public clone and release do not contain the external project's implementation
or user manual, and normal Logistics startup must work without it.

The root launchers detect a sibling `ally-tools/Python/ally_feature` package.
When present, they delegate dependency/environment selection through that project's
`logistics_launch.ini` while continuing to use Logistics' shared launcher entry.
The external bootstrap calls `services.ally_integration.activate`, which manages
an ignored `Python/features/emulation` symlink on Unix or junction on Windows.
It refuses to overwrite an ordinary directory/file. Discovery includes that
package only when activation has occurred; a leftover link alone is insufficient.

From Logistics, the activated feature participates in the normal feature registry,
Settings and navigation contribution contracts. A missing destination should be
investigated through launcher selection, activation and feature availability before
changing the generic host. `Python/tests/application/test_ally_integration.py` covers the host
boundary. Do not remove environment locks or replace an ordinary feature directory
to force activation.

Keep external feature capabilities, emulator setup, dependencies and troubleshooting
in the owning repository, including documentation reached through the ignored link.
Do not link Logistics guides into that local checkout. Its agents must resolve the
link, read the owning repository's instructions and commit there separately.
The root README retains only its prescribed one-sentence acknowledgement.
