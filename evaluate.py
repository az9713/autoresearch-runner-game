"""
Runner Game Evaluator -- runs strategy.json against game seeds, scores results.
This is the evaluation harness (READ-ONLY, like evaluate.py in prompt-optimizer).

The LLM agent CANNOT modify this file.

Usage:
    python evaluate.py > run.log 2>&1

Outputs greppable metrics and writes last_run.json with per-game failure details.
"""

import json
import sys
from pathlib import Path

from game_engine import load_strategy, evaluate_strategy

STRATEGY_FILE = Path(__file__).parent / "strategy.json"
LAST_RUN_FILE = Path(__file__).parent / "last_run.json"

# Fixed evaluation seeds -- 20 games for consistent measurement
EVAL_SEEDS = list(range(20))

# Extended evaluation seeds -- 30 games for final verification
EXTENDED_SEEDS = list(range(30))

TARGET_SCORE = 50


def main():
    # Load strategy
    try:
        params = load_strategy(str(STRATEGY_FILE))
    except FileNotFoundError:
        print(f"ERROR: {STRATEGY_FILE} not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {STRATEGY_FILE}: {e}", file=sys.stderr)
        print(f"parse_errors: 1")
        sys.exit(1)

    # Validate required fields
    required = [
        'jump_trigger', 'jump_max_dist', 'emergency_dist', 'speed_factor',
        'dj_height_frac', 'dj_min_ticks', 'dj_max_dist',
        'duck_trigger', 'duck_release', 'duck_speed_factor',
    ]
    missing = [f for f in required if f not in params]
    if missing:
        print(f"ERROR: Missing fields in strategy.json: {missing}", file=sys.stderr)
        print(f"parse_errors: 1")
        sys.exit(1)

    # Run standard evaluation
    result = evaluate_strategy(params, EVAL_SEEDS)

    # Run extended evaluation
    extended = evaluate_strategy(params, EXTENDED_SEEDS)

    # Print greppable summary (matching Karpathy's output style)
    print("---")
    print(f"mean_score:     {result['mean_score']:.2f}")
    print(f"min_score:      {result['min_score']}")
    print(f"max_score:      {result['max_score']}")
    print(f"pct_above_50:   {result['pct_above_50']:.1f}")
    print(f"all_above_50:   {result['all_above_50']}")
    print(f"games_played:   {result['games_played']}")
    print(f"parse_errors:   0")
    print(f"target:         {TARGET_SCORE}")
    print(f"extended_mean:  {extended['mean_score']:.2f}")
    print(f"extended_min:   {extended['min_score']}")
    print(f"extended_all50: {extended['all_above_50']}")

    # Write detailed results for the LLM agent to inspect
    last_run = {
        'mean_score': result['mean_score'],
        'min_score': result['min_score'],
        'max_score': result['max_score'],
        'scores': result['scores'],
        'pct_above_50': result['pct_above_50'],
        'all_above_50': result['all_above_50'],
        'target': TARGET_SCORE,
        'death_by_type': result['death_by_type'],
        'worst_5_deaths': result['worst_5_deaths'],
        'all_deaths': result['all_deaths'],
        'extended_scores': extended['scores'],
        'extended_mean': extended['mean_score'],
        'extended_min': extended['min_score'],
        'strategy': params,
    }

    with open(LAST_RUN_FILE, 'w') as f:
        json.dump(last_run, f, indent=2)

    print(f"\nDetailed results written to {LAST_RUN_FILE}", file=sys.stderr)


if __name__ == '__main__':
    main()
