import json
import os
import random
import time
from collections import deque

import requests

BASE_URL = os.environ.get("ARENA_URL", "https://your-app.up.railway.app")
BOT_NAME = os.environ.get("BOT_NAME", "uxuxx1")
STATE_FILE = f"bot_credentials_{BOT_NAME}.json"
WEIGHTS_FILE = f"bot_weights_{BOT_NAME}.json"

DIRECTIONS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
WIDTH = 30
HEIGHT = 30


DEFAULT_WEIGHTS = {
    "space": 100.0,
    "apple": 5000.0,
    "apple_dist": 5.0,
    "enemy_far": 2.0,
    "enemy_close": 3.0,
    "aggression": 0.5,
    "safety_margin": 3,
}


def load_weights():
    if os.path.exists(WEIGHTS_FILE):
        with open(WEIGHTS_FILE) as f:
            w = json.load(f)
        for k, v in DEFAULT_WEIGHTS.items():
            w.setdefault(k, v)
        return w
    return dict(DEFAULT_WEIGHTS)


def save_weights(w):
    with open(WEIGHTS_FILE, "w") as f:
        json.dump(w, f)


def mutate(w, strength=0.15):
    new = {}
    for k, v in w.items():
        if k == "safety_margin":
            new[k] = max(1, min(8, v + random.choice([-1, 0, 1])))
        else:
            delta = v * random.uniform(-strength, strength)
            new[k] = max(0.01, v + delta)
    return new


def register():
    r = requests.post(f"{BASE_URL}/register", json={"name": BOT_NAME}, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"register failed: {r.status_code} {r.text}")
    return r.json()


def load_or_register():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    creds = register()
    with open(STATE_FILE, "w") as f:
        json.dump(creds, f)
    return creds


def api(method, path, token=None, body=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{BASE_URL}{path}"
    if method == "GET":
        return requests.get(url, headers=headers, timeout=10)
    return requests.post(url, headers=headers, json=body, timeout=10)


def neighbors(pos):
    x, y = pos
    for d, (dx, dy) in DIRECTIONS.items():
        yield d, (x + dx, y + dy)


def in_bounds(p):
    return 0 <= p[0] < WIDTH and 0 <= p[1] < HEIGHT


def flood_fill(start, blocked, limit=None):
    if start in blocked or not in_bounds(start):
        return 0
    seen = {start}
    q = deque([start])
    count = 0
    while q:
        x, y = q.popleft()
        count += 1
        if limit and count >= limit:
            return count
        for _, n in neighbors((x, y)):
            if n not in seen and n not in blocked and in_bounds(n):
                seen.add(n)
                q.append(n)
    return count


def bfs_path(start, goals, blocked):
    if not goals:
        return None
    goals = set(goals)
    q = deque([(start, [start])])
    seen = {start}
    while q:
        pos, path = q.popleft()
        if pos in goals:
            return path
        for _, n in neighbors(pos):
            if n in seen or not in_bounds(n):
                continue
            if n in blocked and n not in goals:
                continue
            seen.add(n)
            q.append((n, path + [n]))
    return None


def parse_state(state, my_color):
    enemy_color = "blue" if my_color == "red" else "red"
    me = [tuple(p) for p in state[my_color]["body"]]
    enemy = [tuple(p) for p in state[enemy_color]["body"]]
    apple = tuple(state["apple"]) if state.get("apple") else None
    return me, enemy, apple


def choose_move(state, my_color, w):
    me, enemy, apple = parse_state(state, my_color)
    head = me[0]
    my_len = len(me)
    enemy_len = len(enemy)
    enemy_head = enemy[0]

    safe_moves = []
    for d, n in neighbors(head):
        if not in_bounds(n):
            continue
        if n in me[1:]:
            continue
        if n in enemy[:-1]:
            continue
        if n == enemy_head and my_len <= enemy_len:
            continue
        safe_moves.append((d, n))

    if not safe_moves:
        return random.choice(list(DIRECTIONS.keys()))

    scored = []
    for d, n in safe_moves:
        blocked = (set(me) | set(enemy)) - {n}
        if apple and n == apple:
            blocked.discard(apple)
        space = flood_fill(n, blocked, limit=WIDTH * HEIGHT)
        if space < my_len + w["safety_margin"]:
            continue
        score = space * w["space"]
        if apple and n == apple:
            score += w["apple"]
        if apple:
            dist = abs(n[0] - apple[0]) + abs(n[1] - apple[1])
            score -= dist * w["apple_dist"]
        dist_enemy = abs(n[0] - enemy_head[0]) + abs(n[1] - enemy_head[1])
        if my_len > enemy_len:
            score -= dist_enemy * w["enemy_close"] * w["aggression"]
        else:
            score += dist_enemy * w["enemy_far"]
        scored.append((score, d))

    if not scored:
        for d, n in safe_moves:
            blocked = (set(me) | set(enemy)) - {n}
            space = flood_fill(n, blocked)
            scored.append((space, d))

    if apple:
        blocked = set(me) | set(enemy[:-1])
        path = bfs_path(head, [apple], blocked)
        if path and len(path) > 1:
            next_cell = path[1]
            for d, n in safe_moves:
                if n == next_cell:
                    blocked_after = (set(me) | set(enemy)) - {n}
                    if apple and n == apple:
                        blocked_after.discard(apple)
                    space = flood_fill(n, blocked_after)
                    if space >= my_len + w["safety_margin"]:
                        return d

    scored.sort(reverse=True)
    return scored[0][1]


def play_once(creds, w):
    token = creds["token"]
    r = api("POST", "/queue/join", token=token)
    if r.status_code != 200:
        return None
    data = r.json()
    status = data.get("status")
    if status == "queued":
        while True:
            time.sleep(2)
            r = api("POST", "/queue/join", token=token)
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("status") in ("matched", "already_in_match"):
                break
    match_id = data.get("match_id")
    if not match_id:
        return None

    my_color = None
    last_sent = None
    result = None
    while True:
        r = api("GET", f"/match/{match_id}/state")
        if r.status_code != 200:
            return result
        st = r.json()
        if my_color is None:
            my_color = "red" if st.get("red_name") == BOT_NAME else "blue"
        if st.get("finished"):
            result = "win" if st.get("winner") == my_color else "loss"
            return result
        move = choose_move(st, my_color, w)
        if move != last_sent:
            api(
                "POST",
                f"/match/{match_id}/move",
                token=token,
                body={"direction": move},
            )
            last_sent = move
        time.sleep(0.08)


def main():
    creds = load_or_register()
    w = load_weights()
    print(f"{BOT_NAME} started, bot_id={creds['bot_id']}")
    while True:
        try:
            result = play_once(creds, w)
            if result == "loss":
                w = mutate(w)
                save_weights(w)
                print(f"{BOT_NAME}: loss, weights mutated")
            elif result == "win":
                save_weights(w)
                print(f"{BOT_NAME}: win, weights kept")
        except Exception as e:
            print(f"{BOT_NAME}: error {e}")
        time.sleep(2)


if __name__ == "__main__":
    main()
