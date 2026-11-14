# Mobile playback tools

On iOS, a newly opened video starts with controls visible and hides them after
three seconds of active playback. Tap the picture to fade controls back in or
out. Pausing, seeking, opening a menu, VoiceOver, and the Duo laptop deck keep
controls available. Playback options use a scrollable alert on iPhone, including
Duo, and an anchored sheet on iPad. System bars are removed after the fade so safe-area changes
do not move visible controls. Reduce Motion uses an immediate transition.

On Android, tap the video to enter fullscreen or reveal the controls. The
timeline, playback buttons and **Unlock controls** stay clear of the system
navigation and tablet taskbar area, including when a swipe reveals system bars.

Choose **Playback** in the iOS navigation controls or Duo's lower fold deck.
On Android choose **More playback options → Playback…**. Playback options include
exact time entry, Start over, speed, subtitles,
folder navigation, mute and control locking. iOS picture sizing uses the separate
Fit/Fill button; Android also offers picture sizing through its playback tools.
See the [shared control guide](../user/controls.md) for time
formats, queue ordering, automatic next-episode behavior and encrypted cloud
resume. Mobile remembers progress approximately every five seconds and on closing
or backgrounding when access remains available. Reopening resumes automatically;
**Start over** is always available in Playback.

The top overlay shows the full filename including its extension in white, with
an icon and label for a cloud, local or local encrypted file. The title, playback
buttons and timeline fade together when controls appear or disappear. Choose
**Show in folder** in the playback menu to close playback, open the source folder
and select the video in the file browser.

Double-tap the left/right side of the movie to skip ten seconds; double-tap its
center to toggle Play/Pause. Mobile never displays Undo seek.
**Lock controls** hides controls and prevents accidental touch or keyboard seeks.
A visible **Unlock controls** button restores them. Escape also unlocks.

External keyboards support Space (Play/Pause), Left/Right (ten-second skips),
M (mute), F (fullscreen), G (go to time), P/N (previous/next) and Escape
(unlock or leave fullscreen). On-screen controls remain accessible without a
keyboard. Control locking and credentials remain separate: unlocking controls
never unlocks a protected source.

**Subtitles and audio** offers a subtitle browser within the video's current
source, including other folders. It accepts SRT, VTT, ASS and SSA files up to
8 MiB; matching sidecars are still offered automatically. Files stay in provider
streams. Preferred audio/subtitle languages, subtitle size, subtitle delay and
audio sync offset are adjustable. Positive delay means later. Native engines
control styling and may not override formatting embedded in ASS subtitles.
Android applies font/language changes by reopening the decoder at the current
position; this can briefly rebuffer. Other settings apply without that reload.

The green cache strip is labeled **Cache ≈** for remote playback: ranges are
mapped approximately from bytes, not measured presentation timestamps. Local
sources are available without a network fetch. No cache amount guarantees
uninterrupted playback on a slow connection.

Manual Pause updates playback intent and the held position while the decoder
acknowledges its asynchronous pause command. Android uses a volatile TextureView
snapshot for an immediate visual hold. On iOS, the native sample-buffer video
layer remains visible and VLC holds its picture; a few queued frames may finish
before Pause is acknowledged. Other iOS renderer fallbacks retain the volatile
snapshot hold. Snapshots stay in memory and are removed on resume, closing or
privacy concealment. A snapshot unavailable during renderer startup cannot
provide that hold. PiP/casting use their system/receiver presentation and need
separate timing checks. See the [iOS HDR pause investigation](../development/hdr-play-pause.md)
for the presentation-path change and its remaining visual acceptance.

The new tools have SDK compilation and host checks. Physical Duo touch, keyboard,
fold and pause timing still need acceptance; those checks are separate from the
baseline installation requested before these additions.


Picture-in-picture uses ten-second backward/forward actions on Android and the
system skip controls on iOS. Seeking respects control locking and the source's
access policy. iOS clamps skips at the start and end and completes no-op requests.
Android keeps its subtitle surface attached when entering PiP. iOS uses classic
system PiP by default; its video surface does not include VLC subtitle overlays.
On iOS 17.4 or later, **Playback → Subtitle PiP (reopen video)** enables the
subtitle compositor for the next time the video opens. Turn it off and reopen
to return to classic PiP. Changing this preference leaves active playback intact.

## Watching on a TV with iPhone or iPad

Turn on **Settings → Video → Native AirPlay video**, then open a local MP4,
MOV, M4V or MKV. Tap the **AirPlay** picker in the Logistics player and choose
your TV. Use the same timeline, play/pause and skip controls while the TV plays.
To return to the Duo, choose **iPhone** in the same picker. Playback returns
to the current position when the audio route switches.

Compatible MKVs stream over Wi-Fi. Logistics copies H.264 or H.265 (HEVC)
video, including HDR metadata, and offers compatible AAC, AC-3, E-AC-3 and
mono, stereo or 5.1 Opus audio. Opus converts to AAC. TrueHD/Atmos files can
use an alternate AC-3 track if present. While on TV, use **Audio tracks** and
**Subtitles** in Logistics to choose the tracks the receiver can play.
The same choices are advertised to Apple TV's playback controls, so they can
also be selected with the Siri Remote where the receiver exposes those menus.
The Duo's track menus read the current Apple player selection when reopened.
Embedded SubRip and WebVTT and discovered local SRT and WebVTT sidecars are
available as TV text subtitles. Image-based PGS subtitles remain available
during local playback. Session-only protection blocks AirPlay.

Speed, mute and fit/fill controls target the Apple player during AirPlay.
Changing speed while paused keeps the video paused. Mute remains in effect
when returning to the phone. Subtitle appearance and HDR output use the TV's
settings; the phone's audio and subtitle delay settings apply to local playback.

The playlist covers the full movie, so a timeline jump requests the fragment
around the new position. A jump may pause briefly while Logistics reads from
the nearest keyframe. Receiver support and Siri Remote behavior depend on the
TV.
