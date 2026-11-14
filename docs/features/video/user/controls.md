# Playback tools

- **Playback → Go to time** accepts seconds, `MM:SS` or `HH:MM:SS`, including fractions. Press **G** to open it. A seek of at least ten seconds offers **Undo seek** for eight seconds (**Ctrl+Z**). Seek and Undo preserve Play/Pause. **Start over** clears the held position.
- **Playback → Lock controls** guards against accidental input. Use **Unlock** or Escape to restore it.
- **Speed** runs from 0.5× to 2×. **Picture** offers Fit, Fill (cropped), and Original size. The green cache strip maps remote bytes to time approximately.
- **Current folder** lists videos in natural filename order. **P/N** selects previous/next. **Play next automatically** advances within the folder at natural completion and requires source access.
- **Audio** and **Subtitles** choose embedded tracks or UTF-8 SRT, VTT, ASS or SSA files from the provider picker. Set language codes, subtitle size, delay or audio offset. Positive delay means later. Private subtitles must share the video's storage. Qt compatibility is limited to external SRT/VTT captions.

Notes Library videos opened as files use the full player. Inline Markdown clips start paused at zero.

## Remembered playback choices

Per-video position, speed, picture and track choices restore on reopen. Finishing returns to the start. Local renames can preserve state. Changed sources invalidate old positions. LocalCrypt and session-only checkpoints follow the [private reader policy](../../../user/reader-history.md). See [mobile playback tools](../user_mobile/controls.md).
