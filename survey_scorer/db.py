import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS respondents (
    respondent_id TEXT PRIMARY KEY,
    age           INTEGER,
    child_age     INTEGER,
    gender        TEXT
);

CREATE TABLE IF NOT EXISTS results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    respondent_id TEXT  NOT NULL,
    instrument_id TEXT  NOT NULL,
    scale_id      TEXT  NOT NULL,
    scale_name    TEXT  NOT NULL,
    raw_score     REAL  NOT NULL,
    level         TEXT  NOT NULL,
    label         TEXT  NOT NULL,
    interpretation TEXT NOT NULL,
    calculated_at TEXT  NOT NULL DEFAULT (datetime('now')),
    UNIQUE(respondent_id, instrument_id, scale_id)
);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.executescript(SCHEMA)
    # Migrate: add columns for existing DBs that lack them
    for col, typ in [("age", "INTEGER"), ("child_age", "INTEGER"), ("gender", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE respondents ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    return conn


def save_respondent(conn: sqlite3.Connection, respondent_id: str,
                    age: int = None, child_age: int = None, gender: str = None):
    conn.execute(
        """INSERT INTO respondents (respondent_id, age, child_age, gender)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(respondent_id) DO UPDATE SET
               age = COALESCE(excluded.age, age),
               child_age = COALESCE(excluded.child_age, child_age),
               gender = COALESCE(excluded.gender, gender)""",
        (respondent_id, age, child_age, gender),
    )
    conn.commit()


def save_results(conn: sqlite3.Connection, score_results: list) -> int:
    saved = 0
    for result in score_results:
        conn.execute(
            "INSERT OR IGNORE INTO respondents (respondent_id) VALUES (?)",
            (result.respondent_id,),
        )
        for scale in result.scales:
            conn.execute(
                """
                INSERT OR REPLACE INTO results
                    (respondent_id, instrument_id, scale_id, scale_name,
                     raw_score, level, label, interpretation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.respondent_id,
                    result.instrument_id,
                    scale.scale_id,
                    scale.scale_name,
                    scale.raw_score,
                    scale.level,
                    scale.label,
                    scale.interpretation,
                ),
            )
            saved += 1
    conn.commit()
    return saved


def query_results(
    conn: sqlite3.Connection,
    instrument_id: str = None,
    respondent_id: str = None,
) -> list:
    query = """
        SELECT respondent_id, instrument_id, scale_id, scale_name,
               raw_score, level, label, interpretation, calculated_at
        FROM results
        WHERE 1=1
    """
    params = []
    if instrument_id:
        query += " AND instrument_id = ?"
        params.append(instrument_id)
    if respondent_id:
        query += " AND respondent_id = ?"
        params.append(respondent_id)
    query += " ORDER BY respondent_id, instrument_id, scale_id"

    cursor = conn.execute(query, params)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
