"""
Sifter — human A/B comparison scoring tool.

Usage:
    python sifter.py <jobname> [--port PORT]

Reads:  jobs/<jobname>/input.jsonl   — one {"a": ..., "b": ..., "font": ...} per line
Writes: jobs/<jobname>/output.jsonl  — mirrors input with "score" field added
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

# --- State ---

pairs: list[dict] = []
scores: list[int | None] = []
fonts: set[str] = set()
job_dir: Path = Path()


def load_input(path: Path):
    global pairs, scores, fonts
    with open(path) as f:
        pairs = [json.loads(line) for line in f if line.strip()]
    scores = [None] * len(pairs)
    fonts = {p["font"] for p in pairs if p.get("font")}


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


def validate_fonts(font_set: set[str]):
    """Fetch each unique Google Font before server starts. Exit on failure."""
    if not font_set:
        return
    print(f"Validating {len(font_set)} Google Font(s)...")
    for name in sorted(font_set):
        url = "https://fonts.googleapis.com/css2?family=" + \
            name.replace(" ", "+") + "&display=swap"
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "Mozilla/5.0")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    print(
                        f"FAIL: '{name}' returned HTTP {resp.status}", file=sys.stderr)
                    sys.exit(1)
            print(f"  OK: {name}")
        except urllib.error.HTTPError as e:
            print(
                f"FAIL: font '{name}' not found (HTTP {e.code})", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(
                f"FAIL: could not fetch font '{name}': {e.reason}", file=sys.stderr)
            sys.exit(1)


# --- App ---

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
def index():
    font_links = "\n".join(
        f'<link href="https://fonts.googleapis.com/css2?family={f.replace(" ", "+")}&display=swap" rel="stylesheet">'
        for f in sorted(fonts)
    )
    return HTML.replace("<!-- FONT_LINKS -->", font_links)


@app.get("/api/status")
def status():
    scored = sum(1 for s in scores if s is not None)
    return {"total": len(pairs), "scored": scored}


@app.get("/api/pair/{idx}")
def get_pair(idx: int):
    if idx < 0 or idx >= len(pairs):
        return JSONResponse({"error": "out of range"}, 404)
    return {"index": idx, **pairs[idx], "score": scores[idx]}


@app.get("/api/first-unscored")
def first_unscored():
    for i, s in enumerate(scores):
        if s is None:
            return {"index": i}
    return {"index": 0}


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
<!-- FONT_LINKS -->
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
    position: fixed; top: 50%; transform: translateY(-50%);
    font-size: 32px; color: #333;
    cursor: pointer; padding: 20px;
    z-index: 10;
  }
  #arrow-left:hover, #arrow-right:hover { color: #888; }
  #arrow-left { left: 16px; }
  #arrow-right { right: 16px; }
</style>
</head>
<body>
  <div id="progress"></div>
  <div id="font-label" style="position:fixed; top:36px; font-size:13px; color:#555;"></div>
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
  <div id="arrow-left">&#9664;</div>
  <div id="arrow-right">&#9654;</div>

<script>
let IDX = 0;
let TOTAL = 0;
let BUSY = false;

const $a     = document.getElementById('specimen-a');
const $b     = document.getElementById('specimen-b');
const $font  = document.getElementById('font-label');
const $prog  = document.getElementById('progress');
const $btns  = document.querySelectorAll('.score-btn');

async function render() {
  BUSY = true;
  try {
    const [pair, st] = await Promise.all([
      fetch('/api/pair/' + IDX).then(r => r.json()),
      fetch('/api/status').then(r => r.json()),
    ]);
    TOTAL = st.total;
    const font = pair.font ? '"' + pair.font + '", monospace' : 'monospace';
    $a.textContent = pair.a;
    $a.style.fontFamily = font;
    $b.textContent = pair.b;
    $b.style.fontFamily = font;
    $font.textContent = pair.font || 'default';
    $prog.textContent = (IDX + 1) + ' / ' + st.total + '  (' + st.scored + ' scored)';
    $btns.forEach(function(b) {
      b.classList.toggle('active', Number(b.dataset.s) === pair.score);
    });
  } finally {
    BUSY = false;
  }
}

async function score(val) {
  if (BUSY) return;
  BUSY = true;
  try {
    await fetch('/api/pair/' + IDX + '/score', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({score: val})
    });
    $btns.forEach(function(b) {
      b.classList.toggle('active', Number(b.dataset.s) === val);
    });
    var st = await fetch('/api/status').then(function(r) { return r.json(); });
    TOTAL = st.total;
    $prog.textContent = (IDX + 1) + ' / ' + st.total + '  (' + st.scored + ' scored)';
  } finally {
    BUSY = false;
  }
}

function go(dir) {
  if (BUSY) return;
  var next = IDX + dir;
  if (next < 0 || next >= TOTAL) return;
  IDX = next;
  render();
}

// --- event listeners ---
document.addEventListener('keydown', function(e) {
  if (e.key === 'ArrowLeft')  { e.preventDefault(); go(-1); return; }
  if (e.key === 'ArrowRight') { e.preventDefault(); go(1);  return; }
  var n = Number(e.key);
  if (n >= 1 && n <= 5) { e.preventDefault(); score(n); }
});

$btns.forEach(function(b) {
  b.addEventListener('click', function() { score(Number(b.dataset.s)); });
});
document.getElementById('arrow-left').addEventListener('click', function() { go(-1); });
document.getElementById('arrow-right').addEventListener('click', function() { go(1); });

// --- init ---
fetch('/api/first-unscored')
  .then(function(r) { return r.json(); })
  .then(function(d) { IDX = d.index; return fetch('/api/status'); })
  .then(function(r) { return r.json(); })
  .then(function(d) { TOTAL = d.total; render(); });
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
    validate_fonts(fonts)
    load_existing_output(job_dir / "output.jsonl")
    print(
        f"Loaded {len(pairs)} pairs, {sum(1 for s in scores if s is not None)} already scored")

    uvicorn.run(app, host="0.0.0.0", port=args.port)
