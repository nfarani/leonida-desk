---
description: Turn an already-selected story into a short people watch to the end. Writes the production package; generates and posts nothing.
allowed-tools: Bash, Read, Write, Edit, WebFetch
argument-hint: <video desk rank | story:ID>
---

Make the short for: $ARGUMENTS

The story has ALREADY been selected. Do not look for other stories, re-rank, or question the choice. The article provides the information; your job is to make it impossible to scroll past, without bending a single fact. Follow CLAUDE.md sections 2, 4 and 14. Use `.venv/bin/python` if `python` is not on PATH.

The viewer should think "wait... WHAT?", then "no way", then "show me another one".

**0. Start.** `python scripts/make_video.py init $ARGUMENTS`. It prints the evidence packet and its verified claims. If a source you need is NOT OPENED, open it now and add claims with `scripts/article.py claim` and `opened` (see `commands/article.md` steps 2-3). Read every claim before going on.

**1. Find the entertainment (`entertainment_angle`).** Do not follow the article's structure or reuse its headline. Fill all six: `surprising_fact`, `entertaining_consequence`, `visual_opportunity`, `relatable_scenario` (the moment every player has lived), `wait_what_moment`, `why_viewers_care` (an ordinary viewer, not a lore expert). Article angle: "GTA VI may have advanced weather." Video angle: "Imagine getting five stars while the streets are flooding."

**2. Find the money shot first (`money_shot`).** What single visual stops the scroll? It is shot 1, marked `"money_shot": true`. Never save the best picture for the middle. Show it, then make the viewer want to know why it is happening.

**3. The first two seconds are sacred.** Open on a consequence, a question, a shocking visual, a mystery, a reaction or a challenge, in a very short first sentence. Never "Today we...", "New GTA 6 information...", "According to...", a logo, an establishing shot or background. Write three genuinely different `hooks`, pick `recommended_hook`, and set `hook_style` (shock, question, mystery, discovery, challenge, humor, consequence, story). Rotate the style from the previous video.

**4. Write it in the narrator's voice** (`config/publishing.yaml -> video.narrator`). He is our own original host: sounds like he lives in the game's world and is telling a friend something wild. He reacts; he does not report. One sentence, one idea, plain spoken words. "And when it rains? Your car starts losing grip." Translate terminology into consequences so someone who has never played understands at once. Never imitate an existing character or actor.

**5. Build on curiosity:** hook → curiosity → small payoff → new question → bigger payoff → escalation → final payoff → next curiosity. Do not explain everything at once. Each beat should be more interesting than the last; do not deliver the best moment at second 3 and explain it for 30. Micro-hooks ("Watch the car.", "Except there's a problem.") are welcome when natural and never repeated from recent videos.

**6. Facts stay facts.** Each voiceover line has a `kind`:
   - `fact`: carries `claims` ids from the packet. Quotes are verbatim.
   - `speculation`: our what-if. It MUST sound conditional ("could", "might", "imagine", "if"). The reaction can be dramatic; the claim cannot mislead. Series vocabulary (wanted stars and the like) belongs only in lines that are plainly hypothetical, never stated as a feature of an unreleased game.
   - `framing`: reaction, question, sign-off.
   The video inherits the story's label; below HIGH_CONFIDENCE_REPORT every hook and the title are hedged; "confirmed" or "official" only when the label is CONFIRMED.

**7. Every sentence has a visual (the beat map).** For each line decide what is said, what the viewer sees, what happens on screen and why they keep watching. Every line belongs to a shot (`vo_lines`); every generated shot has a `purpose`. Shots change when the story does, not on a timer: no dead attention. If four seconds of something unfolding is gripping, hold it; if nothing is happening, change it. A graphic or still held past a few seconds is dead footage.

**8. Higgsfield prompts make something HAPPEN.** Not "cinematic tropical city in rain" but "sports car speeding through a rain-soaked tropical city enters deep standing water at speed, rear tyres lose traction, it fishtails toward camera as police lights appear through the rain behind it". Each prompt carries subject, action, environment, camera behaviour, movement, emotion, story purpose and continuity with the shots around it, plus duration and 9:16. One achievable action per 3-6 second shot. Original scenes only: never name a game, studio or platform, never ask for gameplay. Set `continuity.reference_prompt` and `"reference": true` on shots that must match; avoid camera angles that invite a real maker's badge (rear views of cars).

**9. Captions are entertainment.** Give lines a punch `caption`: "FIVE STARS?!", "THE ROAD / FLOODS", "LOOK AT THE *CAR*", "YOU'RE COOKED" (five words at most; `/` breaks the line, `*word*` takes the accent; `""` shows nothing). They sell the idea; they do not transcribe. The full transcript is written to `captions.srt` automatically. Tags, sources and the end card follow `config/design.yaml`: each shot's `graphics` (for a sourced fact use `"tag": "ON RECORD"` with `"tag_text"` naming the source, for example GAME INFORMER; no "AI" label is drawn on screen), `end_card.lines`; `hook_title` only if the opening needs a title as well as its caption.

**10. Sound.** `music_prompt`, `audio_beds` (ambience: `prompt`, `from_shot`, `to_shot`, `db`), and per-shot `sfx` events (`prompt`, `at` seconds into the shot, `seconds`, `db`) for the things the viewer sees: engine, siren, rain, thunder, tyres, an impact, a riser, a bass hit. Use silence on purpose. Nothing is louder than the voice.

**11. End on the next curiosity (`ending_hook`).** The last thing said opens another question the channel can answer ("But apparently the police get even smarter."), only if the evidence supports there being one. Never "follow for part two".

**12. Retention edit (`retention_edit`).** Reread the whole draft. Every sentence: does the viewer need this? Every shot: does it make them stay? Every second: would it be better gone? Cut repetition, context, slow transitions, generic visuals, obvious explanations, pauses, article language, filler. Do not protect the runtime: a great 27 seconds beats an adequate 42. Record what you removed in `cut`, with `seconds_before` and `seconds_after`.

**13. The scroll test (`viewer_test`).** Imagine meeting this while flicking through Shorts. Answer every question in `video.retention.viewer_test` with `{"pass": true|false, "note": "..."}`, honestly. Any "no" means rework and re-answer; do not accept the first adequate draft. The checker refuses a package with an unanswered question or a "no".

**14. Fill the rest and check.** `treatment`, `editorial_angle`, `visual_premise` / `visual_escalation` / `visual_payoff` / `visual_style`, `editing_notes`, `sound_music`, `cta`, `youtube_title`, `youtube_description` (with the AI disclosure line), `tiktok_caption`, `instagram_caption`, `sources` (packet only). Then `python scripts/make_video.py check <video_id>`: fix every ERROR; read every WARNING and fix it or tell the editor why it stands.

**15. Present to the editor:** the entertainment angle and money shot, the three hooks and the pick, the voiceover with its captions side by side, the beat map (line → what we see → why they stay), the prompts, sound plan, ending hook, what the retention edit cut, the scroll-test answers, titles and captions, sources, and the production plan from `python scripts/make_video.py produce <video_id>`.

Nothing is generated or posted by this command. Next: `/render <video_id>`.
