"""
Runner Game Engine — READ-ONLY evaluation infrastructure.
This file is the equivalent of prepare.py in the autoresearch pattern.
The LLM agent CANNOT modify this file.

Contains:
- Game simulation engine (RunnerGame, GameState, Obstacle)
- Evaluation harness (evaluate_strategy)
- Deterministic seeded RNG for reproducible games
"""

import random
import json
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


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

            if i < 8:
                obs_type = 'ground'
            elif i < 20:
                obs_type = self.rng.choice(['ground', 'ground', 'low'])
            else:
                w = [0.35 - 0.1 * progress, 0.35, 0.30 + 0.1 * progress]
                obs_type = self.rng.choices(['ground', 'low', 'high'], weights=w)[0]

            if obs_type == 'ground':
                width = self.rng.uniform(15, 25 + 8 * progress)
                height = self.rng.uniform(20, 35 + 15 * progress)
            elif obs_type == 'low':
                width = self.rng.uniform(20, 30 + 10 * progress)
                height = self.rng.uniform(15, 28)
            else:
                width = self.rng.uniform(20, 30)
                height = self.rng.uniform(22, 30)

            min_gap = max(100, 180 - 80 * progress)
            max_gap = max(150, 280 - 100 * progress)
            gap = self.rng.uniform(min_gap, max_gap)

            speed_mult = 1.0
            if i > 25 and self.rng.random() < 0.12 * progress:
                speed_mult = self.rng.uniform(1.05, 1.2 + 0.15 * progress)

            self.state.obstacles.append(Obstacle(
                x=x, width=width, height=height,
                type=obs_type, speed_mult=speed_mult
            ))
            x += width + gap

    def get_next_obstacle(self) -> Optional[Obstacle]:
        player_world_x = self.state.distance + self.state.player_x
        for obs in self.state.obstacles:
            if obs.x + obs.width > player_world_x:
                return obs
        return None

    def get_obstacles_ahead(self, count: int = 3) -> List[Obstacle]:
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
        s.speed = s.base_speed + min(s.score * 0.02, 2.5)
        next_obs = self.get_next_obstacle()
        if next_obs:
            s.speed *= next_obs.speed_mult

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

        if s.is_jumping:
            s.player_vy += s.gravity
            s.player_y += s.player_vy
            if s.player_y <= 0:
                s.player_y = 0
                s.player_vy = 0
                s.is_jumping = False
                s.can_double_jump = True
                s.player_height = 20.0 if s.is_ducking else 40.0

        s.distance += s.speed

        pw_left = s.distance + s.player_x
        pw_right = pw_left + s.player_width
        p_top = s.player_y + s.player_height

        for obs in self.state.obstacles:
            if obs.x > pw_right + 10:
                break
            if obs.x + obs.width < pw_left:
                continue
            if obs.type == 'high':
                if p_top > obs.height and s.player_y < obs.height:
                    s.game_over = True
                    return self._info()
            else:
                if s.player_y < obs.height:
                    s.game_over = True
                    return self._info()

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
# Strategy Loader — loads strategy.json (the file the LLM agent edits)
# =============================================================================

def load_strategy(path: str = "strategy.json") -> dict:
    """Load strategy parameters from JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


class AIPlayer:
    """AI that plays using strategy parameters from strategy.json."""

    def __init__(self, params: dict):
        self.p = params
        self.jump_tick = -100

    def decide(self, info: dict, game: RunnerGame) -> str:
        if info['game_over']:
            return 'none'

        p = self.p
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

        adj_jump = p['jump_trigger'] + speed * p['speed_factor']
        adj_duck = p['duck_trigger'] + speed * p['duck_speed_factor']

        # HIGH obstacles: duck
        if obs_type == 'high':
            if not jumping and dist < adj_duck and dist > p['duck_release']:
                return 'duck'
            if ducking and dist < p['duck_release']:
                return 'none'
            if ducking:
                return 'duck'
            return 'none'

        # GROUND/LOW: jump
        if not jumping:
            if dist < adj_jump and dist > p['emergency_dist']:
                self.jump_tick = tick
                return 'jump'
            if dist < p['emergency_dist'] and dist > 0:
                self.jump_tick = tick
                return 'jump'

        # Double jump if needed
        if jumping and can_dj:
            since = tick - self.jump_tick
            if since >= p['dj_min_ticks'] and dist < p['dj_max_dist']:
                if y < obs_h * p['dj_height_frac']:
                    return 'double_jump'

        return 'none'


# =============================================================================
# Game Runner & Evaluation
# =============================================================================

def play_game(params: dict, seed: int, max_ticks: int = 50000) -> dict:
    """Play one complete game, return detailed results."""
    game = RunnerGame(seed=seed)
    player = AIPlayer(params)
    info = game._info()

    death_obs = None
    while not info['game_over'] and info['tick'] < max_ticks:
        action = player.decide(info, game)
        info = game.step(action)

    # Capture death context
    if info['game_over']:
        next_obs = game.get_next_obstacle()
        if next_obs:
            death_obs = {
                'type': next_obs.type,
                'height': next_obs.height,
                'width': next_obs.width,
                'player_y': info['player_y'],
                'player_vy': info['player_vy'],
                'was_jumping': info['is_jumping'],
                'was_ducking': info['is_ducking'],
                'speed': info['speed'],
            }

    return {
        'seed': seed,
        'score': info['score'],
        'distance': info['distance'],
        'ticks': info['tick'],
        'game_over': info['game_over'],
        'death_context': death_obs,
    }


def evaluate_strategy(params: dict, seeds: List[int]) -> dict:
    """Evaluate strategy across multiple game seeds. Returns detailed results."""
    results = []
    for seed in seeds:
        r = play_game(params, seed)
        results.append(r)

    scores = [r['score'] for r in results]
    deaths = [r for r in results if r['death_context']]

    # Analyze death patterns
    death_by_type = {'ground': 0, 'low': 0, 'high': 0}
    death_details = []
    for r in deaths:
        ctx = r['death_context']
        death_by_type[ctx['type']] = death_by_type.get(ctx['type'], 0) + 1
        death_details.append({
            'seed': r['seed'],
            'score': r['score'],
            'obstacle_type': ctx['type'],
            'obstacle_height': round(ctx['height'], 1),
            'player_y_at_death': round(ctx['player_y'], 1),
            'was_jumping': ctx['was_jumping'],
            'was_ducking': ctx['was_ducking'],
            'speed_at_death': round(ctx['speed'], 1),
        })

    # Sort deaths by score (worst first) to highlight biggest problems
    death_details.sort(key=lambda d: d['score'])

    return {
        'mean_score': round(sum(scores) / len(scores), 2),
        'min_score': min(scores),
        'max_score': max(scores),
        'scores': scores,
        'all_above_50': all(s >= 50 for s in scores),
        'pct_above_50': round(sum(1 for s in scores if s >= 50) / len(scores) * 100, 1),
        'games_played': len(seeds),
        'death_by_type': death_by_type,
        'worst_5_deaths': death_details[:5],
        'all_deaths': death_details,
    }
