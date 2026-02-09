"""
Sifter — human A/B comparison scoring tool.

Usage:
    python sifter.py <jobname> [--port PORT]

Reads:  jobs/<jobname>/input.jsonl   — one {"a": ..., "b": ...} per line
Writes: jobs/<jobname>/output.jsonl  — mirrors input with "score" field added
"""

import argparse
import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

# --- State ---

pairs: list[dict] = []
scores: list[int | None] = []
job_dir: Path = Path()


def load_input(path: Path):
    global pairs, scores
    with open(path) as f:
        pairs = [json.loads(line) for line in f if line.strip()]
    scores = [None] * len(pairs)


def load_existing_output(path: Path):
    """Resume from previous session."""
    if not path.exists():
        return
    with open(path) as f:
        for i, line in enumerate(f):
            if i >= len(scores):
                break
            obj = json.loads(line)
            scores[i] = obj.get("score")


def flush_output(path: Path):
    with open(path, "w") as f:
        for pair, score in zip(pairs, scores):
            f.write(json.dumps({**pair, "score": score}) + "\n")


# --- App ---

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.get("/api/status")
def status():
    scored = sum(1 for s in scores if s is not None)
    return {"total": len(pairs), "scored": scored}


@app.get("/api/pair/{idx}")
def get_pair(idx: int):
    if idx < 0 or idx >= len(pairs):
        return JSONResponse({"error": "out of range"}, 404)
    return {"index": idx, **pairs[idx], "score": scores[idx]}


@app.post("/api/pair/{idx}/score")
def set_score(idx: int, body: dict):
    if idx < 0 or idx >= len(pairs):
        return JSONResponse({"error": "out of range"}, 404)
    s = body.get("score")
    if s not in (1, 2, 3, 4, 5):
        return JSONResponse({"error": "score must be 1-5"}, 400)
    scores[idx] = s
    flush_output(job_dir / "output.jsonl")
    return {"ok": True}


# --- HTML ---

HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Sifter</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: system-ui, sans-serif;
    background: #111; color: #eee;
    height: 100vh; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    user-select: none;
  }
  #progress { position: fixed; top: 16px; font-size: 14px; color: #888; }
  #arena {
    display: flex; align-items: center; justify-content: center; gap: 80px;
    flex: 1;
  }
  .specimen {
    font-size: 220px; font-family: monospace;
    min-width: 260px; text-align: center;
    line-height: 1.1;
  }
  .label { font-size: 14px; color: #666; text-align: center; margin-bottom: 8px; }
  #vs { font-size: 24px; color: #444; }
  #scorebar {
    display: flex; gap: 12px; margin-bottom: 60px;
  }
  .score-btn {
    width: 56px; height: 56px; border-radius: 8px;
    border: 2px solid #333; background: transparent; color: #aaa;
    font-size: 22px; cursor: pointer; transition: all 0.1s;
  }
  .score-btn:hover { border-color: #666; color: #fff; }
  .score-btn.active { border-color: #4af; color: #4af; background: #4af1; }
  #nav-hint {
    position: fixed; bottom: 16px; font-size: 13px; color: #555;
  }
  #arrow-left, #arrow-right {
    position: fixed; top: 50%; font-size: 32px; color: #333;
    cursor: pointer; padding: 20px;
  }
  #arrow-left:hover, #arrow-right:hover { color: #888; }
  #arrow-left { left: 16px; }
  #arrow-right { right: 16px; }
</style>
</head>
<body>
  <div id="progress"></div>
  <div id="arrow-left">&#9664;</div>
  <div id="arrow-right">&#9654;</div>
  <div id="arena">
    <div>
      <div class="label">A</div>
      <div class="specimen" id="specimen-a"></div>
    </div>
    <div id="vs">vs</div>
    <div>
      <div class="label">B</div>
      <div class="specimen" id="specimen-b"></div>
    </div>
  </div>
  <div id="scorebar">
    <button class="score-btn" data-s="1">1</button>
    <button class="score-btn" data-s="2">2</button>
    <button class="score-btn" data-s="3">3</button>
    <button class="score-btn" data-s="4">4</button>
    <button class="score-btn" data-s="5">5</button>
  </div>
  <div id="nav-hint">&#8592; &#8594; navigate &nbsp;&middot;&nbsp; 1-5 score</div>

<script>
let idx = 0;
let total = 0;

async function loadPair() {
  const r = await fetch(`/api/pair/${idx}`);
  if (!r.ok) return;
  const d = await r.json();
  document.getElementById('specimen-a').textContent = d.a;
  document.getElementById('specimen-b').textContent = d.b;
  document.querySelectorAll('.score-btn').forEach(b => {
    b.classList.toggle('active', parseInt(b.dataset.s) === d.score);
  });
  updateProgress();
}

async function updateProgress() {
  const r = await fetch('/api/status');
  const d = await r.json();
  total = d.total;
  document.getElementById('progress').textContent =
    `${idx + 1} / ${d.total}  (${d.scored} scored)`;
}

async function submitScore(s) {
  await fetch(`/api/pair/${idx}/score`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({score: s})
  });
  document.querySelectorAll('.score-btn').forEach(b => {
    b.classList.toggle('active', parseInt(b.dataset.s) === s);
  });
  // auto-advance
  if (idx < total - 1) { idx++; loadPair(); }
  else { updateProgress(); }
}

function nav(dir) {
  const next = idx + dir;
  if (next >= 0 && next < total) { idx = next; loadPair(); }
}

document.addEventListener('keydown', e => {
  if (e.key === 'ArrowLeft')  nav(-1);
  if (e.key === 'ArrowRight') nav(1);
  const n = parseInt(e.key);
  if (n >= 1 && n <= 5) submitScore(n);
});

document.querySelectorAll('.score-btn').forEach(b => {
  b.addEventListener('click', () => submitScore(parseInt(b.dataset.s)));
});
document.getElementById('arrow-left').addEventListener('click', () => nav(-1));
document.getElementById('arrow-right').addEventListener('click', () => nav(1));

// Start from first unscored
(async () => {
  const st = await (await fetch('/api/status')).json();
  total = st.total;
  // find first unscored
  for (let i = 0; i < total; i++) {
    const r = await fetch(`/api/pair/${i}`);
    const d = await r.json();
    if (d.score === null) { idx = i; break; }
  }
  loadPair();
})();
</script>
</body>
</html>
"""

# --- CLI ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sifter — A/B scoring tool")
    parser.add_argument(
        "job", help="Job name (reads from jobs/<job>/input.jsonl)")
    parser.add_argument("--port", type=int, default=9413)
    args = parser.parse_args()

    job_dir = Path(__file__).parent / "jobs" / args.job
    input_path = job_dir / "input.jsonl"

    if not input_path.exists():
        print(f"Not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    load_input(input_path)
    load_existing_output(job_dir / "output.jsonl")
    print(
        f"Loaded {len(pairs)} pairs, {sum(1 for s in scores if s is not None)} already scored")

    uvicorn.run(app, host="0.0.0.0", port=args.port)
