# Playback tools

Open **Playback…** for exact time entry, **Start over**, playback speed and picture
size. Speeds range from 0.5× to 2× with pitch compensation when the decoder supports
it. **Fit** preserves the complete image, **Fill** crops the edges to fill the
available area, and **Original size** uses the video's native size and can clip
large pictures. Fit is the default. These preferences survive reopening.

**Go to time** accepts seconds, `MM:SS` or `HH:MM:SS`, including fractional seconds.
A seek of ten seconds or more exposes **Undo seek** for eight seconds. Seeking
and undo preserve the current Play/Pause choice. **G** opens time entry;
**Ctrl+Z** undoes a recent seek.

**Current folder** lists videos in natural filename order: episode 2 comes before
episode 10. Choose a video or use **Previous** / **Next** (**P** / **N**).
**Play next automatically** is off by default. It advances at natural completion,
within the current folder and source; it cannot bypass credential authorization.
Folder listings run on a worker and may take time on cloud storage.

**Subtitles and languages** accepts preferred language codes such as `fr` and
`en`; blank uses the decoder default. Load any UTF-8 SRT accessible through the
existing provider picker. External SRT size and delay are adjustable; a positive
delay displays cues later. Embedded subtitle styling/delay and audio sync offsets
are available on mobile; Qt's desktop player does not expose those adjustments.

The green timeline strip shows locally available ranges. For remote videos its
byte-to-time mapping is **approximate**, especially with variable bitrate files;
it is not a guarantee of a particular number of playable seconds. Hover over the
slider for the explanation. The existing memory budget remains in effect.

Session-only cloud and LocalCrypt progress uses the credential ZIP password,
through the shared [reader-state policy](../../../user/reader-history.md). Changing
the ZIP password preserves old checkpoints for explicit previous-password migration.
Opening resumes automatically; use **Start over** to restart. Replacing the source
invalidates its old checkpoint. There is no decrypted movie cache on disk.

See [mobile playback tools](../user_mobile/controls.md) for touch and fold controls.
