from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "stramo_projects.db"


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS projects (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        navn TEXT    NOT NULL,
        dato TEXT    NOT NULL,
        data TEXT    NOT NULL
    )""")
    con.commit()
    return con


def lagre_prosjekt(navn: str, data: dict) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO projects (navn, dato, data) VALUES (?,?,?)",
            (navn or "Uten navn",
             datetime.today().strftime("%d.%m.%Y %H:%M"),
             json.dumps(data, ensure_ascii=False)),
        )
        return cur.lastrowid


def hent_alle_prosjekter() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, navn, dato FROM projects ORDER BY id DESC"
        ).fetchall()
    return [{"id": r[0], "navn": r[1], "dato": r[2]} for r in rows]


def hent_prosjekt(pid: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT data FROM projects WHERE id=?", (pid,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def slett_prosjekt(pid: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM projects WHERE id=?", (pid,))
        con.commit()


def oppdater_prosjekt(pid: int, navn: str, data: dict) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE projects SET navn=?, dato=?, data=? WHERE id=?",
            (navn,
             datetime.today().strftime("%d.%m.%Y %H:%M"),
             json.dumps(data, ensure_ascii=False),
             pid),
        )
        con.commit()
