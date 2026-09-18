import asyncio
import json
import time
import uuid

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

import db
from game import DIRECTIONS, Game

app = FastAPI(title="uxuxxshak")

active_matches = {}
queue = []


class Match:
    def __init__(self, match_id, red_bot_id, blue_bot_id):
        self.id = match_id
        self.game = Game()
        self.red_bot = red_bot_id
        self.blue_bot = blue_bot_id
        self.red_name = db.get_bot_name(red_bot_id)
        self.blue_name = db.get_bot_name(blue_bot_id)
        self.red_move = None
        self.blue_move = None
        self.last_step = time.time()
        self.saved = False


def finalize_match(m):
    winner = m.game.winner
    winner_bot = m.red_bot if winner == "red" else m.blue_bot
    loser_bot = m.blue_bot if winner == "red" else m.red_bot
    db.update_elo(winner_bot, +20, True)
    db.update_elo(loser_bot, -30, False)
    db.save_match(m.id, m.red_bot, m.blue_bot, winner)
    db.save_replay(m.id, json.dumps(m.game.history))
    print(f"[MATCH {m.id}] winner={winner} tick={m.game.tick}")


async def worker():
    while True:
        now = time.time()
        for mid, m in list(active_matches.items()):
            if m.game.finished:
                continue
            if now - m.last_step >= 0.1:
                m.last_step = now
                red_dir = m.red_move or m.game.red.direction
                blue_dir = m.blue_move or m.game.blue.direction
                m.game.step(red_dir, blue_dir)
                m.red_move = None
                m.blue_move = None
                if m.game.finished and not m.saved:
                    m.saved = True
                    finalize_match(m)
        await asyncio.sleep(0.02)


def try_matchmake():
    if len(queue) >= 2:
        red = queue.pop(0)
        blue = queue.pop(0)
        mid = str(uuid.uuid4())
        active_matches[mid] = Match(mid, red, blue)
        print(f"[MATCHMAKER] new match {mid}: {red} vs {blue}")
        return mid
    return None


@app.on_event("startup")
async def startup():
    db.init_db()
    asyncio.create_task(worker())


class RegisterBody(BaseModel):
    name: str


class MoveBody(BaseModel):
    direction: str


def auth(authorization: Optional[str]):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing token")
    token = authorization.split(" ", 1)[1]
    bot = db.get_bot_by_token(token)
    if not bot:
        raise HTTPException(401, "invalid token")
    return bot


@app.get("/")
def root():
    return {
        "status": "ok",
        "queue": len(queue),
        "active_matches": len(active_matches),
    }


@app.post("/register")
def register(body: RegisterBody):
    res = db.create_bot(body.name)
    if not res:
        raise HTTPException(400, "name taken")
    return res


@app.post("/queue/join")
def queue_join(authorization: Optional[str] = Header(None)):
    bot = auth(authorization)
    bot_id = bot["bot_id"]
    for m in active_matches.values():
        if not m.game.finished and bot_id in (m.red_bot, m.blue_bot):
            return {"status": "already_in_match", "match_id": m.id}
    if bot_id in queue:
        return {"status": "already_queued", "position": queue.index(bot_id) + 1}
    queue.append(bot_id)
    mid = try_matchmake()
    if mid:
        return {"status": "matched", "match_id": mid}
    return {"status": "queued", "position": len(queue)}


@app.get("/match/{match_id}/state")
def get_state(match_id: str):
    m = active_matches.get(match_id)
    if not m:
        raise HTTPException(404, "match not active")
    st = m.game.state()
    st["red_name"] = m.red_name
    st["blue_name"] = m.blue_name
    return st


@app.post("/match/{match_id}/move")
def make_move(
    match_id: str,
    body: MoveBody,
    authorization: Optional[str] = Header(None),
):
    bot = auth(authorization)
    m = active_matches.get(match_id)
    if not m:
        raise HTTPException(404, "match not found")
    if m.game.finished:
        raise HTTPException(400, "match finished")
    if body.direction not in DIRECTIONS:
        raise HTTPException(400, "invalid direction")
    if m.red_bot == bot["bot_id"]:
        m.red_move = body.direction
    elif m.blue_bot == bot["bot_id"]:
        m.blue_move = body.direction
    else:
        raise HTTPException(403, "not your match")
    return {"accepted": True, "tick": m.game.tick}


@app.get("/leaderboard")
def leaderboard(top: int = 10):
    return db.get_leaderboard(top)


@app.get("/match/{match_id}/replay")
def get_replay(match_id: str):
    data = db.get_replay(match_id)
    if not data:
        raise HTTPException(404, "replay not found")
    return json.loads(data)


BASE_STYLE = """
<style>
body { background:#1a1a1a; color:#eee; font-family:monospace; margin:0; padding:16px; }
a { color:#7CB342; }
h1 { color:#7CB342; font-size:18px; }
canvas { image-rendering: pixelated; display:block; margin:8px 0;
         border:2px solid #558B2F; max-width:100%; height:auto; }
.row { padding:6px 0; border-bottom:1px solid #333; }
.red { color:#E53935; } .blue { color:#2196F3; }
.btn { display:inline-block; padding:8px 14px; background:#7CB342; color:#000;
       text-decoration:none; margin:4px 4px 4px 0; font-weight:bold; }
</style>
"""

JS_CANVAS = """
<script>
const CELL = 15;
const W = 30, H = 30;
function drawState(state, canvas) {
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = '#7CB342';
  ctx.fillRect(0, 0, W*CELL, H*CELL);
  ctx.strokeStyle = '#558B2F';
  ctx.lineWidth = 1;
  for (let i = 0; i <= W; i++) {
    ctx.beginPath(); ctx.moveTo(i*CELL, 0); ctx.lineTo(i*CELL, H*CELL); ctx.stroke();
  }
  for (let j = 0; j <= H; j++) {
    ctx.beginPath(); ctx.moveTo(0, j*CELL); ctx.lineTo(W*CELL, j*CELL); ctx.stroke();
  }
  if (state.apple) {
    const [x, y] = state.apple;
    ctx.fillStyle = '#FF1744';
    ctx.fillRect(x*CELL + 2, y*CELL + 2, CELL - 4, CELL - 4);
  }
  drawSnake(ctx, state.red.body, '#C62828');
  drawSnake(ctx, state.blue.body, '#1565C0');

  function drawSnake(ctx, body, color) {
    if (!body || body.length === 0) return;
    ctx.fillStyle = color;
    for (let i = 1; i < body.length; i++) {
      const [x, y] = body[i];
      ctx.fillRect(x*CELL, y*CELL, CELL, CELL);
    }
    const [hx, hy] = body[0];
    ctx.fillRect(hx*CELL, hy*CELL, CELL, CELL);
    let dx = 0, dy = 0;
    if (body.length > 1) {
      dx = hx - body[1][0];
      dy = hy - body[1][1];
    }
    const eye = 3;
    let ex = hx*CELL + CELL/2 - eye/2;
    let ey = hy*CELL + CELL/2 - eye/2;
    if (dx > 0) ex = hx*CELL + CELL - eye - 2;
    else if (dx < 0) ex = hx*CELL + 2;
    if (dy > 0) ey = hy*CELL + CELL - eye - 2;
    else if (dy < 0) ey = hy*CELL + 2;
    ctx.fillStyle = '#000';
    ctx.fillRect(ex, ey, eye, eye);
  }
}
</script>
"""


@app.get("/matches", response_class=HTMLResponse)
def matches_page():
    active = []
    for mid, m in active_matches.items():
        if not m.game.finished:
            active.append(
                f'<div class="row">[LIVE] <a href="/watch/{mid}">{m.red_name}</a>'
                f' vs <a href="/watch/{mid}">{m.blue_name}</a></div>'
            )
    finished = db.get_recent_matches(20)
    finished_html = "".join(
        f'<div class="row">'
        f'<a href="/watch/{m["id"]}">{m["red_name"]}</a> vs <a href="/watch/{m["id"]}">{m["blue_name"]}</a>'
        f' - <span class="{"red" if m["winner"]=="red" else "blue"}">победил {m["winner"]}</span>'
        f' <a href="/replay/{m["id"]}">[реплей]</a>'
        f"</div>"
        for m in finished
    )
    return f"""<html><head><title>uxuxxshak</title>{BASE_STYLE}</head><body>
<h1>uxuxxshak</h1>
<p><a class="btn" href="/">Статус</a><a class="btn" href="/leaderboard">Топы</a><a class="btn" href="/matches">Матчи</a></p>
<h2 style="color:#7CB342;">Активные матчи ({len(active)})</h2>
{''.join(active) or '<div class="row">пусто</div>'}
<h2 style="color:#7CB342;">Последние матчи</h2>
{finished_html or '<div class="row">пусто</div>'}
</body></html>"""


@app.get("/watch/{match_id}", response_class=HTMLResponse)
def watch_page(match_id: str):
    return f"""<html><head><title>Матч {match_id[:8]}</title>{BASE_STYLE}</head><body>
<h1>Матч {match_id[:8]}</h1>
<canvas id="c" width="{30*15}" height="{30*15}"></canvas>
<div id="info">Загрузка...</div>
<p><a class="btn" href="/matches">К списку</a></p>
{JS_CANVAS}
<script>
const canvas = document.getElementById('c');
const info = document.getElementById('info');
async function tick() {{
  try {{
    const r = await fetch('/match/{match_id}/state');
    if (r.ok) {{
      const st = await r.json();
      drawState(st, canvas);
      info.innerHTML = `<span class="red">${{st.red_name}}</span> vs <span class="blue">${{st.blue_name}}</span> tick ${{st.tick}}` +
        (st.finished ? ` победил ${{st.winner}}` : '');
      if (st.finished) return;
    }}
  }} catch(e) {{}}
  setTimeout(tick, 150);
}}
tick();
</script>
</body></html>"""


@app.get("/replay/{match_id}", response_class=HTMLResponse)
def replay_page(match_id: str):
    return f"""<html><head><title>Реплей {match_id[:8]}</title>{BASE_STYLE}</head><body>
<h1>Реплей {match_id[:8]}</h1>
<canvas id="c" width="{30*15}" height="{30*15}"></canvas>
<div id="info">Загрузка...</div>
<p><a class="btn" href="/matches">К списку</a></p>
{JS_CANVAS}
<script>
const canvas = document.getElementById('c');
const info = document.getElementById('info');
async function play() {{
  const r = await fetch('/match/{match_id}/replay');
  if (!r.ok) {{ info.textContent = 'Реплей не найден'; return; }}
  const frames = await r.json();
  for (let i = 0; i < frames.length; i++) {{
    const st = frames[i];
    drawState(st, canvas);
    info.textContent = `Кадр ${{i+1}} / ${{frames.length}} tick ${{st.tick}}` +
      (st.finished ? ` победил ${{st.winner}}` : '');
    await new Promise(res => setTimeout(res, 100));
  }}
}}
play();
</script>
</body></html>"""
