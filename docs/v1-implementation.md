# V1 Implementation: Evolutionary Self-Improving Runner Game

## Overview

The V1 implementation is a self-contained Python runner game where an AI player
autonomously improves its obstacle-clearing strategy using evolutionary parameter
optimization. The system follows a simplified version of the autoresearch pattern
(mutate -> evaluate -> keep/discard) but does NOT use an LLM agent -- it uses
blind random mutation of numeric parameters.

**Key result**: The AI reaches 50+ score on all test games (mean=75.8, min=57)
within 2-4 iterations of self-improvement.

---

## Architecture

```
runner_game.py (single file, 508 lines)
  |
  +-- Game Engine (RunnerGame, GameState, Obstacle)
  |     - Simulates a side-scrolling runner
  |     - 200 pre-generated obstacles per game
  |     - Deterministic via seeded RNG
  |
  +-- AI Strategy (Strategy dataclass, AIPlayer)
  |     - 10 tunable float/int parameters
  |     - Rule-based decision logic using parameters as thresholds
  |     - Mutation via gaussian noise within bounds
  |
  +-- Evaluation (play_game, evaluate)
  |     - Plays complete games, returns scores
  |     - Evaluates across multiple seeds for robustness
  |
  +-- Self-Improvement Loop (self_improve)
        - Evolutionary: mutate best -> evaluate -> keep if better
        - Adaptive mutation rate (increases during plateau)
        - Stops when all eval games score >= 50
```

---

## Game Engine Details

### World Model

The game world is a 1D horizontal track. The player has a fixed screen X position
(50 units) while the world scrolls past. Distance traveled = world units scrolled.

Key physics constants:
- Base speed: 5.0 units/tick
- Speed increase: +0.02 per score point, capped at +2.5
- Gravity: -0.8 units/tick^2
- Jump power: 13.0 units/tick (initial vertical velocity)
- Jump peak height: ~99 units (at tick ~16)
- Jump total duration: ~32 ticks
- Double jump power: 13.0 * 0.75 = 9.75 (extends peak to ~123 units)

### Player

- Width: 20 units, Height: 40 standing / 20 ducking
- Actions per tick: 'jump', 'duck', 'double_jump', or 'none'
- Can only jump from ground (not mid-air, except double jump)
- Can only duck while on ground
- One double jump per jump arc (resets on landing)

### Obstacle Types

1. **Ground** (index 0-7: 100% ground, 8-19: ~67%, 20+: ~30-35%)
   - Sits on ground. Height: 20-50 units.
   - Player must JUMP over (player_y must exceed obstacle height).

2. **Low** (index 8-19: ~33%, 20+: ~35%)
   - Sits on ground. Height: 15-28 units.
   - Player must JUMP over.

3. **High** (index 20+: ~30-35%)
   - Overhead bar. Clearance height: 22-30 units from ground.
   - Player must DUCK under (player height 20 < clearance 22-30).
   - Collision if player_top > clearance AND player_y < clearance.

### Progressive Difficulty

The `progress` factor ranges from 0.0 (obstacle 0) to 1.0 (obstacle 80+):
- Obstacle variety increases (high obstacles appear at index 20+)
- Ground obstacle heights grow: 20-35 -> 20-50
- Gaps between obstacles shrink: 180-280 -> 100-150 units
- Occasional speed multiplier sections (1.05x-1.35x) after obstacle 25

### Collision Detection

For each obstacle overlapping the player horizontally:
- Ground/Low: `player_y < obstacle_height` = collision (must be above it)
- High: `player_top > clearance AND player_y < clearance` = collision (must duck under)

### Scoring

Score = number of obstacles whose trailing edge is behind the player's leading edge.
One point per cleared obstacle. Game ends on first collision.

---

## AI Strategy Parameters

The AI player uses a `Strategy` dataclass with 10 parameters that control when
and how it reacts to obstacles:

| Parameter | Default | Range | Purpose |
|-----------|---------|-------|---------|
| `jump_trigger` | 85.0 | 30-200 | Base distance to trigger jump |
| `jump_max_dist` | 140.0 | 60-300 | Maximum trigger distance |
| `emergency_dist` | 15.0 | 5-50 | Emergency last-second jump |
| `speed_factor` | 2.5 | 0-8 | Speed scales jump trigger: `trigger + speed * factor` |
| `dj_height_frac` | 0.9 | 0.3-1.5 | Double jump if `player_y < height * frac` |
| `dj_min_ticks` | 6 | 2-15 | Minimum ticks after jump before double jump |
| `dj_max_dist` | 80.0 | 30-150 | Double jump only if obstacle within this distance |
| `duck_trigger` | 90.0 | 40-200 | Base distance to start ducking for high obstacles |
| `duck_release` | -25.0 | -60-0 | Distance (negative = past) to stop ducking |
| `duck_speed_factor` | 1.5 | 0-5 | Speed scales duck trigger |

### Decision Logic (per tick)

```
1. If next obstacle is HIGH:
   - If not jumping and within duck range -> DUCK
   - If past duck_release distance -> stop ducking
   - Otherwise maintain current duck state

2. If next obstacle is GROUND or LOW:
   - If not jumping and within adjusted jump range -> JUMP
   - If not jumping and within emergency distance -> JUMP (emergency)

3. If jumping and can double jump:
   - If enough ticks elapsed AND obstacle close AND too low -> DOUBLE JUMP

4. Otherwise -> NONE
```

The adjusted jump distance = `jump_trigger + speed * speed_factor`.
At baseline speed 5.0: adjusted = 85 + 5*2.5 = 97.5 units.
This means the AI jumps ~97.5/5 = ~19.5 ticks before reaching the obstacle.
At tick 19.5 of a jump, player_y = 13*19.5 - 0.4*380 = 253.5 - 152 = 101.5 units.
This is well above any obstacle height (max ~50), giving comfortable clearance.

---

## Self-Improvement Loop

### How It Works

The loop is a simple (1+1) evolutionary strategy:

```
1. Initialize: baseline Strategy with hand-tuned defaults
2. Evaluate baseline on N=15 game seeds -> record mean score
3. LOOP:
   a. Mutate best strategy (gaussian noise on each parameter with probability 0.3)
   b. Evaluate mutant on same N seeds
   c. If mutant mean > best mean: KEEP (replace best)
   d. Else: DISCARD
   e. If all N games score >= 50: TARGET REACHED, stop
   f. If plateau > 8 iterations: increase mutation rate and strength
   g. If plateau > 15: large shake-up mutation
4. Final evaluation on 30 seeds for robustness
5. If any of 30 seeds < 50: do 50 more refinement iterations on expanded set
```

### Mutation Mechanics

Each parameter is independently mutated with probability `rate` (default 0.3):
- Float parameters: `value += gaussian(0, strength * (hi - lo))`
- Int parameters: `value += randint(-2, 2)`
- All values clamped to their defined bounds

Adaptive mutation when stuck:
- Plateau 0-8: rate=0.3, strength=0.15 (normal exploration)
- Plateau 8-15: rate=0.5, strength=0.25 (wider search)
- Plateau 15+: rate=0.8, strength=0.4 (shake-up)

### Why It Converges Quickly

The baseline defaults are already well-tuned through physics analysis:
- Jump timing calculated from projectile motion equations
- Duck parameters set from known player height (20) vs clearance range (22-30)
- Speed compensation factor derived from speed-distance relationship

Typical results: baseline mean=72.7 (min=57), target reached in 2-4 iterations.

---

## What This Is NOT

This is NOT the Karpathy autoresearch pattern. Key differences:

| Aspect | Karpathy Pattern | V1 Implementation |
|--------|-----------------|-------------------|
| Agent | LLM reads failures, hypothesizes, edits code | Random gaussian mutation |
| Versioning | Git commits per experiment, reset on discard | In-memory only |
| Learnings | resources.md accumulates knowledge | None |
| Failure analysis | Agent reads per-example failures | None (only aggregate score) |
| Strategy file | Editable text file (prompt.txt/train.py) | In-memory dataclass |
| Intelligence | Semantic understanding of what to change | Blind random search |
| Experiment tracking | TSV log with commit hashes | In-memory list |

The V1 approach works because the search space is small (10 parameters) and the
baseline is already close to optimal. For harder optimization problems, the
LLM-guided approach would be necessary.

---

## Test Coverage

16 tests in `test_runner.py` cover:
- Game mechanics: basic state, jump physics (peak=99.2), duck (height 40->20)
- Collision: ground obstacles (blocks), high obstacles (duck clears)
- AI behavior: jumps, ducks, uses all 3 action types
- Strategy: mutation changes parameters, evaluation returns correct structure
- Performance: baseline mean > 40, deterministic seeds, progressive difficulty
- Speed: increases with score (5.0 -> 6.6+)
- Double jump: extends height (99.2 -> 123.2)
- Convergence: self-improvement reaches 50+ target across 30 seeds

---

## Files

| File | Lines | Purpose |
|------|-------|---------|
| `runner_game.py` | 508 | Game engine + AI + evolution loop |
| `test_runner.py` | 336 | 16 tests covering all components |
| `index.html` | ~400 | Visual HTML5 canvas game with evolution UI |
| `results.json` | - | Full experiment results (generated) |
| `results.tsv` | - | Experiment log (generated) |
