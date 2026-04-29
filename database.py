import sqlite3
import os
from datetime import datetime

_data_dir = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(_data_dir, exist_ok=True)
DB_PATH = os.path.join(_data_dir, "jobs.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            url TEXT UNIQUE NOT NULL,
            budget TEXT,
            posted_at TEXT,
            fetched_at TEXT NOT NULL,
            matched_keywords TEXT,
            is_bookmarked INTEGER DEFAULT 0,
            is_dismissed INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fetch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT NOT NULL,
            source TEXT NOT NULL,
            count INTEGER NOT NULL,
            status TEXT NOT NULL,
            message TEXT
        )
    """)
    conn.commit()
    conn.close()


def insert_job(source, title, description, url, budget, posted_at, matched_keywords):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO jobs
            (source, title, description, url, budget, posted_at, fetched_at, matched_keywords)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source, title, description, url, budget, posted_at,
            datetime.now().isoformat(),
            ",".join(matched_keywords)
        ))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def log_fetch(source, count, status, message=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO fetch_logs (fetched_at, source, count, status, message)
        VALUES (?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), source, count, status, message))
    conn.commit()
    conn.close()


_CATEGORY_KEYWORDS = {
    "medical": ["医療", "看護", "クリニック", "病院", "医師", "薬剤師", "介護", "ヘルスケア"],
    "writer":  ["ライター", "執筆", "ライティング", "記事作成", "記事執筆", "コンテンツ制作"],
    "sns":     ["SNS", "Instagram", "インスタ", "TikTok", "ソーシャルメディア"],
}


def _category_clause(category: str):
    keywords = _CATEGORY_KEYWORDS.get(category, [])
    if not keywords:
        return "", []
    conditions, params = [], []
    for kw in keywords:
        conditions.append("(title LIKE ? OR description LIKE ? OR matched_keywords LIKE ?)")
        params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
    return " AND (" + " OR ".join(conditions) + ")", params


def get_jobs(limit=200, offset=0, source=None, only_bookmarked=False, search=None, category=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM jobs WHERE is_dismissed = 0"
    params = []
    if source and source != "all":
        query += " AND source = ?"
        params.append(source)
    if only_bookmarked:
        query += " AND is_bookmarked = 1"
    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if category:
        clause, cat_params = _category_clause(category)
        query += clause
        params.extend(cat_params)
    query += " ORDER BY fetched_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job_count(source=None, only_bookmarked=False, search=None, category=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT COUNT(*) FROM jobs WHERE is_dismissed = 0"
    params = []
    if source and source != "all":
        query += " AND source = ?"
        params.append(source)
    if only_bookmarked:
        query += " AND is_bookmarked = 1"
    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if category:
        clause, cat_params = _category_clause(category)
        query += clause
        params.extend(cat_params)
    cursor.execute(query, params)
    count = cursor.fetchone()[0]
    conn.close()
    return count


def toggle_bookmark(job_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET is_bookmarked = 1 - is_bookmarked WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()


def dismiss_job(job_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET is_dismissed = 1 WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()


def get_fetch_logs(limit=20):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM fetch_logs ORDER BY fetched_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    stats = {}
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE is_dismissed = 0")
    stats["total"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE is_bookmarked = 1 AND is_dismissed = 0")
    stats["bookmarked"] = cursor.fetchone()[0]
    cursor.execute("SELECT source, COUNT(*) as cnt FROM jobs WHERE is_dismissed = 0 GROUP BY source")
    stats["by_source"] = {row[0]: row[1] for row in cursor.fetchall()}
    cursor.execute("""
        SELECT fetched_at FROM jobs WHERE is_dismissed = 0
        ORDER BY fetched_at DESC LIMIT 1
    """)
    row = cursor.fetchone()
    stats["last_fetch"] = row[0] if row else None
    conn.close()
    return stats
