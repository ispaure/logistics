# Audio playback and capture privacy

Mobile video and read-aloud share one output owner. Ordinary playback bypasses
Bluetooth approvals. In a protected process, approve the selected output under
**Settings → Privacy & Security → Protected audio outputs**, then explicitly Play.
Unknown identities fail closed. Approval is device-local and binds a hashed
port identity/profile. Route changes, interruption and loss follow the
[privacy policy](access-privacy.md).

`services/audio_output.py` owns consent state. `mobile/audio_output.py` owns
route generation, Play and monitor lifetime. Native probes use
`audio_output_native.py` and Android `AudioOutputs.java`. Video checks during
playback, speech before each utterance. iOS uses scene capture reports and
shields above modals. Android uses secure-window protection and queries anticipated
media outputs where available. Ambiguous external routes fail protected consent.

OS rerouting may precede notification and receivers can retain buffered audio.
iOS general still screenshots and external cameras remain outside app shielding.
Desktop capture protection is best effort. Mobile owns Bluetooth consent.

Run `python3 dev.py test mobile test_audio_output.py` for route, consent and
lifetime behavior. Actual Bluetooth and iPhone Mirroring require physical checks.
[Hardware acceptance](../../features/video/development/hardware-acceptance.md)

Protected output approval can be presented over native fullscreen video.
If iOS dismisses the controller and its prompt, Play or Settings can ask again.
The output name is a label. When Android cannot query the selected route,
admit an unambiguous enumerated output or internal-only speaker/receiver
combination. Unknown Bluetooth identities are refused under protection.
The route monitor also rechecks selection for changes without a connection event.

`audio_hardware_probe.py` opens native read-aloud Settings and logs transitions.
`video_hardware_probe.py` covers ordinary and protected audio plus a missing
Wi-Fi waiver. Rebuild both native adapters and Python for those probes.
`mobile_build.validation.video_native` exercises native compilation.

## Disposable read-aloud playback acceptance

With the [pinned mobile wheels](../build-release/mobile-device-deployment.md)
available, run from root:

```sh
mobile_build/.venv/bin/python -m mobile_build.validation.document_storage_tools ios \
  --probe speech-playback --output test-results/speech-playback
```

Expect voice fallback and native start, word-progress and completion on the
owned simulator. Use a physical probe for acoustic playback.
