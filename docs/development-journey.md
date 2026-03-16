# Development Journey: Self-Improving Runner Game

A detailed account of building a self-improving runner game using Karpathy's
autoresearch framework with Gemini LLM reasoning. This documents the full
human-AI collaboration, the technical decisions, the dead ends, and the final
successful implementation.

---

## 1. The Starting Point

### The Brief

The user provided two reference codebases in `.ignore/`:

1. **prompt-optimizer**: An autonomous prompt engineering system that evolved a
   4-line event extraction prompt to 100% accuracy (180/180 fields) in 8
   experiments, using Karpathy's autoresearch pattern with Gemini 2.5 Flash.

2. **autoresearch-master**: Karpathy's original autonomous LLM training
   framework where agents modify `train.py`, train for 5 minutes on a GPU,
   and keep or discard based on validation loss.

The task: build a self-improving runner game where the runner scores at least
50 points (1 point per cleared obstacle), using these codebases as reference.

### What Was Built First (V1: Evolutionary Approach)

Claude built a complete runner game in Python (`runner_game.py`) with:
- A physics-based game engine (jump, duck, double jump, three obstacle types)
- An AI player controlled by 10 tunable parameters
- A self-improvement loop using random gaussian mutation (not LLM-driven)

This V1 worked immediately -- the baseline already scored well (mean=72.7)
because Claude hand-tuned the default parameters using physics calculations.
The evolutionary loop reached the 50+ target in 2-4 iterations.

But the user correctly identified: **this was not Karpathy's framework**. It
used blind random mutation, not LLM reasoning. There was no git versioning,
no failure analysis, no accumulated learnings.

---

## 2. Building the Real Karpathy Framework

### The Architecture

The user pushed for the real implementation. Through iterative discussion, the
architecture evolved to mirror the reference codebases exactly:

| Component | prompt-optimizer | Our Runner Game |
|-----------|-----------------|-----------------|
| Editable file | `prompt.txt` | `strategy.json` |
| Evaluation script | `evaluate.py` | `evaluate.py` |
| Read-only infrastructure | `evaluate.py` | `game_engine.py` |
| Agent instructions | `program.md` | `program.md` |
| Learnings | `resources.md` | `resources.md` |
| Experiment log | `results.tsv` | `results.tsv` |
| Failure analysis | `last_run.json` | `last_run.json` |
| Branch pattern | `prompt-opt/<tag>` | `runner-opt/<tag>` |

Key files created:
- **`game_engine.py`** (read-only): Game simulation, AI player, evaluation harness
- **`evaluate.py`** (read-only): Runs strategy.json against 20 game seeds
- **`strategy.json`** (editable): The 10 AI parameters -- the only file the agent modifies
- **`program.md`** (read-only): Instructions for the autonomous agent
- **`server.py`**: HTTP server bridging the browser to real files, git, and Python evaluation

### The HTML Visualization Problem

A significant portion of the development was spent on the HTML visualization.
The journey went through several iterations:

**Iteration 1**: Standalone HTML with in-memory evolution (random mutation).
Worked but was disconnected from the Karpathy framework -- no real files, no
git, no LLM reasoning.

**Iteration 2**: HTML calling server.py API endpoints. The browser orchestrated
the real Karpathy loop: reading strategy.json, running evaluate.py, executing
git commit/reset. But mutations were still random.

**Iteration 3**: Added Gemini LLM reasoning. The browser calls `/api/reason`
which sends the current strategy, death analysis, and accumulated learnings to
Gemini, which proposes targeted parameter changes.

**The Revert Bug**: A persistent issue where `index.html` kept reverting to the
old standalone version. Root cause: `server.py` used `git reset --hard HEAD~1`
to discard failed experiments, which reset ALL files including `index.html`.
Fix: changed to `git checkout HEAD~1 -- strategy.json` + `git reset HEAD~1`
to only revert the strategy file.

### Speed and Visual Clarity

The user identified several UX problems through hands-on testing:

1. **Game too fast**: Even at "0.5x", the runner moved too quickly for human
   observation. Fixed by implementing fractional tick accumulation (0.05 ticks
   per frame = 3 ticks/second for "Ultra Slow" mode).

2. **No episode boundaries**: Games started and ended without visual indication.
   Fixed with overlays ("New Game", "Game Over" with score), death flash effects,
   collision markers (red X, explosion ring, "COLLISION!" label), and configurable
   pause between games.

3. **Collision gap**: The player appeared to die before touching the obstacle.
   Root cause: the game engine advanced distance before checking collisions, so
   the death frame showed a post-collision position. Fixed by snapping the player
   position to the obstacle on collision.

4. **Duck death confusion**: The runner appeared to successfully duck under a
   high obstacle but still died. This was actually correct behavior -- the AI
   released the duck too early (duck_release=-10) while still under the obstacle
   (width ~25), causing it to stand up and collide. This failure pattern became
   a key optimization target.

---

## 3. The Gemini Integration

### How Gemini Fits the Karpathy Pattern

In Karpathy's framework, the agent (originally Claude Code) reads failure data,
reasons about what went wrong, and proposes changes. In our implementation,
Gemini fills this role:

```
Each Generation:
  1. Server sends Gemini:
     - Current strategy parameters
     - Death analysis from last_run.json (which obstacle type killed the AI,
       player state at death, speed)
     - Accumulated learnings from resources.md
     - Plateau warning if stuck

  2. Gemini reasons about physics and proposes new parameters

  3. Browser writes strategy.json, git commits, runs evaluate.py

  4. If improved: KEEP (commit stays, resources.md updated with what worked)
     If not: DISCARD (git reset, resources.md updated with what failed)
```

### The System Prompt

The Gemini system prompt provides:
- Complete game physics documentation
- All 10 parameter definitions with valid ranges
- Progressive difficulty explanation (high obstacles start at obstacle 20)
- Decision logic formulas
- Concrete guidance for parameter tuning based on death patterns

### What Makes This Not Pure Karpathy

In the pure Karpathy pattern (`program.md` from the reference codebases), the
agent runs indefinitely with no human intervention and no guardrails beyond
the stop conditions in `.env`. The agent is expected to be creative enough to
break through any plateau on its own.

Our implementation adds two deviations:

1. **Plateau detection with hints**: After 3 consecutive discards, the system
   injects a WARNING into the Gemini prompt telling it to try different
   parameters. When scores are stuck around 20, it explicitly suggests duck
   parameter values. When scores are high (>40) but overshooting, it tells
   Gemini to make small refinements instead of bold changes.

2. **Progressive prompt guidance**: The system prompt includes "CRITICAL
   ANALYSIS RULES" that tell Gemini to look at death_by_type first, and gives
   concrete good parameter ranges. The pure Karpathy pattern would let the
   agent discover these ranges on its own.

These deviations were necessary because Gemini 2.5 Flash (the free tier model)
could not break through the score-20 plateau on its own -- it kept tweaking
jump parameters while ignoring the duck parameters needed for high obstacles.
Gemini 2.5 Pro, the stronger model, was able to make the breakthrough on its
first attempt even before the plateau hints kicked in.

---

## 4. The Training Journey

### Phase 1: Gemini 2.5 Flash (Runs 1-2, ~20 generations)

The first runs used Gemini 2.5 Flash on the free tier.

**Run 1 (6 generations)**:
- Gen 1 KEEP: jump_trigger 45->60, speed_factor 0.5->1.0. Mean 12.3->22.1
- Gen 2-6: ALL DISCARDED. Stuck at mean=22.1. Gemini kept tweaking jump
  parameters (jump_trigger, dj_height_frac, dj_min_ticks) but never touched
  duck_trigger or duck_speed_factor.

**Run 2 (9 generations)**:
- Gen 1 KEEP: Similar jump improvements. Mean 12.3->22.1
- Gen 2-9: ALL DISCARDED. Same plateau. Gemini tried duck_trigger=50 once
  (Gen 6) but not enough -- needed 80-120. Also tried duck_trigger=60 with
  duck_speed_factor=1.0 (Gen 9) but still insufficient.

**Diagnosis**: The AI scores ~20 then dies because high obstacles start at
obstacle index 20. With duck_trigger=40 and duck_speed_factor=0.3, the adjusted
duck distance is 40 + 5*0.3 = 41.5 units -- too close to react. Flash couldn't
reason through this despite the death analysis showing "high" obstacle deaths.

### Phase 2: Gemini 2.5 Pro (Final Run, 9 generations)

Switched to Gemini 2.5 Pro (not free tier, stronger reasoning).

**Gen 1 (KEEP -- the breakthrough)**:
Gemini Pro analyzed the death data and made five simultaneous changes:
- jump_trigger: 45 -> 85 (jump earlier)
- speed_factor: 0.5 -> 3.0 (compensate for speed)
- duck_trigger: 40 -> 90 (duck much earlier)
- duck_release: -10 -> -40 (hold duck through full obstacle)
- duck_speed_factor: 0.3 -> 1.5 (duck adapts to speed)

Mean jumped from 12.3 to **60.4** (+48.1). One generation. This is what Flash
couldn't do in 20 generations -- Pro understood that BOTH jump and duck needed
fixing simultaneously.

**Gen 2-5 (ALL DISCARDED -- the overshoot)**:
Pro then overcorrected, pushing jump_trigger to 105-115:
- Gen 2: jump_trigger 85->105 → mean=21.6 (jumped too early, landed on obstacles)
- Gen 3: jump_trigger 85->105, speed_factor 3->5 → mean=2.5 (catastrophic)
- Gen 4: jump_trigger 85->115 → mean=0.5 (almost total failure)
- Gen 5: jump_trigger 85->105, duck_trigger 90->115 → mean=56.9 (close but worse)

**Gen 6 (KEEP -- modest gain)**:
jump_trigger 85->110, duck_trigger 90->120, duck_speed_factor 1.5->2.0.
Mean=60.5 (+0.2). Tiny improvement but kept.

**Gen 7 (DISCARD -- catastrophe)**:
jump_trigger 110->130, aggressive double jump. Mean=0.0. Total failure.
Gemini learned extreme values destroy performance.

**Gen 8 (KEEP -- the self-correction)**:
This was the pivotal moment. Gemini's reasoning:

> "By significantly DECREASING jump_trigger into the recommended range, the AI
> will jump earlier and have more time to clear ground obstacles."

It pulled jump_trigger **back down from 110 to 85** and increased speed_factor
to 4.5. Mean=62.2 (+1.7). Gemini recognized its own overcorrection and reversed
it -- genuine self-correcting reasoning.

**Gen 9 (KEEP -- TARGET REACHED)**:
Gemini identified the final missing piece -- double jump was underutilized:

> "I will make the double jump significantly more aggressive by increasing its
> height fraction trigger, allowing it to activate when the AI is close to the
> obstacle's height but needs a final boost to clear it."

Changes: jump_trigger 85->95, dj_height_frac 0.5->1.1, dj_min_ticks 10->6,
dj_max_dist 40->80.

**Result: mean=76.6, min=62. ALL 20 games scored above 50. TARGET REACHED.**

### Final Strategy

```json
{
    "jump_trigger": 95,         (was 45 -- jumps earlier)
    "jump_max_dist": 140,       (unchanged)
    "emergency_dist": 8,        (unchanged)
    "speed_factor": 4.5,        (was 0.5 -- adapts to speed)
    "dj_height_frac": 1.1,      (was 0.5 -- aggressive double jump)
    "dj_min_ticks": 6,          (was 10 -- double jumps sooner)
    "dj_max_dist": 80,          (was 40 -- wider double jump range)
    "duck_trigger": 110,        (was 40 -- ducks much earlier)
    "duck_release": -40,        (was -10 -- holds duck through obstacle)
    "duck_speed_factor": 2.0    (was 0.3 -- duck adapts to speed)
}
```

### Final Scores

```
[90, 74, 88, 84, 82, 87, 71, 67, 63, 75, 75, 79, 75, 67, 76, 92, 69, 70, 86, 62]
Mean: 76.6, Min: 62, Max: 92
All 20 games above 50: YES
```

---

## 5. Human-AI Collaboration

This project was a genuine collaboration. Neither the human nor the AI could
have reached the final result alone.

### What the Human Contributed

1. **Vision and direction**: The user insisted on implementing the REAL Karpathy
   framework, not a simulation. When Claude built a standalone HTML demo, the
   user pushed: "I want the HTML to implement the real/actual Karpathy framework
   using program.md and doing the keep/discard actions."

2. **Quality standards**: The user tested every iteration hands-on and reported
   specific visual problems (runner too fast, collision gap, unclear episode
   boundaries, confusing episode/gen/seed terminology). Each report led to
   targeted fixes.

3. **Critical questioning**: Questions like "is there an outer loop missing?",
   "why are there two variants?", "does the current implementation support
   observable progression?" forced the architecture to improve.

4. **Debugging by observation**: The user spotted the score-20 plateau, the
   duck death confusion, and the collision gap -- all from watching the game
   visually. Without human eyes on the output, these issues would have persisted.

5. **Model selection**: The decision to switch from Gemini Flash to Gemini Pro
   was the user's call, and it was the right one -- Pro broke through the
   plateau on its first generation.

6. **Restraint**: When the evolution got stuck, the user's instinct was to
   intervene. But they recognized: "we are not supposed to intervene" -- staying
   true to Karpathy's "NEVER STOP" principle. The user waited, and Gemini Pro
   eventually self-corrected and reached the target.

### What Claude Contributed

1. **Full implementation**: Game engine, evaluation harness, server, HTML
   visualization, all the plumbing connecting browser to Python to git to Gemini.

2. **Physics analysis**: Claude calculated jump arcs, collision timing, and
   parameter sensitivities to create the game engine and system prompt.

3. **Root cause analysis**: When bugs appeared (collision gap, file reversion,
   plateau), Claude traced them to specific code issues and fixed them.

4. **Gemini prompt engineering**: The system prompt that teaches Gemini about
   game physics, progressive difficulty, and parameter relationships was
   critical to Gemini Pro's success.

### What Gemini Contributed

1. **The breakthrough**: Gen 1 with Pro -- five parameters changed simultaneously
   based on physics reasoning, jumping mean from 12.3 to 60.4.

2. **Self-correction**: Gen 8 -- recognizing its own overcorrection and pulling
   jump_trigger back down.

3. **The final unlock**: Gen 9 -- identifying that aggressive double jump
   (dj_height_frac=1.1) was the key to clearing tall late-game obstacles.

---

## 6. Mapping to Karpathy's Framework

### What Matches Exactly

1. **Single-file modification**: Only `strategy.json` is edited. Everything else
   is read-only infrastructure.

2. **Git-based versioning**: Every experiment is a commit. Discards revert
   strategy.json. The branch tip is always the best-known strategy. Only kept
   experiments survive in `git log`.

3. **Data-driven decisions**: The agent reads structured failure data
   (`last_run.json`) with per-game death context before proposing changes.

4. **Monotonic improvement**: The branch only advances when the metric improves.

5. **Autonomous loop**: Once started, the loop runs without human intervention
   until the target is met.

6. **Accumulated learnings**: `resources.md` records what worked and what didn't,
   fed back to the agent in subsequent generations.

7. **Results tracking**: `results.tsv` logs every experiment with commit hash,
   scores, status, and description.

8. **Branch per run**: Each click of Start Evolution creates a new
   `runner-opt/<timestamp>` branch.

### What Differs

1. **Plateau hints**: After consecutive discards, the system prompt injects
   guidance about which parameters to try. Pure Karpathy relies on the agent's
   intelligence to break through on its own.

2. **Progressive prompt guidance**: The system prompt includes concrete good
   parameter ranges and critical analysis rules. The original pattern gives the
   agent only the code and lets it figure out strategies.

3. **Visual feedback loop**: The HTML plays all 20 evaluation games visually
   per generation. This doesn't affect the framework's operation but allows a
   human to observe and understand what's happening -- something the original
   terminal-only approach doesn't provide.

4. **Safe git reset**: Our reset only reverts `strategy.json`, not all files.
   The original uses `git reset --hard HEAD~1` which resets everything.

---

## 7. Lessons Learned

### On LLM Capability

Gemini 2.5 Flash (free tier) could not break the score-20 plateau despite 20
generations of attempts. It kept proposing similar jump parameter tweaks without
ever making the conceptual leap to fix duck parameters. Gemini 2.5 Pro broke
through on its first generation by understanding that BOTH jump and duck needed
fixing simultaneously. Model capability matters enormously for the Karpathy
pattern.

### On Overshooting

After a big improvement, the LLM tends to overcorrect -- pushing parameters
further in the same direction that worked. Gen 1's jump_trigger=85 worked
beautifully, but Gemini then pushed to 105, 115, 130 in subsequent generations,
each time making things worse. The self-correction in Gen 8 (pulling back to 85)
was a sign of genuine reasoning, not pattern matching.

### On the Power of Failure Analysis

The `last_run.json` death analysis was the key enabler. It told the agent not
just "the score was 22" but "the AI died to a high obstacle while standing at
speed 6.1." This structured failure data is what allowed Gemini Pro to make
targeted fixes instead of blind guesses.

### On Human-AI Collaboration

The human's role was not to solve the optimization problem -- that was Gemini's
job. The human's role was to ensure the SYSTEM was correct: the right
architecture, the right evaluation, the right visualization, the right model.
Once the system was right, the LLM could do its job autonomously.

---

## 8. File Inventory

| File | Purpose |
|------|---------|
| `strategy.json` | The 10 AI parameters (only file Gemini edits) |
| `game_engine.py` | Game simulation + AI player (read-only) |
| `evaluate.py` | Evaluation harness -- 20 seeds (read-only) |
| `server.py` | HTTP server: files, git, evaluate.py, Gemini API |
| `program.md` | Agent instructions (Karpathy pattern) |
| `resources.md` | Accumulated learnings from experiments |
| `results.tsv` | Full experiment history (kept + discarded) |
| `last_run.json` | Per-game death analysis from last evaluation |
| `index.html` | Visual frontend: game playback, charts, Gemini reasoning |
| `.env` | Gemini API key and model selection |
| `runner_game.py` | V1 evolutionary approach (standalone, no LLM) |
| `test_runner.py` | 16 automated tests |
| `docs/` | Documentation |
