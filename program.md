# runner-optimizer

Autonomous runner game strategy optimizer, using Karpathy's autoresearch pattern.

An LLM agent iteratively edits `strategy.json`, commits, evaluates, and keeps or
discards changes based on game scores. The goal is to achieve a score of 50+ on
ALL evaluation games.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar15`). The branch `runner-opt/<tag>` must not already exist -- this is a fresh run.
2. **Create the branch**: `git checkout -b runner-opt/<tag>` from current main/master.
3. **Read the in-scope files**: Read these files for full context:
   - `program.md` -- this file, your instructions.
   - `strategy.json` -- the strategy parameters you will modify. **This is the only file you optimize.**
   - `game_engine.py` -- the game engine and AI player. Read-only. Understand the physics and decision logic.
   - `evaluate.py` -- the evaluation script. Read-only.
   - `resources.md` -- accumulated learnings from past experiments. You will update this.
4. **Verify setup**: Run `python evaluate.py` to confirm it works and establish the baseline.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Game Overview

The runner game is a side-scrolling obstacle course. The AI player automatically
runs forward and must clear obstacles to score points (1 point per obstacle).

### Obstacle Types
- **ground**: Sits on the ground (height 20-50). Player must JUMP over it.
- **low**: Sits on the ground (height 15-28). Player must JUMP over it.
- **high**: Overhead bar (clearance 22-30 from ground). Player must DUCK under it (height reduces from 40 to 20).

### Physics
- Base speed: 5.0 units/tick, increases by 0.02 per score point (cap +2.5)
- Jump power: 13.0 (vertical velocity), gravity: -0.8/tick^2
- Jump peak: ~99 units high, duration: ~32 ticks
- Double jump: 0.75x power, available once per jump arc
- Duck height: 20 units (vs 40 standing)

### AI Decision Logic (in game_engine.py AIPlayer.decide)
The AI uses the parameters from strategy.json to decide when to jump, duck, or
double-jump. Key formulas:
- `adjusted_jump_dist = jump_trigger + speed * speed_factor`
- `adjusted_duck_dist = duck_trigger + speed * duck_speed_factor`
- Jump when obstacle is within adjusted_jump_dist but beyond emergency_dist
- Duck when high obstacle is within adjusted_duck_dist but beyond duck_release
- Double jump if: jumping, enough ticks elapsed (dj_min_ticks), obstacle close
  (dj_max_dist), and player height < obstacle_height * dj_height_frac

### Progressive Difficulty
- First 8 obstacles: ground only
- Obstacles 8-20: ground + low
- Obstacles 20+: ground + low + high (increasing high frequency)
- Gaps between obstacles shrink over time (280 -> 100-150 units)
- Occasional speed-boost sections (1.05x-1.35x)

## Strategy Parameters

`strategy.json` contains these tunable parameters:

| Parameter | Description | Typical Range |
|-----------|-------------|---------------|
| `jump_trigger` | Base distance (units) to trigger jump | 30-200 |
| `jump_max_dist` | Maximum distance to consider jumping | 60-300 |
| `emergency_dist` | Last-resort jump distance | 5-50 |
| `speed_factor` | Speed multiplier for jump timing | 0-8 |
| `dj_height_frac` | Double jump if below height*frac | 0.3-1.5 |
| `dj_min_ticks` | Min ticks after jump before double jump | 2-15 |
| `dj_max_dist` | Max distance for double jump consideration | 30-150 |
| `duck_trigger` | Base distance to start ducking | 40-200 |
| `duck_release` | Distance (negative=past) to stop ducking | -60-0 |
| `duck_speed_factor` | Speed multiplier for duck timing | 0-5 |

## What You CAN Do

- Modify `strategy.json` -- this is the only file you edit. Tune any parameter value.
- Update `resources.md` -- append what you learned after each experiment.
- Add comments in strategy.json to explain your reasoning (JSON doesn't support comments, so keep notes in resources.md instead).

## What You CANNOT Do

- Modify `game_engine.py`. It is read-only.
- Modify `evaluate.py`. It is read-only.
- Add new files or dependencies.

## The Goal

**Get `min_score >= 50` across ALL 20 evaluation games.** The evaluation runs 20
deterministic game seeds (0-19). Every single game must score at least 50 points.

Secondary goal: maximize `mean_score` (higher average is better, all else equal).

## Output Format

After `python evaluate.py > run.log 2>&1`, the script prints:

```
---
mean_score:     72.50
min_score:      57
max_score:      87
pct_above_50:   100.0
all_above_50:   True
games_played:   20
parse_errors:   0
target:         50
extended_mean:  75.80
extended_min:   57
extended_all50: True
```

Extract key metrics: `grep "^mean_score:\|^min_score:\|^all_above_50:" run.log`

The script also writes `last_run.json` with per-game details including:
- Every game's score
- Death context: which obstacle type killed the player, player height at death,
  whether they were jumping/ducking, speed at death
- Worst 5 deaths sorted by score (lowest first)
- Death counts by obstacle type

**Read `last_run.json`** to understand failure patterns and guide your next change.

## Logging Results

Log each experiment to `results.tsv` (tab-separated):

```
commit	mean_score	min_score	status	description
```

1. git commit hash (short, 7 chars)
2. mean_score achieved
3. min_score achieved
4. status: `keep`, `discard`, or `crash`
5. short description of what this experiment tried

Example:
```
commit	mean_score	min_score	status	description
a1b2c3d	45.20	12	keep	baseline - poor jump timing
b2c3d4e	68.50	42	keep	increased jump_trigger and speed_factor
c3d4e5f	72.00	55	keep	tuned duck_trigger for high obstacles
d4e5f6g	70.00	48	discard	dj_height_frac too aggressive
```

## The Experiment Loop

The experiment runs on a dedicated branch (e.g. `runner-opt/mar15`).

LOOP UNTIL STOPPED:

1. Look at the git state: the current branch/commit we're on.
2. Read `results.tsv` and `resources.md` for context on what's been tried.
3. Read `last_run.json` to understand which specific games are failing and why.
   Focus on the **worst deaths**: what obstacle type, what was the player doing,
   what was the speed. This tells you what parameter to tune.
4. Hypothesize a change to `strategy.json`. Write down your hypothesis before
   making the change.
5. Edit `strategy.json` with your experimental parameter values.
6. `git add strategy.json && git commit -m "descriptive message"`
7. Run the experiment: `python evaluate.py > run.log 2>&1`
8. Read the results: `grep "^mean_score:\|^min_score:\|^all_above_50:" run.log`
9. If grep output is empty, something crashed. Run `tail -n 20 run.log` to diagnose.
10. Record results in `results.tsv` (do NOT commit results.tsv -- leave untracked).
11. If mean_score improved: **KEEP** the commit. Update `resources.md`.
12. If mean_score is equal or worse: **DISCARD** via `git reset --hard HEAD~1`. Update `resources.md` with what didn't work.
13. Check stop conditions:
    - If `all_above_50` is True and you KEPT the change: **TARGET REACHED**. Print final summary and stop.
    - If you've done 30+ experiments with no improvement: consider stopping.
14. If no stop condition triggered, continue the loop.

## Reasoning About Parameters

When analyzing failures in `last_run.json`, think about the physics:

**If dying to ground/low obstacles (not jumping in time)**:
- Increase `jump_trigger` (react earlier)
- Increase `speed_factor` (compensate for higher speeds)
- Decrease `emergency_dist` (allow later emergency jumps)

**If dying to ground/low obstacles (jumping too early, landing on obstacle)**:
- Decrease `jump_trigger` (jump later)
- Decrease `speed_factor` (less speed compensation)

**If dying to high obstacles (not ducking)**:
- Increase `duck_trigger` (react earlier)
- Increase `duck_speed_factor` (compensate for speed)

**If dying to high obstacles (ducking too late or releasing too early)**:
- Increase `duck_trigger` (start ducking sooner)
- Decrease `duck_release` (more negative = hold duck longer)

**If dying at high speeds (late game)**:
- Increase `speed_factor` and `duck_speed_factor` (better speed compensation)

**If double jump issues**:
- Adjust `dj_height_frac` (when to trigger double jump)
- Adjust `dj_min_ticks` (how long to wait before double jumping)
- Adjust `dj_max_dist` (range for double jump consideration)

## Strategies to Try (rough order of expected impact)

1. Increase `jump_trigger` and `speed_factor` to give more reaction time
2. Tune `duck_trigger` and `duck_speed_factor` for reliable high-obstacle clearance
3. Optimize `emergency_dist` for last-second saves
4. Fine-tune `dj_height_frac` and `dj_min_ticks` for tall obstacle clearance
5. Adjust `duck_release` to hold duck through the full obstacle width
6. Balance all parameters together for consistency across all 20 seeds
7. Test edge cases: very high speeds (late game), tight obstacle gaps

## NEVER STOP

Once the experiment loop has begun, do NOT pause to ask the human if you should
continue. Do NOT ask "should I keep going?" or "is this a good stopping point?".
The human might be asleep or away. The loop runs until the target is reached or
the human interrupts you, period.
