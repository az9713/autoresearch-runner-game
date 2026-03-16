"""
Server for the Self-Improving Runner Game.
Bridges the browser UI to the real Karpathy framework:
  - Reads/writes strategy.json
  - Runs evaluate.py
  - Executes git commit / git reset
  - Reads last_run.json, resources.md, results.tsv

Usage:
    python server.py
    Then open http://localhost:8000 in your browser.
"""

import http.server
import json
import subprocess
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

PORT = 8000
ROOT = Path(__file__).parent


# =============================================================================
# Gemini LLM Reasoning -- the brain of the Karpathy framework
# =============================================================================

GEMINI_MODEL = os.getenv("MODEL", "gemini-2.5-flash")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

REASONING_PROMPT = """You are an autonomous researcher optimizing a runner game AI strategy.
You analyze game failure data and propose targeted parameter changes.

## Game Physics
- Side-scrolling runner, auto-runs at increasing speed (base 5.0 + 0.02 per score, cap +2.5)
- Jump power: 13.0, gravity: -0.8/tick^2, peak height ~99 units, duration ~32 ticks
- Double jump: 0.75x power, once per jump arc
- Player height: 40 standing, 20 ducking
- Three obstacle types:
  - ground (height 20-50): must JUMP over
  - low (height 15-28): must JUMP over
  - high (clearance 22-30): must DUCK under (player shrinks to 20)
- Progressive difficulty: obstacles get taller, gaps shrink, speed sections appear

## Strategy Parameters (what you can tune)
- jump_trigger (30-200): base distance to trigger jump. adjusted = jump_trigger + speed * speed_factor
- jump_max_dist (60-300): max distance to consider jumping
- emergency_dist (5-50): last-resort emergency jump distance
- speed_factor (0-8): how much speed affects jump timing
- dj_height_frac (0.3-1.5): double jump if player_y < obstacle_height * this
- dj_min_ticks (2-15): min ticks after jump before double jump allowed
- dj_max_dist (30-150): max obstacle distance for double jump
- duck_trigger (40-200): base distance to start ducking. adjusted = duck_trigger + speed * duck_speed_factor
- duck_release (-60-0): distance to stop ducking (negative = behind player)
- duck_speed_factor (0-5): how much speed affects duck timing

## Your Task
Given the current strategy, death analysis, and past learnings:
1. Analyze the death patterns -- what obstacle type kills most, player state at death, speed
2. Reason about which parameters need adjustment and WHY (cite physics)
3. Propose new parameter values

## Response Format
You MUST respond with valid JSON only, no markdown, no explanation outside JSON:
{
  "analysis": "Brief analysis of death patterns (1-2 sentences)",
  "hypothesis": "What you're changing and why (1-2 sentences)",
  "parameters": {
    "jump_trigger": <number>,
    "jump_max_dist": <number>,
    "emergency_dist": <number>,
    "speed_factor": <number>,
    "dj_height_frac": <number>,
    "dj_min_ticks": <number>,
    "dj_max_dist": <number>,
    "duck_trigger": <number>,
    "duck_release": <number>,
    "duck_speed_factor": <number>
  }
}

Only change parameters that your analysis suggests need adjustment. Keep others at their current values.
Make targeted changes, not random ones. Change 1-4 parameters per experiment."""


def call_gemini(current_strategy, last_run, resources):
    """Call Gemini to analyze failures and propose strategy changes."""
    from google import genai

    client = genai.Client(api_key=GOOGLE_API_KEY)

    user_msg = f"""## Current Strategy
{json.dumps(current_strategy, indent=2)}

## Death Analysis (from last evaluation)
Scores: {last_run.get('scores', [])}
Mean: {last_run.get('mean_score', 0)}, Min: {last_run.get('min_score', 0)}, Max: {last_run.get('max_score', 0)}
Deaths by type: {last_run.get('death_by_type', {})}

Worst 5 deaths:
"""
    for d in last_run.get('worst_5_deaths', [])[:5]:
        user_msg += f"  seed={d['seed']} score={d['score']} type={d['obstacle_type']} "
        user_msg += f"height={d['obstacle_height']} player_y={d['player_y_at_death']} "
        user_msg += f"{'jumping' if d['was_jumping'] else 'ducking' if d['was_ducking'] else 'standing'} "
        user_msg += f"speed={d['speed_at_death']}\n"

    user_msg += f"\n## Past Learnings\n{resources}\n"
    user_msg += "\nPropose improved parameters. Respond with JSON only."

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_msg,
        config=genai.types.GenerateContentConfig(
            system_instruction=REASONING_PROMPT,
            temperature=0.7,
        ),
    )

    raw_response = response.text or ""
    # Strip markdown fences if present
    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    parsed = json.loads(text)
    # Attach the prompts and raw response for logging
    parsed['_system_prompt'] = REASONING_PROMPT
    parsed['_user_prompt'] = user_msg
    parsed['_raw_response'] = raw_response
    parsed['_model'] = GEMINI_MODEL
    return parsed


def run_cmd(cmd, timeout=120):
    """Run a shell command and return (stdout, stderr, returncode)."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=str(ROOT)
        )
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "Timeout", 1


def read_file(name):
    """Read a file from the project root."""
    path = ROOT / name
    if path.exists():
        return path.read_text(encoding='utf-8')
    return None


def write_file(name, content):
    """Write a file to the project root."""
    path = ROOT / name
    path.write_text(content, encoding='utf-8')


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/api/strategy':
            data = read_file('strategy.json')
            if data:
                self.json_response(200, json.loads(data))
            else:
                self.json_response(404, {'error': 'strategy.json not found'})

        elif path == '/api/last_run':
            data = read_file('last_run.json')
            if data:
                self.json_response(200, json.loads(data))
            else:
                self.json_response(404, {'error': 'last_run.json not found'})

        elif path == '/api/resources':
            data = read_file('resources.md')
            self.json_response(200, {'content': data or ''})

        elif path == '/api/results':
            data = read_file('results.tsv')
            self.json_response(200, {'content': data or ''})

        elif path == '/api/git/log':
            out, err, code = run_cmd('git --no-pager log --oneline -20')
            self.json_response(200, {'log': out, 'error': err if code else ''})

        elif path == '/api/git/branch':
            out, err, code = run_cmd('git --no-pager branch')
            self.json_response(200, {'branches': out, 'error': err if code else ''})

        elif path == '/api/git/status':
            out, err, code = run_cmd('git --no-pager status --short')
            self.json_response(200, {'status': out, 'error': err if code else ''})

        else:
            # Serve static files
            super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.read_body()

        if path == '/api/strategy':
            # Write strategy.json
            try:
                params = json.loads(body) if isinstance(body, str) else body
                write_file('strategy.json', json.dumps(params, indent=4) + '\n')
                self.json_response(200, {'ok': True})
            except Exception as e:
                self.json_response(400, {'error': str(e)})

        elif path == '/api/evaluate':
            # Run python evaluate.py
            out, err, code = run_cmd(f'{sys.executable} evaluate.py', timeout=60)
            # Read last_run.json for detailed results
            last_run = read_file('last_run.json')
            results = json.loads(last_run) if last_run else {}
            # Parse greppable output
            metrics = {}
            for line in out.split('\n'):
                if ':' in line and not line.startswith('-'):
                    key, _, val = line.partition(':')
                    key = key.strip()
                    val = val.strip()
                    if key in ('mean_score', 'min_score', 'max_score', 'pct_above_50',
                               'extended_mean', 'extended_min'):
                        try:
                            metrics[key] = float(val)
                        except ValueError:
                            metrics[key] = val
                    elif key in ('all_above_50', 'extended_all50'):
                        metrics[key] = val == 'True'
                    elif key in ('games_played', 'parse_errors', 'target'):
                        try:
                            metrics[key] = int(val)
                        except ValueError:
                            metrics[key] = val
            self.json_response(200, {
                'metrics': metrics,
                'details': results,
                'stdout': out,
                'stderr': err,
                'returncode': code,
            })

        elif path == '/api/git/commit':
            # git add strategy.json && git commit -m "message"
            data = json.loads(body) if isinstance(body, str) else body
            msg = data.get('message', 'experiment')
            run_cmd('git add strategy.json')
            out, err, code = run_cmd(f'git commit -m "{msg}"')
            # Get short hash
            hash_out, _, _ = run_cmd('git --no-pager log --oneline -1')
            short_hash = hash_out.strip().split(' ')[0] if hash_out.strip() else ''
            self.json_response(200, {
                'ok': code == 0,
                'hash': short_hash,
                'output': out,
                'error': err,
            })

        elif path == '/api/git/reset':
            # Revert only strategy.json to previous commit (not all files)
            out, err, code = run_cmd('git checkout HEAD~1 -- strategy.json')
            if code == 0:
                out2, err2, code2 = run_cmd('git reset HEAD~1')
                out += out2; err += err2
            self.json_response(200, {
                'ok': code == 0,
                'output': out,
                'error': err,
            })

        elif path == '/api/git/branch/create':
            data = json.loads(body) if isinstance(body, str) else body
            name = data.get('name', 'runner-opt/run1')
            out, err, code = run_cmd(f'git checkout -b {name}')
            self.json_response(200, {
                'ok': code == 0,
                'output': out,
                'error': err,
            })

        elif path == '/api/resources':
            data = json.loads(body) if isinstance(body, str) else body
            write_file('resources.md', data.get('content', ''))
            self.json_response(200, {'ok': True})

        elif path == '/api/reason':
            # Call Gemini to analyze failures and propose strategy changes
            data = json.loads(body) if isinstance(body, str) else body
            current_strategy = data.get('strategy', {})
            last_run_data = data.get('last_run', {})
            resources_text = data.get('resources', '')
            try:
                result = call_gemini(current_strategy, last_run_data, resources_text)
                self.json_response(200, {
                    'ok': True,
                    'analysis': result.get('analysis', ''),
                    'hypothesis': result.get('hypothesis', ''),
                    'parameters': result.get('parameters', current_strategy),
                    'system_prompt': result.get('_system_prompt', ''),
                    'user_prompt': result.get('_user_prompt', ''),
                    'raw_response': result.get('_raw_response', ''),
                    'model': result.get('_model', ''),
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.json_response(500, {
                    'ok': False,
                    'error': str(e),
                })

        elif path == '/api/results/append':
            data = json.loads(body) if isinstance(body, str) else body
            line = data.get('line', '')
            current = read_file('results.tsv') or ''
            if not current.strip():
                current = 'commit\tmean_score\tmin_score\tstatus\tdescription\n'
            write_file('results.tsv', current.rstrip('\n') + '\n' + line + '\n')
            self.json_response(200, {'ok': True})

        else:
            self.json_response(404, {'error': 'Unknown endpoint'})

    def read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length:
            return self.rfile.read(length).decode('utf-8')
        return ''

    def json_response(self, code, data):
        body = json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        # Quieter logging -- only show API calls
        msg = format % args
        if '/api/' in msg:
            print(f'  {msg}')


if __name__ == '__main__':
    # Reset strategy.json to weak baseline for fresh evolution
    weak_baseline = {
        "jump_trigger": 45.0,
        "jump_max_dist": 140.0,
        "emergency_dist": 8.0,
        "speed_factor": 0.5,
        "dj_height_frac": 0.5,
        "dj_min_ticks": 10,
        "dj_max_dist": 40.0,
        "duck_trigger": 40.0,
        "duck_release": -10.0,
        "duck_speed_factor": 0.3
    }
    write_file('strategy.json', json.dumps(weak_baseline, indent=4) + '\n')
    print(f"Reset strategy.json to weak baseline")
    print(f"Starting server at http://localhost:{PORT}")
    print(f"Open this URL in your browser and click Start Evolution")
    print(f"Press Ctrl+C to stop\n")

    server = http.server.HTTPServer(('', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
