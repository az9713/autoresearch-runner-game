# Autoresearch Runner Game

Re-purposing [Andrej Karpathy's autoresearch framework](https://github.com/karpathy/autoresearch)
to train a side-scrolling runner game. An LLM agent (Gemini 2.5 Pro) autonomously
optimizes the AI player's strategy by analyzing death patterns, reasoning about
game physics, and iteratively editing parameters -- keeping improvements and
discarding failures via git, exactly as in the original autoresearch pattern.

## What This Is

In Karpathy's autoresearch, an LLM agent modifies `train.py` to improve a
language model's validation loss. We apply the same pattern to a runner game:
the LLM agent modifies `strategy.json` to improve the AI player's obstacle-clearing
score. Same framework, different domain.

```
Karpathy's autoresearch:  LLM edits train.py  -> trains model  -> measures val_bpb  -> keep/discard
This project:             LLM edits strategy.json -> plays 20 games -> measures score -> keep/discard
```

The agent runs autonomously. Each experiment is a git commit. Failures are
discarded with `git reset`. The branch tip always holds the best-known strategy.
Gemini reads detailed death analysis (which obstacle type killed the AI, player
state, speed) and proposes targeted parameter changes based on physics reasoning.

## Quick Start

**Prerequisites**: Python 3.10+, git, a Gemini API key

```bash
# Clone
git clone https://github.com/az9713/autoresearch-runner-game.git
cd autoresearch-runner-game

# Install the one dependency
pip install google-genai python-dotenv

# Set your Gemini API key
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# Start the server
python server.py

# Open http://localhost:8000 in your browser
# Click "Start Evolution" and watch the AI improve
```

## How It Works

1. **Weak baseline**: The AI starts with bad parameters (scores ~12 on average)
2. **Gemini analyzes**: Reads death data -- "most deaths are high obstacles while standing, duck_trigger is too low"
3. **Gemini proposes**: Specific parameter changes with physics reasoning
4. **Evaluate**: `evaluate.py` plays 20 deterministic games, measures scores
5. **Keep or discard**: If mean score improved, git commit stays. If not, `git reset`
6. **Repeat**: Gemini sees what worked/failed and proposes the next change
7. **Target**: All 20 games scoring 50+ points

The browser shows all 20 games per generation visually, with game speed controls,
death analysis, Gemini reasoning (including full prompts), strategy diffs, and
a live progress chart.

## Results

Starting from a deliberately weak baseline (mean=12.3), Gemini 2.5 Pro reached
the target in 9 generations:

```
Gen 1:  mean=60.4  (+48.1)  KEEP   Fixed jump AND duck params simultaneously
Gen 2:  mean=21.6           DISCARD  Overshot jump_trigger
Gen 3:  mean=2.5            DISCARD  Overshot further
Gen 4:  mean=0.5            DISCARD  Catastrophic overshoot
Gen 5:  mean=56.9           DISCARD  Close but not better
Gen 6:  mean=60.5  (+0.2)   KEEP   Modest gain
Gen 7:  mean=0.0            DISCARD  Extreme values, total failure
Gen 8:  mean=62.2  (+1.7)   KEEP   Self-corrected: pulled jump_trigger BACK DOWN
Gen 9:  mean=76.6  (+14.4)  KEEP   Unlocked aggressive double jump -- TARGET REACHED
```

Final: mean=76.6, min=62, max=92. All 20 games above 50.

## Mapping to Karpathy's Framework

| Concept | autoresearch | prompt-optimizer | This project |
|---------|-------------|-----------------|--------------|
| Editable file | `train.py` | `prompt.txt` | `strategy.json` |
| Evaluation | `prepare.py` | `evaluate.py` | `evaluate.py` |
| Metric | val_bpb (lower=better) | accuracy % | mean_score (higher=better) |
| Agent brain | Claude Code | Claude Code | Gemini 2.5 Pro |
| Branch pattern | `autoresearch/<tag>` | `prompt-opt/<tag>` | `runner-opt/<tag>` |
| Stop condition | Manual | Plateau/cost | All games >= 50 |

## Project Structure

```
autoresearch-runner-game/
  strategy.json          The 10 AI parameters (only file the LLM edits)
  game_engine.py         Game simulation + AI player (read-only)
  evaluate.py            Evaluation harness: 20 seeds (read-only)
  server.py              HTTP server bridging browser to files/git/Gemini
  program.md             Agent instructions (Karpathy pattern)
  resources.md           Accumulated learnings from experiments
  results.tsv            Full experiment history
  last_run.json          Per-game death analysis
  index.html             Visual frontend with game playback + charts
  .env                   Gemini API key
  runner_game.py         V1 standalone evolutionary approach (no LLM)
  test_runner.py         16 automated tests
  docs/
    README.md            Detailed technical documentation
    development-journey.md  Full development story with human-AI collaboration
    v1-implementation.md    V1 evolutionary approach documentation
    v2-karpathy-framework.md  Karpathy framework mapping
```

## Documentation

- **[Technical Documentation](docs/README.md)**: Game physics, AI strategy parameters, decision logic, evaluation details
- **[Development Journey](docs/development-journey.md)**: Full story of building this, including the Gemini Flash plateau, Pro's breakthrough, and human-AI collaboration
- **[V1 Implementation](docs/v1-implementation.md)**: The initial evolutionary approach (random mutation, no LLM)
- **[V2 Karpathy Framework](docs/v2-karpathy-framework.md)**: How the framework maps to the original codebases

## Credits

- [Andrej Karpathy's autoresearch](https://github.com/karpathy/autoresearch) -- the framework pattern
- [prompt-optimizer](https://github.com/karpathy/autoresearch) -- reference implementation for prompt engineering
- Gemini 2.5 Pro -- the LLM agent that does the actual optimization
- Built with Claude Code (Anthropic) as the development AI assistant
