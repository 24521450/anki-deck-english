"""Load oxford_full.jsonl into SQLite for queries.

Schema:
  words (word PRIMARY KEY, cefr, opal, awl, oxford_lists, fetched_at, n_defs)
  definitions (id INTEGER PK, word FK, n, text, examples_json)
  register_tags (word, tag) — one row per (word, tag)
  subject_labels (word, label) — one row per (word, label)
  pos (word, pos) — one row per (word, pos)

Usage:
  python tools/load_oxford_sqlite.py            # build
  python tools/load_oxford_sqlite.py --query "SELECT cefr, COUNT(*) FROM words GROUP BY cefr"
"""
from __future__ import annotations
import argparse
import json
import sqlite3
import sys
from pathlib import Path

PR = Path(r"C:\Users\admin\Downloads\ielts-deck")
JSONL = PR / "data" / "oxford_full.jsonl"
DB = PR / "data" / "anki_vocab.db"

SCHEMA = """
DROP TABLE IF EXISTS words;
DROP TABLE IF EXISTS definitions;
DROP TABLE IF EXISTS register_tags;
DROP TABLE IF EXISTS subject_labels;
DROP TABLE IF EXISTS pos;

CREATE TABLE words (
  word TEXT PRIMARY KEY,
  cefr TEXT,
  opal TEXT,
  awl TEXT,
  oxford_lists TEXT,
  fetched_at TEXT,
  n_defs INTEGER,
  source_url TEXT
);

CREATE TABLE definitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  word TEXT NOT NULL,
  n INTEGER NOT NULL,
  text TEXT,
  examples_json TEXT,
  FOREIGN KEY (word) REFERENCES words(word) ON DELETE CASCADE
);
CREATE INDEX idx_def_word ON definitions(word);

CREATE TABLE register_tags (
  word TEXT NOT NULL,
  tag TEXT NOT NULL,
  FOREIGN KEY (word) REFERENCES words(word) ON DELETE CASCADE,
  PRIMARY KEY (word, tag)
);

CREATE TABLE subject_labels (
  word TEXT NOT NULL,
  label TEXT NOT NULL,
  FOREIGN KEY (word) REFERENCES words(word) ON DELETE CASCADE,
  PRIMARY KEY (word, label)
);

CREATE TABLE pos (
  word TEXT NOT NULL,
  pos TEXT NOT NULL,
  FOREIGN KEY (word) REFERENCES words(word) ON DELETE CASCADE,
  PRIMARY KEY (word, pos)
);

CREATE INDEX idx_pos_word ON pos(word);
CREATE INDEX idx_reg_word ON register_tags(word);
CREATE INDEX idx_subj_word ON subject_labels(word);
"""


def build():
    if not JSONL.exists():
        sys.exit(f"Missing {JSONL} — run scrape_oxford_full.py first")
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)

    n_words = 0
    with JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "error" in rec:
                continue  # skip failed fetches
            w = rec["word"]
            con.execute(
                "INSERT INTO words (word, cefr, opal, awl, oxford_lists, fetched_at, n_defs, source_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    w,
                    rec.get("cefr"),
                    rec.get("opal"),
                    rec.get("awl"),
                    ",".join(rec.get("oxford_lists") or []),
                    rec.get("fetched_at"),
                    len(rec.get("definitions") or []),
                    rec.get("source_url"),
                ),
            )
            for p in rec.get("pos") or []:
                con.execute("INSERT OR IGNORE INTO pos (word, pos) VALUES (?, ?)", (w, p))
            for tag in rec.get("register_tags") or []:
                con.execute("INSERT OR IGNORE INTO register_tags (word, tag) VALUES (?, ?)", (w, tag))
            for sub in rec.get("subject_labels") or []:
                con.execute("INSERT OR IGNORE INTO subject_labels (word, label) VALUES (?, ?)", (w, sub))
            for d in rec.get("definitions") or []:
                con.execute(
                    "INSERT INTO definitions (word, n, text, examples_json) VALUES (?, ?, ?, ?)",
                    (w, d.get("n"), d.get("text"), json.dumps(d.get("examples") or [])),
                )
            n_words += 1
    con.commit()
    # Stats
    cur = con.execute("SELECT COUNT(*) FROM words")
    n = cur.fetchone()[0]
    cur = con.execute("SELECT COUNT(*) FROM definitions")
    nd = cur.fetchone()[0]
    cur = con.execute("SELECT COUNT(*) FROM register_tags")
    nr = cur.fetchone()[0]
    cur = con.execute("SELECT COUNT(*) FROM subject_labels")
    ns = cur.fetchone()[0]
    con.close()
    print(f"Built {DB}: words={n} definitions={nd} register_tags={nr} subject_labels={ns}")


def query(sql: str):
    con = sqlite3.connect(DB)
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    for row in cur.fetchall():
        print(dict(zip(cols, row)))
    con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--query", help="Run a SQL query against the built database")
    args = p.parse_args()
    if args.query:
        if not DB.exists():
            build()
        query(args.query)
    else:
        build()
