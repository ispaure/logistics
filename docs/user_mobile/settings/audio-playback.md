# Audio playback

Open **Settings → Audio playback** to see and remove approved Bluetooth audio
outputs. The list applies to videos and every read-aloud reader **only while session-only protection is active**. This means at least one session-only credential is loaded, or retained protected content still prevents screencasting. Ordinary playback does not ask for Bluetooth approval or rely on this list. It is saved on
this device and is separate from Bluetooth pairing in system Settings.

While protection is active, select a Bluetooth output in system controls, then press Play or **Approve current
output…**. An unapproved output asks for approval. Approving it leaves playback
paused: press Play separately when you are ready. Declining or cancelling leaves
it unapproved and paused.

During session-only protection, changing the selected audio output pauses playback, even when the new device was already approved. Removing approval also pauses protected playback. Ordinary playback is unaffected by approval-list edits or consent-related output-switch rules. Calls, interruptions and actual headphone/Bluetooth output loss still pause ordinary playback, and reconnecting a device does not restart it automatically. Device labels include a short
identifier so two devices with the same name can be distinguished.

During session-only protection, if Logistics cannot identify the selected output, it keeps playback paused. Unavailable Bluetooth identity does not block ordinary playback. Try
selecting a readable output in system controls. Some older Android versions cannot
identify the selected output when several devices are connected. A changed device
identity or Bluetooth profile may need fresh approval.

When any session-only credentials are loaded, capture/mirroring restrictions apply
across the app, including ordinary document browsing. iOS hides content when the
OS reports active capture and pauses audio. Supported capture protection does not
prevent still screenshots or filming the device with another camera. Actual iPhone
Mirroring and physical Bluetooth checks remain pending; see the
[privacy and validation limits](../../development/audio-playback.md).
