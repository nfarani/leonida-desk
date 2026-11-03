---
description: Produce the finished video for a package: narration, Higgsfield clips, graphics, captions, sound and final.mp4. Never spends credits without confirmation.
allowed-tools: Bash, Read
argument-hint: <video id> [confirm]
---

Produce the finished 9:16 video for $ARGUMENTS. Use `.venv/bin/python` if `python` is not on PATH.

1. **Show the plan first:** `python scripts/make_video.py produce <video_id>`. It lists every generation, the model for each and the estimated credits (asked from the Higgsfield CLI itself), and generates nothing. Report the estimate and the account balance (`higgsfield account status`).

2. **Paid generation needs the editor's explicit yes in this conversation.** Only then run `python scripts/make_video.py produce <video_id> --confirm` (in the background; it takes several minutes). It:
   - generates the narration, one clip per voiceover line (Higgsfield text-to-speech, voice in `config/publishing.yaml -> video.production.voice`);
   - times every shot from the narration, and writes `timeline.json`;
   - generates the continuity reference image, the stills and the clips through the `higgsfield` CLI, saving each job id before waiting on it;
   - draws the text cards, the ON RECORD / NOT SAID / WHAT IF tags, the captions and the AI disclosure locally, from each shot's `on_screen_text`;
   - assembles everything with FFmpeg: scenes, overlays, burned-in captions, voice, each clip's own sound, ambience beds and music, normalised for loudness;
   - writes `final.mp4` and `captions.srt` into the package and sets the status to READY_FOR_REVIEW.

3. **If it stops**, read the message. Finished steps are kept: running the same command again continues and never pays twice for a finished job. A shot rejected by moderation needs a new prompt first.

4. **Look before you hand over.** Extract a frame from each shot and check it against the storyboard: the right subject, continuity with the reference, no readable text or brand marks, nothing that looks like a game interface. To redo one shot, delete its file in `assets/` and its entry in `package.json -> render.jobs`, adjust the prompt or `video.production.video_model`, and run produce again. Tell the editor what you checked and anything that still looks weak.

   Then run the scroll test again on the finished video, from frames and the timeline: does frame one stop the scroll, is the caption on screen with the first word, does something change whenever attention would drop, is any held frame dead, does the last frame leave a question? You cannot hear the result: say so, and tell the editor exactly what to listen for (the voice's energy, effects against narration, the mix). If the cut would be better shorter, shorten it and export again before handing over.

5. After the editor has watched `final.mp4`: `python scripts/make_video.py approve <video_id>` (or `reject`). Posting is done by the editor; `/published` records it.

The graphic layer follows the Leonida Desk visual system in `config/design.yaml`; do not restyle a single video. To re-export after a graphics or caption change without regenerating anything, run produce again with `--output final_v<n>.mp4` (earlier exports are kept).

Package fields that steer production: `hook_title`, `end_card.lines` (wrap a word in *asterisks* for the accent), each shot's `graphics` (`tag`, `source.quote`, `source.by`) and `footage` (what runs under a shot that has no clip of its own), each voiceover line's `emphasis`; `continuity.reference_prompt` and `"reference": true` on the shots that must match it; `reuse_shot` on a card that holds an earlier frame; `music_prompt`; `audio_beds` (`prompt`, `from_shot`, `to_shot`, `db`); per-shot `sfx` events (`prompt`, `at`, `seconds`, `db`); a voiceover line's punch `caption`.

The narrator's voice is `config/publishing.yaml -> video.production.voice`. To audition candidates for the editor: `python scripts/make_video.py voices "<a line in the narrator's style>" --names <voice> <voice> ... --confirm` (a fraction of a credit each; files land in `outputs/voices/`). Choosing the voice is the editor's decision: it has to be heard.

Fallbacks, if the CLI is not installed or logged in: `python scripts/make_video.py render <video_id>` writes a manual generation sheet (or uses the HTTP API adapter when configured), and `ingest` picks up clips saved by hand. Never invent a model name, endpoint or price.
