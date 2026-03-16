# Self-Improving Runner Game

A side-scrolling runner game with an AI player that autonomously optimizes its
own strategy to clear obstacles and score points. The AI improves itself using
Andrej Karpathy's autoresearch framework -- an LLM agent reads failure data,
reasons about what went wrong, edits a strategy file, and keeps or discards
changes based on measured results.

## Table of Contents

1. [How the Game Works](#1-how-the-game-works)
2. [How the AI Plays](#2-how-the-ai-plays)
3. [How the AI Improves Itself (Karpathy's Framework)](#3-how-the-ai-improves-itself-karpathys-framework)
4. [Mapping to Karpathy's Original Codebases](#4-mapping-to-karpathys-original-codebases)
5. [Experiment Results](#5-experiment-results)
6. [User Guide: Setup and Running](#6-user-guide-setup-and-running)
7. [File Reference](#7-file-reference)

---

## 1. How the Game Works

The game simulates an endless side-scrolling runner. A player character runs
forward automatically at increasing speed. Obstacles appear in the path. The
player scores one point for each obstacle it clears. The game ends on first
collision.

### The World

The world is a 1D horizontal track. The player has a fixed screen position
(50 units from the left edge) while obstacles scroll toward it. Each game
pre-generates 200 obstacles from a seeded random number generator, making every
game with the same seed produce the exact same obstacle layout.

### Physics

| Constant | Value | Notes |
|----------|-------|-------|
| Base speed | 5.0 units/tick | Increases by 0.02 per point scored, caps at +2.5 |
| Gravity | -0.8 units/tick^2 | Pulls the player down during jumps |
| Jump power | 13.0 units/tick | Initial upward velocity when jumping |
| Jump peak height | ~99 units | Reached at approximately tick 16 of the jump |
| Jump duration | ~32 ticks | Total time airborne from one jump |
| Double jump power | 9.75 units/tick | 75% of normal jump, available once per jump arc |
| Player height (standing) | 40 units | |
| Player height (ducking) | 20 units | |

### Obstacle Types

The game has three obstacle types that appear with progressive frequency:

**Ground obstacles** (obstacles 0-200, starting at 100% frequency)
- Sit on the ground. Height ranges from 20 to 50 units.
- The player must **jump** over them. A collision occurs if the player's feet
  (player_y) are below the obstacle's top edge.

**Low obstacles** (appear starting at obstacle 8)
- Sit on the ground. Height ranges from 15 to 28 units.
- The player must **jump** over them. Same collision rule as ground obstacles.

**High obstacles** (appear starting at obstacle 20, frequency increases)
- Overhead bars hanging from above. Clearance ranges from 22 to 30 units.
- The player must **duck** under them. When ducking, the player shrinks from
  40 units tall to 20 units tall. A collision occurs if the player's top edge
  exceeds the obstacle's clearance height while the player's feet are below it.

### Progressive Difficulty

The game gets harder over time through four mechanisms:

1. **Obstacle variety**: First 8 obstacles are ground-only. Low obstacles appear
   at obstacle 8. High obstacles appear at obstacle 20, with increasing frequency.

2. **Obstacle size**: Ground obstacles grow taller as the game progresses
   (20-35 units early, up to 20-50 units late).

3. **Shrinking gaps**: The distance between obstacles decreases from 180-280 units
   early in the game to 100-150 units later.

4. **Speed sections**: After obstacle 25, some sections have a speed multiplier
   (1.05x to 1.35x), forcing faster reactions.

### Scoring

Score = number of obstacles whose trailing edge has passed behind the player's
leading edge. One point per obstacle cleared. The game ends on first collision.

---

## 2. How the AI Plays

The AI player is a rule-based agent controlled by 10 tunable parameters stored
in `strategy.json`. Every tick (frame), the AI reads the game state, checks the
next obstacle ahead, and decides one of four actions: `jump`, `duck`,
`double_jump`, or `none`.

### Strategy Parameters

```json
{
    "jump_trigger": 90.0,
    "jump_max_dist": 140.0,
    "emergency_dist": 10.0,
    "speed_factor": 4.5,
    "dj_height_frac": 0.9,
    "dj_min_ticks": 6,
    "dj_max_dist": 80.0,
    "duck_trigger": 100.0,
    "duck_release": -40.0,
    "duck_speed_factor": 1.5
}
```

| Parameter | What It Controls |
|-----------|-----------------|
| `jump_trigger` | Base distance (in world units) at which the AI triggers a jump for ground/low obstacles. |
| `jump_max_dist` | Maximum distance at which the AI considers jumping. Prevents premature jumps. |
| `emergency_dist` | If an obstacle is this close or closer, jump immediately regardless of other conditions. |
| `speed_factor` | Multiplied by current speed and added to `jump_trigger` to compensate for faster gameplay. At speed 7: adjusted trigger = 90 + 7 * 4.5 = 121.5 units. |
| `dj_height_frac` | If the player's height is below `obstacle_height * dj_height_frac` during a jump, trigger a double jump. |
| `dj_min_ticks` | Minimum ticks after the initial jump before a double jump is considered. Prevents wasting the double jump too early in the arc. |
| `dj_max_dist` | Maximum distance to the obstacle for a double jump to be considered. |
| `duck_trigger` | Base distance at which the AI starts ducking for high obstacles. |
| `duck_release` | Distance (negative means the obstacle is behind the player) at which the AI stops ducking. |
| `duck_speed_factor` | Multiplied by speed and added to `duck_trigger` for speed compensation. |

### Decision Logic

Each tick, the AI runs this logic:

```
1. Look at the next obstacle ahead.

2. If it is a HIGH obstacle:
   - If not jumping and within duck range --> DUCK
   - If past duck_release distance       --> stop ducking (NONE)
   - If already ducking                  --> keep ducking (DUCK)

3. If it is a GROUND or LOW obstacle:
   - If not jumping and within adjusted jump range --> JUMP
   - If not jumping and within emergency range      --> JUMP (emergency)

4. If currently jumping and can double-jump:
   - If enough ticks since jump AND obstacle close AND too low --> DOUBLE JUMP

5. Otherwise --> NONE
```

The key insight is that the AI adapts its reaction distances based on current
speed. At speed 5 (early game), the adjusted jump trigger is 90 + 5*4.5 = 112.5
units. At speed 7.5 (late game), it is 90 + 7.5*4.5 = 123.75 units. This
gives the AI more lead time at higher speeds.

---

## 3. How the AI Improves Itself (Karpathy's Framework)

The self-improvement system follows Andrej Karpathy's "autoresearch" pattern,
where an LLM (Large Language Model) agent acts as an autonomous researcher.
Instead of blind random search, the agent reads failure data, reasons about
the underlying physics, forms a hypothesis, and makes a targeted edit.

### The Core Loop

```
                  +------------------+
                  |  Read last_run   |
                  |  .json (failures)|
                  +--------+---------+
                           |
                  +--------v---------+
                  |  Analyze deaths: |
                  |  type, height,   |
                  |  player state,   |
                  |  speed           |
                  +--------+---------+
                           |
                  +--------v---------+
                  |  Form hypothesis |
                  |  about which     |
                  |  parameter to    |
                  |  change and why  |
                  +--------+---------+
                           |
                  +--------v---------+
                  | Edit strategy    |
                  | .json            |
                  +--------+---------+
                           |
                  +--------v---------+
                  | git commit       |
                  +--------+---------+
                           |
                  +--------v---------+
                  | python evaluate  |
                  | .py > run.log    |
                  +--------+---------+
                           |
                  +--------v---------+
                  | Read results:    |
                  | grep mean_score  |
                  +--------+---------+
                           |
                    +------+------+
                    |             |
               Improved?    Not improved?
                    |             |
             +------v------+ +---v-----------+
             | KEEP commit | | git reset     |
             | Update      | | --hard HEAD~1 |
             | resources   | | (DISCARD)     |
             +------+------+ +---+-----------+
                    |             |
                    +------+------+
                           |
                  +--------v---------+
                  | Target met?      |
                  | (all games >=50) |
                  +--------+---------+
                           |
                    +------+------+
                    |             |
                   Yes           No
                    |             |
                  STOP     Back to top
```

### What Makes This Different From Random Search

In a traditional evolutionary approach (our V1 implementation), parameters are
randomly mutated with gaussian noise. The algorithm has no understanding of the
game -- it just tries random changes and keeps improvements.

In the Karpathy framework, the LLM agent:

1. **Reads structured failure data**: `last_run.json` tells the agent exactly
   which games failed, what obstacle type killed the player, whether the player
   was jumping or ducking at the time of death, the player's height, and the
   game speed.

2. **Reasons about physics**: The agent calculates jump arcs. For example:
   "At speed 5.9, the adjusted jump distance is 60 + 5.9 * 1.0 = 65.9 units.
   Time to reach = 65.9 / 5.9 = 11.2 ticks. Player height at tick 11.2 =
   13 * 11.2 - 0.4 * 125.4 = 95.4 units. That's high enough, so the issue
   must be something else..."

3. **Forms targeted hypotheses**: Instead of randomly changing all parameters,
   the agent identifies the specific parameter responsible for the failure
   pattern and adjusts it in the right direction.

4. **Accumulates knowledge**: `resources.md` records what worked and what did
   not, so the agent avoids repeating failed experiments.

5. **Uses git for version control**: Every experiment is a git commit. Failures
   are cleanly discarded with `git reset --hard HEAD~1`. The branch tip always
   represents the best-known strategy.

### Example: How the Agent Solved the Baseline

**Baseline state**: mean_score=58.65, min_score=44. Two games scored below 50.

**Agent reads last_run.json**:
```
Death by type: ground=5, low=8, high=7
Worst death: seed=2, score=44, type=low, height=19.9,
             player_y=15.1, jumping=True, speed=5.9
```

**Agent reasons**: "The player jumped but only reached height 15.1 when the
obstacle is 19.9 tall. The player was jumping (jumping=True) but too low --
this means it jumped too late. The jump_trigger is 60, giving adjusted distance
of 60 + 5.9*1.0 = 65.9. Time to reach: 65.9/5.9 = 11.2 ticks. Height at
tick 11.2: 13*11.2 - 0.4*125.4 = 95.4. That should be enough... unless the
player is already past the leading edge. The issue is the adjusted distance is
too small -- the player starts jumping when the obstacle is only 65.9 units
away, but at speed 5.9 it takes only 11 ticks, and the obstacle's trailing
edge extends further. I need to increase jump_trigger and speed_factor."

**Agent edits strategy.json**: jump_trigger 60->85, speed_factor 1->3.

**Result**: mean_score jumps from 58.65 to 73.10 (+14.45). All 20 games now
score above 50. The commit is KEPT.

---

## 4. Mapping to Karpathy's Original Codebases

This project is built on two reference implementations of Karpathy's pattern:

### Reference 1: prompt-optimizer

An autonomous prompt engineering system that evolved a 4-line event extraction
prompt into a 27-line perfect prompt, achieving 100% accuracy (180/180 fields)
in 8 experiments with zero human intervention.

### Reference 2: autoresearch-master

Karpathy's autonomous LLM training framework where agents modify a training
script (`train.py`), run 5-minute GPU training sessions, and keep or discard
based on validation loss.

### How They Map to the Runner Game

| Concept | prompt-optimizer | autoresearch-master | Runner Game |
|---------|-----------------|-------------------|-------------|
| **What the agent edits** | `prompt.txt` (system prompt for event extraction) | `train.py` (GPT model architecture and training loop) | `strategy.json` (10 numeric AI parameters) |
| **Evaluation script** | `evaluate.py` (scores prompt against 30 test examples) | `prepare.py` + `train.py` (trains model, measures val_bpb) | `evaluate.py` (plays 20 games, measures scores) |
| **Read-only infrastructure** | `evaluate.py`, `eval_set.jsonl` | `prepare.py` (data, tokenizer, eval harness) | `game_engine.py` (game physics, collision, AI player logic) |
| **Metric** | accuracy % (higher = better) | val_bpb (lower = better) | mean_score (higher = better) |
| **Target** | 100% accuracy | Lowest possible val_bpb | min_score >= 50 across all 20 games |
| **Agent instructions** | `program.md` | `program.md` | `program.md` |
| **Accumulated learnings** | `resources.md` | (not formalized) | `resources.md` |
| **Experiment log** | `results.tsv` (commit, accuracy, status, description) | `results.tsv` (commit, val_bpb, memory, status, description) | `results.tsv` (commit, mean_score, min_score, status, description) |
| **Failure analysis** | `last_run.json` (per-example field scores, raw responses) | `run.log` (training metrics, stack traces) | `last_run.json` (per-game death context: obstacle type, player state, speed) |
| **Branch naming** | `prompt-opt/<tag>` | `autoresearch/<tag>` | `runner-opt/<tag>` |
| **Keep/discard mechanism** | Keep commit if accuracy improved; `git reset --hard HEAD~1` to discard | Keep commit if val_bpb improved; `git reset --hard HEAD~1` to discard | Keep commit if mean_score improved; `git reset --hard HEAD~1` to discard |
| **Stop condition** | MAX_ITERATIONS, MAX_COST_USD, PLATEAU_WINDOW from .env | Manual interruption | all_above_50 == True |
| **Autonomy directive** | "NEVER STOP unless a stop condition triggers" | "NEVER STOP -- loop runs until the human interrupts you" | "NEVER STOP -- the loop runs until the target is reached or the human interrupts" |

### The Five Principles Shared Across All Three

1. **Single-file modification**: The agent edits exactly one file. Everything
   else is read-only infrastructure. This constrains the search space and
   ensures reviewability.

2. **Git-based versioning**: Every experiment is a commit. Failures are
   discarded with `git reset --hard HEAD~1`. The branch tip always represents
   the best-known state. The full history of kept improvements is in the git log.

3. **Data-driven decisions**: The agent reads structured output (JSON failure
   details) to guide its next hypothesis. It does not guess blindly.

4. **Monotonic improvement**: The branch only advances when the metric improves.
   The best result is always at the branch tip.

5. **Autonomous loop**: The agent runs without human intervention until a stop
   condition triggers. The human may be asleep or away.

---

## 5. Experiment Results

### Optimization Trajectory

Starting from a deliberately weak baseline (jump_trigger=60, speed_factor=1.0),
the LLM agent ran 8 experiments over the `runner-opt/mar15` branch:

```
Experiment  mean_score  min  Status   Change
---------  ----------  ---  ------   ------
baseline       58.65    44  keep     jump_trigger=60, speed_factor=1.0
exp1           73.10    57  KEEP     jump_trigger 60->85, speed_factor 1->3
exp2           73.10    57  discard  duck_trigger 60->95 (no effect)
exp3           74.15    57  KEEP     speed_factor 3->4, duck_trigger 60->100
exp4           72.95    57  discard  speed_factor 4->3.5 (regression)
exp5           69.15    56  discard  dj_height_frac 0.9->1.1 (major regression)
exp6           75.15    57  KEEP     speed_factor 4->4.5, duck_release -25->-40
exp7           75.40    57  KEEP     jump_trigger 85->90
exp8           75.40    57  discard  duck_speed_factor 1.5->2.0 (no effect)
```

### Git History (Only Kept Experiments)

```
7fbed4c exp7: jump_trigger 85->90 to land earlier before high obstacles
e5994ce exp6: speed_factor 4->4.5, duck_release -25->-40 for longer duck hold
5a6552b exp3: speed_factor 3->4, duck_trigger 60->100, duck_speed_factor 1->1.5
6b091e8 exp1: increase jump_trigger 60->85, speed_factor 1->3
3d9f6de Initial commit
```

### Final Strategy

```json
{
    "jump_trigger": 90.0,
    "jump_max_dist": 140.0,
    "emergency_dist": 10.0,
    "speed_factor": 4.5,
    "dj_height_frac": 0.9,
    "dj_min_ticks": 6,
    "dj_max_dist": 80.0,
    "duck_trigger": 100.0,
    "duck_release": -40.0,
    "duck_speed_factor": 1.5
}
```

### Final Evaluation

```
Standard (20 games):  mean=75.40  min=57  max=92  100% >= 50
Extended (30 games):  mean=76.77  min=57  max=92  100% >= 50
```

### Key Learnings (from resources.md)

**What works**:
- jump_trigger=85-90 gives enough reaction time for ground/low obstacles
- speed_factor=4.0-4.5 scales jump timing correctly at high speeds
- duck_trigger=100 with duck_speed_factor=1.5 catches high obstacles reliably
- duck_release=-40 holds the duck through the full obstacle width
- Double jump (dj_height_frac=0.9, dj_min_ticks=6) is critical for tall obstacles

**What does not work**:
- Reducing speed_factor below 3.5 causes missed jumps at high speeds
- Restricting double jump parameters causes a major score regression
- Adjusting duck parameters alone without tuning speed compensation has no effect

---

## 6. User Guide: Setup and Running

### Prerequisites

- **Python 3.10 or later** (tested with Python 3.13)
- **Git** (for the Karpathy experiment loop)
- **No additional packages required** -- the game uses only Python standard library modules
  (`random`, `json`, `copy`, `dataclasses`, `typing`, `pathlib`, `sys`)

To check your Python version:
```bash
python --version
```

If you see `Python 3.10.x` or higher, you are good to go. If not, install
Python from https://www.python.org/downloads/

### Quick Start: Run the Evaluation

This runs the current strategy against 20 game seeds and shows the results:

```bash
cd claude_code_runner_game
python evaluate.py
```

Expected output:
```
---
mean_score:     75.40
min_score:      57
max_score:      92
pct_above_50:   100.0
all_above_50:   True
games_played:   20
parse_errors:   0
target:         50
extended_mean:  76.77
extended_min:   57
extended_all50: True
```

This also writes `last_run.json` with detailed per-game failure analysis.

### Quick Start: Run the V1 Evolutionary Self-Improvement

This runs the in-memory evolutionary loop (random mutation, no LLM needed):

```bash
python runner_game.py
```

This will show the baseline, iterate through mutations, and display when the
target is reached. Results are saved to `results.json` and `results.tsv`.

### Quick Start: Watch the Game Visually

Open `index.html` in any modern web browser:

```bash
# On Windows
start index.html

# On macOS
open index.html

# On Linux
xdg-open index.html
```

In the browser:
- Click **Start Evolution** to watch the AI evolve in real-time
- Use **1x / 5x / 20x** buttons to control evolution speed
- Click **Watch Best AI** to see the best strategy play a full game
- The right panel shows the evolution log (kept/discarded experiments)

### Quick Start: Run Tests

```bash
python test_runner.py
```

Expected output: `RESULTS: 16 passed, 0 failed, 16 total`

### Running the Karpathy Optimization Loop

This is the full LLM-agent-driven optimization. You need Claude Code installed.

**Step 1**: Initialize the repository (if not already done):
```bash
cd claude_code_runner_game
git init
git add -A
git commit -m "Initial commit"
```

**Step 2**: Reset the strategy to a weak baseline to give the agent room to improve:
```bash
cat > strategy.json << 'EOF'
{
    "jump_trigger": 60.0,
    "jump_max_dist": 140.0,
    "emergency_dist": 10.0,
    "speed_factor": 1.0,
    "dj_height_frac": 0.9,
    "dj_min_ticks": 6,
    "dj_max_dist": 80.0,
    "duck_trigger": 60.0,
    "duck_release": -25.0,
    "duck_speed_factor": 1.0
}
EOF
git add strategy.json
git commit -m "Reset to weak baseline for optimization"
```

**Step 3**: Launch Claude Code and run the optimization:
```bash
claude "Read program.md and follow its instructions exactly. Create branch runner-opt/run1 and optimize strategy.json until all 20 games score 50 or more."
```

Or use the slash command (if Claude Code is already running):
```
/optimize
```

The agent will:
1. Create a branch `runner-opt/run1`
2. Run the baseline evaluation
3. Read failure analysis
4. Hypothesize and edit strategy.json
5. Commit, evaluate, keep or discard
6. Repeat until all games score 50+

You can leave it running unattended. The agent will not stop to ask questions.

### Manually Editing the Strategy

You can also tune the strategy by hand:

1. Edit `strategy.json` with your parameter values
2. Run `python evaluate.py` to see the results
3. Check `last_run.json` for death analysis
4. Repeat until satisfied

---

## 7. File Reference

### Core Files

| File | Editable? | Purpose |
|------|-----------|---------|
| `strategy.json` | Yes | The 10 AI parameters. The only file the LLM agent edits. |
| `game_engine.py` | No | Game simulation (physics, obstacles, collision), AI player logic, evaluation harness. |
| `evaluate.py` | No | Runs strategy.json against 20+30 game seeds, outputs metrics and writes last_run.json. |
| `program.md` | No | Instructions for the LLM agent: how to set up, run, and iterate. |
| `resources.md` | Yes | Accumulated learnings from experiments (what worked, what didn't). |

### Generated Files

| File | Purpose |
|------|---------|
| `last_run.json` | Per-game results with death context. Written by evaluate.py. |
| `run.log` | Raw evaluation output. Written by redirecting evaluate.py. |
| `results.tsv` | Experiment log (commit hash, scores, status, description). Untracked by git. |
| `results.json` | Full results from the V1 evolutionary loop. |

### V1 Files (Evolutionary Approach)

| File | Purpose |
|------|---------|
| `runner_game.py` | Self-contained game + AI + evolutionary self-improvement loop. |
| `test_runner.py` | 16 tests covering game mechanics, AI behavior, and convergence. |
| `index.html` | HTML5 canvas visualization with live evolution. |

### Documentation

| File | Purpose |
|------|---------|
| `docs/README.md` | This file. |
| `docs/v1-implementation.md` | Detailed documentation of the V1 evolutionary approach. |
| `docs/v2-karpathy-framework.md` | Technical documentation of the Karpathy framework mapping. |

### Reference Codebases (in .ignore/)

| Directory | Purpose |
|-----------|---------|
| `.ignore/prompt-optimizer/` | Karpathy's autoresearch pattern applied to prompt engineering. Achieved 100% accuracy in 8 experiments. |
| `.ignore/autoresearch-master/` | Karpathy's original autonomous LLM training framework. |
