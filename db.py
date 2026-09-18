import sqlite3
import time
import uuid

DB_PATH = "arena.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS bots (
        id TEXT PRIMARY KEY,
        name TEXT UNIQUE,
        token TEXT UNIQUE,
        elo INTEGER DEFAULT 1000,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        created_at INTEGER
    )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS matches (
        id TEXT PRIMARY KEY,
        red_bot TEXT,
        blue_bot TEXT,
        winner TEXT,
        created_at INTEGER
    )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS replays (
        match_id TEXT PRIMARY KEY,
        data TEXT
    )"""
    )
    conn.commit()
    conn.close()


def create_bot(name):
    bot_id = str(uuid.uuid4())
    token = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO bots (id, name, token, elo, created_at) VALUES (?, ?, ?, 1000, ?)",
            (bot_id, name, token, int(time.time())),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return None
    conn.close()
    return {"bot_id": bot_id, "token": token, "elo": 1000}


def get_bot_by_token(token):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, name, elo, wins, losses FROM bots WHERE token=?", (token,)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "bot_id": row[0],
        "name": row[1],
        "elo": row[2],
        "wins": row[3],
        "losses": row[4],
    }


def get_bot_name(bot_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM bots WHERE id=?", (bot_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "unknown"


def update_elo(bot_id, delta, won):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if won:
        c.execute(
            "UPDATE bots SET elo = elo + ?, wins = wins + 1 WHERE id=?",
            (delta, bot_id),
        )
    else:
        c.execute(
            "UPDATE bots SET elo = elo + ?, losses = losses + 1 WHERE id=?",
            (delta, bot_id),
        )
    conn.commit()
    conn.close()


def save_match(match_id, red_bot, blue_bot, winner):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO matches (id, red_bot, blue_bot, winner, created_at) VALUES (?, ?, ?, ?, ?)",
        (match_id, red_bot, blue_bot, winner, int(time.time())),
    )
    conn.commit()
    conn.close()


def save_replay(match_id, data_json):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO replays (match_id, data) VALUES (?, ?)",
        (match_id, data_json),
    )
    conn.commit()
    conn.close()


def get_replay(match_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT data FROM replays WHERE match_id=?", (match_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def get_leaderboard(limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT name, elo, wins, losses FROM bots ORDER BY elo DESC LIMIT ?",
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"name": r[0], "elo": r[1], "wins": r[2], "losses": r[3]} for r in rows
    ]


def get_recent_matches(limit=20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """SELECT m.id, m.winner, m.created_at, rb.name, bb.name
        FROM matches m
        JOIN bots rb ON rb.id = m.red_bot
        JOIN bots bb ON bb.id = m.blue_bot
        ORDER BY m.created_at DESC LIMIT ?""",
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "winner": r[1],
            "created_at": r[2],
            "red_name": r[3],
            "blue_name": r[4],
        }
        for r in rows
    ]
