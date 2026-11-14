# Optional external feature integration

Platform launchers can activate a sibling Ally Tools package through
`services.ally_integration.activate`. Activation owns the ignored
`Python/features/emulation` symlink/junction and refuses to overwrite ordinary
files or directories. A leftover link alone never enables discovery.
Normal startup supports a missing sibling.

Check launcher selection, activation and feature availability for a missing
destination. Run `python3 dev.py test desktop test_ally_integration.py` for the
Logistics boundary. Keep external guides with their owning repository.
