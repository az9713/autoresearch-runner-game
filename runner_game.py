"""
Self-Improving Runner Game
==========================
A runner game where an AI player autonomously improves its strategy
using the autoresearch pattern (mutate -> test -> keep/discard).

The runner must clear obstacles to score points (1 point per obstacle).
Target: 50+ points consistently.
"""

import random
import json
import copy
from dataclasses import dataclass, field, asdict
from typing import List, Optional


# =============================================================================
# Game Engine
# =============================================================================

@dataclass
class Obstacle:
    x: float           # world x position
    width: float       # obstacle width
    height: float      # obstacle height (top of ground obs, or bottom clearance for high obs)
    type: str          # 'ground', 'low', 'high'
    speed_mult: float = 1.0


@dataclass
class GameState:
    player_x: float = 50.0       # fixed screen position
    player_y: float = 0.0        # y from ground
    player_vy: float = 0.0
    player_width: float = 20.0
    player_height: float = 40.0  # 40 standing, 20 ducking
    is_jumping: bool = False
    is_ducking: bool = False
    can_double_jump: bool = True
    score: int = 0
    distance: float = 0.0        # world distance scrolled
    speed: float = 5.0
    base_speed: float = 5.0
    gravity: float = -0.8
    jump_power: float = 13.0
    game_over: bool = False
    tick: int = 0
    obstacles: List[Obstacle] = field(default_factory=list)


class RunnerGame:
    """Simulates a side-scrolling runner game."""

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.state = GameState()
        self._generate_obstacles()

    def _generate_obstacles(self):
        """Pre-generate obstacles with progressive difficulty."""
        x = 250.0
        for i in range(200):
            progress = min(i / 80.0, 1.0)

            # Type selection with progressive difficulty
            if i < 8:
                obs_type = 'ground'
            elif i < 20:
                obs_type = self.rng.choice(['ground', 'ground', 'low'])
            else:
                w = [0.35 - 0.1 * progress, 0.35, 0.30 + 0.1 * progress]
                obs_type = self.rng.choices(['ground', 'low', 'high'], weights=w)[0]

            # Dimensions
            if obs_type == 'ground':
                width = self.rng.uniform(15, 25 + 8 * progress)
                height = self.rng.uniform(20, 35 + 15 * progress)
            elif obs_type == 'low':
                width = self.rng.uniform(20, 30 + 10 * progress)
                height = self.rng.uniform(15, 28)
            else:  # high - clearance height (player must be shorter than this)
                width = self.rng.uniform(20, 30)
                height = self.rng.uniform(22, 30)  # clearance: duck height is 20

            # Gap between obstacles decreases with progress
            min_gap = max(100, 180 - 80 * progress)
            max_gap = max(150, 280 - 100 * progress)
            gap = self.rng.uniform(min_gap, max_gap)

            # Occasional speed sections
            speed_mult = 1.0
            if i > 25 and self.rng.random() < 0.12 * progress:
                speed_mult = self.rng.uniform(1.05, 1.2 + 0.15 * progress)

            self.state.obstacles.append(Obstacle(
                x=x, width=width, height=height,
                type=obs_type, speed_mult=speed_mult
            ))
            x += width + gap

    def get_next_obstacle(self) -> Optional[Obstacle]:
        """Get next obstacle ahead of player."""
        player_world_x = self.state.distance + self.state.player_x
        for obs in self.state.obstacles:
            if obs.x + obs.width > player_world_x:
                return obs
        return None

    def get_obstacles_ahead(self, count: int = 3) -> List[Obstacle]:
        """Get next N obstacles ahead."""
        player_world_x = self.state.distance + self.state.player_x
        result = []
        for obs in self.state.obstacles:
            if obs.x + obs.width > player_world_x:
                result.append(obs)
                if len(result) >= count:
                    break
        return result

    def step(self, action: str = 'none') -> dict:
        """Advance one tick. Actions: 'none', 'jump', 'duck', 'double_jump'."""
        if self.state.game_over:
            return self._info()

        s = self.state
        s.tick += 1

        # Speed ramps up with score
        s.speed = s.base_speed + min(s.score * 0.02, 2.5)
        next_obs = self.get_next_obstacle()
        if next_obs:
            s.speed *= next_obs.speed_mult

        # Actions
        if action == 'jump' and not s.is_jumping:
            s.player_vy = s.jump_power
            s.is_jumping = True
            s.can_double_jump = True
            s.is_ducking = False
            s.player_height = 40.0
        elif action == 'double_jump' and s.is_jumping and s.can_double_jump and s.player_y > 3:
            s.player_vy = s.jump_power * 0.75
            s.can_double_jump = False
        elif action == 'duck' and not s.is_jumping:
            s.is_ducking = True
            s.player_height = 20.0
        elif action == 'none' and s.is_ducking:
            s.is_ducking = False
            s.player_height = 40.0

        # Physics
        if s.is_jumping:
            s.player_vy += s.gravity
            s.player_y += s.player_vy
            if s.player_y <= 0:
                s.player_y = 0
                s.player_vy = 0
                s.is_jumping = False
                s.can_double_jump = True
                s.player_height = 20.0 if s.is_ducking else 40.0

        # Move
        s.distance += s.speed

        # Collision detection
        pw_left = s.distance + s.player_x
        pw_right = pw_left + s.player_width
        p_top = s.player_y + s.player_height

        for obs in self.state.obstacles:
            if obs.x > pw_right + 10:
                break
            if obs.x + obs.width < pw_left:
                continue

            # Horizontal overlap confirmed
            if obs.type == 'high':
                # High obstacle: clearance is obs.height from ground
                # Player collides if their top exceeds the clearance AND on the ground
                if p_top > obs.height and s.player_y < obs.height:
                    s.game_over = True
                    return self._info()
            else:
                # Ground/low: player must jump above obstacle height
                if s.player_y < obs.height:
                    s.game_over = True
                    return self._info()

        # Score: count passed obstacles
        new_score = 0
        for obs in self.state.obstacles:
            if obs.x + obs.width < pw_left:
                new_score += 1
            else:
                break
        s.score = new_score

        return self._info()

    def _info(self) -> dict:
        s = self.state
        next_obs = self.get_next_obstacle()
        obs_ahead = self.get_obstacles_ahead(3)
        dist_to_next = (next_obs.x - s.distance - s.player_x) if next_obs else 999
        return {
            'score': s.score,
            'distance': s.distance,
            'player_y': s.player_y,
            'player_vy': s.player_vy,
            'is_jumping': s.is_jumping,
            'is_ducking': s.is_ducking,
            'can_double_jump': s.can_double_jump,
            'speed': s.speed,
            'game_over': s.game_over,
            'tick': s.tick,
            'next_obs_type': next_obs.type if next_obs else None,
            'next_obs_dist': dist_to_next,
            'next_obs_height': next_obs.height if next_obs else 0,
            'next_obs_width': next_obs.width if next_obs else 0,
            'obs_ahead': [
                {'type': o.type, 'dist': o.x - s.distance - s.player_x,
                 'height': o.height, 'width': o.width}
                for o in obs_ahead
            ],
        }


# =============================================================================
# AI Strategy (tunable parameters)
# =============================================================================

@dataclass
class Strategy:
    """Tunable parameters for the AI runner."""
    # When to jump: distance to obstacle (in world units)
    jump_trigger: float = 85.0
    # Don't jump if too far
    jump_max_dist: float = 140.0
    # Emergency jump distance
    emergency_dist: float = 15.0
    # How much speed affects jump timing
    speed_factor: float = 2.5
    # Double jump: use if below this fraction of obstacle height at this delay
    dj_height_frac: float = 0.9
    dj_min_ticks: int = 6
    dj_max_dist: float = 80.0
    # Duck trigger and release distances for high obstacles
    duck_trigger: float = 90.0
    duck_release: float = -25.0
    # How much speed affects duck timing
    duck_speed_factor: float = 1.5

    def mutate(self, rng: random.Random, rate: float = 0.3,
               strength: float = 0.15) -> 'Strategy':
        """Create mutated copy."""
        new = copy.deepcopy(self)
        bounds = {
            'jump_trigger': (30.0, 200.0),
            'jump_max_dist': (60.0, 300.0),
            'emergency_dist': (5.0, 50.0),
            'speed_factor': (0.0, 8.0),
            'dj_height_frac': (0.3, 1.5),
            'dj_min_ticks': (2, 15),
            'dj_max_dist': (30.0, 150.0),
            'duck_trigger': (40.0, 200.0),
            'duck_release': (-60.0, 0.0),
            'duck_speed_factor': (0.0, 5.0),
        }
        for name, (lo, hi) in bounds.items():
            if rng.random() < rate:
                val = getattr(new, name)
                if isinstance(val, int):
                    val = max(int(lo), min(int(hi), val + rng.randint(-2, 2)))
                else:
                    val = max(lo, min(hi, val + rng.gauss(0, strength * (hi - lo))))
                setattr(new, name, val)
        return new


class AIPlayer:
    """AI that plays using a Strategy."""

    def __init__(self, strategy: Strategy):
        self.s = strategy
        self.jump_tick = -100

    def decide(self, info: dict, game: RunnerGame) -> str:
        if info['game_over']:
            return 'none'

        st = self.s
        dist = info['next_obs_dist']
        obs_type = info['next_obs_type']
        obs_h = info['next_obs_height']
        speed = info['speed']
        y = info['player_y']
        jumping = info['is_jumping']
        ducking = info['is_ducking']
        can_dj = info['can_double_jump']
        tick = info['tick']

        if obs_type is None:
            return 'none'

        # Adjust distances for speed
        adj_jump = st.jump_trigger + speed * st.speed_factor
        adj_duck = st.duck_trigger + speed * st.duck_speed_factor

        # HIGH obstacles: duck
        if obs_type == 'high':
            if not jumping and dist < adj_duck and dist > st.duck_release:
                return 'duck'
            if ducking and dist < st.duck_release:
                return 'none'
            if ducking:
                return 'duck'
            return 'none'

        # GROUND/LOW: jump
        if not jumping:
            if dist < adj_jump and dist > st.emergency_dist:
                self.jump_tick = tick
                return 'jump'
            if dist < st.emergency_dist and dist > 0:
                self.jump_tick = tick
                return 'jump'

        # Double jump if needed
        if jumping and can_dj:
            since = tick - self.jump_tick
            if since >= st.dj_min_ticks and dist < st.dj_max_dist:
                if y < obs_h * st.dj_height_frac:
                    return 'double_jump'

        return 'none'


# =============================================================================
# Game Runner
# =============================================================================

def play_game(strategy: Strategy, seed: Optional[int] = None,
              max_ticks: int = 50000) -> dict:
    game = RunnerGame(seed=seed)
    player = AIPlayer(strategy)
    info = game._info()
    while not info['game_over'] and info['tick'] < max_ticks:
        action = player.decide(info, game)
        info = game.step(action)
    return {
        'score': info['score'],
        'distance': info['distance'],
        'ticks': info['tick'],
    }


def evaluate(strategy: Strategy, seeds: List[int]) -> dict:
    scores = []
    for seed in seeds:
        r = play_game(strategy, seed=seed)
        scores.append(r['score'])
    return {
        'mean': sum(scores) / len(scores),
        'min': min(scores),
        'max': max(scores),
        'scores': scores,
        'all_above_50': all(s >= 50 for s in scores),
        'pct_above_50': sum(1 for s in scores if s >= 50) / len(scores) * 100,
    }


# =============================================================================
# Self-Improvement Loop
# =============================================================================

def self_improve(max_iters=150, target=50, n_games=15, verbose=True):
    """Autoresearch-style self-improvement loop."""
    rng = random.Random(42)
    seeds = list(range(n_games))

    strategy = Strategy()
    base = evaluate(strategy, seeds)

    log = [{
        'iter': 0, 'mean': base['mean'], 'min': base['min'],
        'max': base['max'], 'pct50': base['pct_above_50'],
        'status': 'baseline', 'scores': base['scores'],
    }]

    best_mean = base['mean']
    best_strategy = copy.deepcopy(strategy)
    plateau = 0

    if verbose:
        print("=" * 65)
        print("SELF-IMPROVING RUNNER GAME (autoresearch pattern)")
        print("=" * 65)
        print(f"Target: {target}+ on ALL {n_games} games")
        print(f"Baseline: mean={base['mean']:.1f} min={base['min']} max={base['max']}")
        print(f"  Scores: {base['scores']}")
        print("-" * 65)

    for i in range(1, max_iters + 1):
        # Adaptive mutation
        if plateau > 15:
            rate, strength = 0.8, 0.4
        elif plateau > 8:
            rate, strength = 0.5, 0.25
        else:
            rate, strength = 0.3, 0.15

        candidate = best_strategy.mutate(rng, rate=rate, strength=strength)
        result = evaluate(candidate, seeds)

        if result['mean'] > best_mean:
            status = 'KEEP'
            delta = result['mean'] - best_mean
            best_mean = result['mean']
            best_strategy = copy.deepcopy(candidate)
            plateau = 0
        else:
            status = 'discard'
            delta = result['mean'] - best_mean
            plateau += 1

        log.append({
            'iter': i, 'mean': result['mean'], 'min': result['min'],
            'max': result['max'], 'pct50': result['pct_above_50'],
            'status': status, 'delta': delta, 'scores': result['scores'],
        })

        if verbose:
            m = ">>>" if status == 'KEEP' else "   "
            print(f"{m} {i:3d}: mean={result['mean']:6.1f} min={result['min']:3d} "
                  f"max={result['max']:3d} [{status:7s}] d={delta:+.1f} "
                  f"({result['pct_above_50']:.0f}% >=50)")

        # Check target
        if result['all_above_50'] and status == 'KEEP':
            if verbose:
                print("-" * 65)
                print(f"TARGET REACHED at iteration {i}!")
                print(f"All {n_games} games >= {target}")
                print(f"Scores: {result['scores']}")
            break

    # Final evaluation on 30 seeds (includes training seeds)
    final_seeds = list(range(30))
    final = evaluate(best_strategy, final_seeds)

    # If any final seeds score < target, do additional focused improvement
    if not final['all_above_50'] and best_mean >= target:
        if verbose:
            print("\nRefining on expanded seed set...")
        expanded_seeds = list(range(30))
        for j in range(50):
            candidate = best_strategy.mutate(rng, rate=0.3, strength=0.12)
            result = evaluate(candidate, expanded_seeds)
            if result['mean'] > best_mean and result['min'] >= final['min']:
                best_mean = result['mean']
                best_strategy = copy.deepcopy(candidate)
                if verbose:
                    print(f"  Refined: mean={result['mean']:.1f} min={result['min']}")
                if result['all_above_50']:
                    break
        final = evaluate(best_strategy, final_seeds)

    if verbose:
        print("=" * 65)
        print("FINAL EVALUATION (30 games)")
        print("=" * 65)
        print(f"Mean:  {final['mean']:.1f}")
        print(f"Min:   {final['min']}")
        print(f"Max:   {final['max']}")
        print(f">=50:  {final['pct_above_50']:.0f}%")
        print(f"Scores: {final['scores']}")
        print(f"\nBest strategy:")
        for k, v in asdict(best_strategy).items():
            print(f"  {k}: {v}")

    return {
        'best_strategy': asdict(best_strategy),
        'log': log,
        'final': final,
        'iterations': len(log) - 1,
    }


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    data = self_improve(max_iters=150, target=50, n_games=15, verbose=True)

    with open('results.json', 'w') as f:
        json.dump(data, f, indent=2)
    print("\nResults saved to results.json")

    # TSV log
    with open('results.tsv', 'w') as f:
        f.write("iter\tmean\tmin\tmax\tpct50\tstatus\n")
        for e in data['log']:
            f.write(f"{e['iter']}\t{e['mean']:.1f}\t{e['min']}\t{e['max']}\t"
                    f"{e['pct50']:.0f}\t{e['status']}\n")
    print("Log saved to results.tsv")
