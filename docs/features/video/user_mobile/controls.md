# Mobile playback tools

On iOS, a newly opened video starts with controls visible and hides them after
three seconds of active playback. Tap the picture to fade controls back in or
out. Pausing, seeking, opening a menu, VoiceOver, and the Duo laptop deck keep
controls available. Playback options use a scrollable alert on iPhone, including
Duo, and an anchored sheet on iPad. System bars are removed after the fade so safe-area changes
do not move visible controls. Reduce Motion uses an immediate transition.

Choose **Playback** in the iOS navigation controls or Duo's lower fold deck.
On Android choose **More playback options → Playback…**. The menu includes exact
time entry, Start over, speed, picture size, subtitles, folder navigation, mute
and control locking. See the [shared control guide](../user/controls.md) for time
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
center to toggle Play/Pause. A large seek shows **Undo seek** for eight seconds.
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

Manual Pause holds the visible frame and position immediately while the decoder
finishes its asynchronous pause command. Resume starts from the held position.
The temporary frame stays in memory and is removed on resume, closing or privacy
concealment. iOS uses a render-server snapshot; Android uses a TextureView snapshot.
A snapshot unavailable during renderer startup cannot provide that visual hold.
PiP/casting use their system/receiver presentation and need separate timing checks.

The new tools have SDK compilation and host checks. Physical Duo touch, keyboard,
fold and pause timing still need acceptance; those checks are separate from the
baseline installation requested before these additions.
