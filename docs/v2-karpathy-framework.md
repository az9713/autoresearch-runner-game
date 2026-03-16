# V2 Implementation: Karpathy's Autoresearch Framework

## Overview

The V2 implementation follows Karpathy's autoresearch pattern exactly as used in
the prompt-optimizer and autoresearch-master reference codebases. An LLM agent
(Claude) acts as an autonomous researcher: it reads failure analysis, hypothesizes
parameter changes, edits the strategy file, commits to git, evaluates, and keeps
or discards based on score improvement.

**Key result**: Starting from a deliberately weak baseline (mean=58.65, min=44),
the LLM agent reached all-20-games-above-50 in a single experiment, and optimized
to mean=75.40 (min=57) across 8 experiments with 4 keeps and 4 discards.

---

## Framework Mapping

| Autoresearch Concept | prompt-optimizer | autoresearch-master | Runner Game (V2) |
|---------------------|-----------------|-------------------|-----------------|
| Editable file | `prompt.txt` | `train.py` | `strategy.json` |
| Evaluation script | `evaluate.py` | `prepare.py evaluate_bpb()` | `evaluate.py` |
| Game engine | N/A (API-based) | `prepare.py` (data/tokenizer) | `game_engine.py` |
| Metric | accuracy % (higher=better) | val_bpb (lower=better) | mean_score (higher=better) |
| Target | 100% accuracy | lowest val_bpb | min_score >= 50 |
| Agent instructions | `program.md` | `program.md` | `program.md` |
| Learnings file | `resources.md` | N/A | `resources.md` |
| Experiment log | `results.tsv` | `results.tsv` | `results.tsv` |
| Failure analysis | `last_run.json` | `run.log` | `last_run.json` |
| Branch pattern | `prompt-opt/<tag>` | `autoresearch/<tag>` | `runner-opt/<tag>` |

---

## File Structure

```
claude_code_runner_game/
  game_engine.py      READ-ONLY  Game engine, AI player, evaluation harness
  evaluate.py         READ-ONLY  Evaluation script (runs strategy.json against 20 games)
  strategy.json       EDITABLE   The only file the LLM agent modifies (10 parameters)
  program.md          READ-ONLY  Instructions for the LLM agent
  resources.md        EDITABLE   Accumulated learnings (updated after each experiment)
  results.tsv         UNTRACKED  Experiment log with commit hashes
  last_run.json       GENERATED  Per-game failure analysis (written by evaluate.py)
  run.log             GENERATED  Raw evaluation output
  .claude/commands/
    optimize.md                  Slash command to start the optimization loop
```

---

## How the Loop Works

### Step-by-Step Protocol

```
1. SETUP
   - Create branch: git checkout -b runner-opt/<tag>
   - Read: program.md, strategy.json, game_engine.py, evaluate.py, resources.md
   - Run baseline: python evaluate.py > run.log 2>&1
   - Initialize results.tsv with baseline entry

2. EXPERIMENT LOOP (repeat until target met)
   a. Read last_run.json -- analyze death patterns:
      - Which obstacle type killed the player?
      - Was the player jumping or ducking?
      - What was the player_y at death?
      - What was the speed?

   b. Form hypothesis:
      "Deaths to [type] at speed [x] with player_y=[y] suggest [parameter]
       needs to be [increased/decreased] because [physics reasoning]."

   c. Edit strategy.json with new parameter values

   d. git add strategy.json && git commit -m "expN: [description]"

   e. python evaluate.py > run.log 2>&1

   f. grep "^mean_score:|^min_score:|^all_above_50:" run.log

   g. KEEP or DISCARD:
      - If mean_score improved: KEEP (advance branch)
      - If mean_score same or worse: git reset --hard HEAD~1 (discard)

   h. Update resources.md with what worked or didn't

   i. Log to results.tsv (untracked by git)

   j. Check: if all_above_50 == True and KEPT: TARGET REACHED
```

### Git State After Optimization

Only KEPT experiments appear in the git log. The branch tip always represents
the best-known strategy:

```
7fbed4c exp7: jump_trigger 85->90 to land earlier before high obstacles     [KEEP]
e5994ce exp6: speed_factor 4->4.5, duck_release -25->-40                    [KEEP]
5a6552b exp3: speed_factor 3->4, duck_trigger 60->100, duck_speed_factor    [KEEP]
6b091e8 exp1: increase jump_trigger 60->85, speed_factor 1->3               [KEEP]
3d9f6de Initial commit                                                       [BASE]
```

Discarded experiments (exp2, exp4, exp5, exp8) leave no trace in git history.
They exist only in results.tsv as a record of what was tried.

---

## Failure Analysis: How the LLM Agent Reasons

### last_run.json Structure

```json
{
  "mean_score": 75.40,
  "min_score": 57,
  "scores": [83, 70, 87, 57, 78, ...],
  "death_by_type": {"ground": 6, "low": 5, "high": 9},
  "worst_5_deaths": [
    {
      "seed": 3,
      "score": 57,
      "obstacle_type": "high",
      "obstacle_height": 26.0,
      "player_y_at_death": 6.2,
      "was_jumping": true,
      "was_ducking": false,
      "speed_at_death": 6.1
    }
  ]
}
```

### Reasoning Example

From experiment 3:
```
OBSERVATION: Deaths to ground/low obstacles show player jumping but only
reaching py=15.1 -- not high enough to clear obstacle height 19.9.

PHYSICS: At speed 5.9, adjusted_jump = 60 + 5.9*1.0 = 65.9 units.
Time to reach obstacle = 65.9/5.9 = 11.2 ticks.
Player height at tick 11.2 = 13*11.2 - 0.4*125 = 145.6 - 50 = 95.6.
Wait, that's high enough. The issue must be the TAIL end of the jump.
After clearing the leading edge, the player descends. By tick 25:
height = 13*25 - 0.4*625 = 325 - 250 = 75. Still OK.
Actually, the issue is the jump is triggered too close -- the player
hasn't gained enough height by the time it reaches the obstacle.

HYPOTHESIS: Increase speed_factor from 1.0 to 3.0 so adjusted_jump =
60 + 5.9*3.0 = 77.7, giving 77.7/5.9 = 13.2 ticks to reach obstacle.
Height at 13.2: 13*13.2 - 0.4*174 = 171.6 - 69.6 = 102. Much better.

RESULT: mean_score improved 58.65 -> 73.10 (+14.45). KEEP.
```

---

## Experiment History

| Exp | mean_score | min | Status | Description |
|-----|-----------|-----|--------|-------------|
| 0 | 58.65 | 44 | baseline | Deliberately weak: jump_trigger=60, speed_factor=1.0 |
| 1 | 73.10 | 57 | KEEP | jump_trigger 60->85, speed_factor 1->3 (+14.45) |
| 2 | 73.10 | 57 | discard | duck_trigger 60->95, duck_speed_factor 1->2 (no change) |
| 3 | 74.15 | 57 | KEEP | speed_factor 3->4, duck_trigger 60->100 (+1.05) |
| 4 | 72.95 | 57 | discard | speed_factor 4->3.5 (regression) |
| 5 | 69.15 | 56 | discard | dj_height_frac/min_ticks too restrictive (-5.0) |
| 6 | 75.15 | 57 | KEEP | speed_factor 4->4.5, duck_release -25->-40 (+1.0) |
| 7 | 75.40 | 57 | KEEP | jump_trigger 85->90 (+0.25) |
| 8 | 75.40 | 57 | discard | duck_speed_factor 1.5->2.0 (no change) |

### Progression

```
Baseline  [===========                                           ] 58.65
Exp 1     [======================================                ] 73.10  +14.45
Exp 3     [========================================              ] 74.15  +1.05
Exp 6     [=========================================             ] 75.15  +1.00
Exp 7     [=========================================             ] 75.40  +0.25
                                                          Target: 50 ---|
```

---

## How to Run the Optimization

### Manual (as done above)
```bash
git checkout -b runner-opt/<tag>
# Edit strategy.json
git add strategy.json && git commit -m "description"
python evaluate.py > run.log 2>&1
grep "^mean_score:" run.log
# If improved: keep. Otherwise: git reset --hard HEAD~1
```

### Via Claude Code Slash Command
```
/optimize
```
This reads program.md and runs the full autonomous loop.

### Via Claude Code Directly
```
claude "Read program.md and follow its instructions. Create branch runner-opt/run2 and optimize strategy.json to score 50+ on all games."
```

---

## Comparison: V1 (Evolutionary) vs V2 (Karpathy/LLM)

| Aspect | V1 (Evolutionary) | V2 (Karpathy/LLM) |
|--------|-------------------|-------------------|
| Agent | Random gaussian mutation | LLM reads failures, reasons about physics |
| Intelligence | Blind search | Semantic understanding of game mechanics |
| Versioning | In-memory only | Git commits, branch per experiment |
| Learnings | None | resources.md accumulates knowledge |
| Failure analysis | Aggregate scores only | Per-game death context (type, height, speed) |
| Experiment tracking | In-memory list | results.tsv with commit hashes |
| Reproducibility | Seed-based | Git branch tip = best strategy |
| Discoverability | Must try all parameters | Can reason about which parameter matters |
| Human readability | Opaque numbers | Hypotheses, reasoning, physics analysis |
| Cost | Free (CPU only) | LLM API calls (or local Claude Code session) |
| Speed | ~100 iterations/second | ~1 iteration/minute (includes reasoning) |
| Typical convergence | 2-4 iterations | 1-8 experiments |
