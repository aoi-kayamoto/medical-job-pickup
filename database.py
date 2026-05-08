import sqlite3
import os
from datetime import datetime

# データ保存先: Docker volume (/app/data) があればそこへ、なければ data/ フォルダへ
_data_dir = "/app/data" if os.path.isdir("/app/data") else os.path.join(os.path.dirname(__file__), "data")
os.makedirs(_data_dir, exist_ok=True)  # フォルダがなければ自動作成（配布版の安全設計）
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
            job_tier INTEGER DEFAULT 2,
            is_scam INTEGER DEFAULT 0,
            scam_score INTEGER DEFAULT 0,
            scam_reasons TEXT,
            categories TEXT,
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
            scam_blocked INTEGER DEFAULT 0,
            status TEXT NOT NULL,
            message TEXT
        )
    """)
    conn.commit()
    conn.close()
    _migrate_db()


def _migrate_db():
    """既存DBへ新カラムを安全に追加（冪等）"""
    conn = get_connection()
    cursor = conn.cursor()
    migrations = [
        ("ALTER TABLE jobs ADD COLUMN job_tier INTEGER DEFAULT 2",),
        ("ALTER TABLE jobs ADD COLUMN is_scam INTEGER DEFAULT 0",),
        ("ALTER TABLE jobs ADD COLUMN scam_score INTEGER DEFAULT 0",),
        ("ALTER TABLE jobs ADD COLUMN scam_reasons TEXT",),
        ("ALTER TABLE jobs ADD COLUMN categories TEXT",),
        ("ALTER TABLE fetch_logs ADD COLUMN scam_blocked INTEGER DEFAULT 0",),
    ]
    for (sql,) in migrations:
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError:
            pass  # カラムが既に存在する場合は無視
    conn.commit()
    conn.close()


def insert_job(source, title, description, url, budget, posted_at,
               matched_keywords, job_tier=2, is_scam=0,
               scam_score=0, scam_reasons=None, categories=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO jobs
            (source, title, description, url, budget, posted_at, fetched_at,
             matched_keywords, job_tier, is_scam, scam_score, scam_reasons, categories)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source, title, description, url, budget, posted_at,
            datetime.now().isoformat(),
            ",".join(matched_keywords),
            job_tier,
            is_scam,
            scam_score,
            ",".join(scam_reasons or []),
            ",".join(categories or []),
        ))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def log_fetch(source, count, scam_blocked=0, status="success", message=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO fetch_logs (fetched_at, source, count, scam_blocked, status, message)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), source, count, scam_blocked, status, message))
    conn.commit()
    conn.close()


def get_jobs(limit=200, offset=0, source=None, tier=None,
             only_bookmarked=False, search=None, show_scam=False):
    conn = get_connection()
    cursor = conn.cursor()
    scam_condition = "is_scam = 1" if show_scam else "is_scam = 0"
    query = f"SELECT * FROM jobs WHERE is_dismissed = 0 AND {scam_condition}"
    params = []
    if source and source != "all":
        query += " AND source = ?"
        params.append(source)
    if tier and tier != "all" and not show_scam:
        query += " AND job_tier = ?"
        params.append(int(tier))
    if only_bookmarked:
        query += " AND is_bookmarked = 1"
    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    query += " ORDER BY job_tier ASC, fetched_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job_count(source=None, tier=None, only_bookmarked=False, search=None, show_scam=False):
    conn = get_connection()
    cursor = conn.cursor()
    scam_condition = "is_scam = 1" if show_scam else "is_scam = 0"
    query = f"SELECT COUNT(*) FROM jobs WHERE is_dismissed = 0 AND {scam_condition}"
    params = []
    if source and source != "all":
        query += " AND source = ?"
        params.append(source)
    if tier and tier != "all" and not show_scam:
        query += " AND job_tier = ?"
        params.append(int(tier))
    if only_bookmarked:
        query += " AND is_bookmarked = 1"
    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
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

    # 総数（詐欺除外済み）
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE is_dismissed = 0 AND is_scam = 0")
    stats["total"] = cursor.fetchone()[0]

    # Tier別
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE is_dismissed = 0 AND is_scam = 0 AND job_tier = 1")
    stats["tier1"] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE is_dismissed = 0 AND is_scam = 0 AND job_tier = 2")
    stats["tier2"] = cursor.fetchone()[0]

    # ブックマーク
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE is_bookmarked = 1 AND is_dismissed = 0 AND is_scam = 0")
    stats["bookmarked"] = cursor.fetchone()[0]

    # 詐欺ブロック数（累計）
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE is_scam = 1")
    stats["scam_blocked"] = cursor.fetchone()[0]

    # ソース別
    cursor.execute("""
        SELECT source, COUNT(*) as cnt
        FROM jobs WHERE is_dismissed = 0 AND is_scam = 0
        GROUP BY source
    """)
    stats["by_source"] = {row[0]: row[1] for row in cursor.fetchall()}

    # 最終取得日時
    cursor.execute("""
        SELECT fetched_at FROM jobs ORDER BY fetched_at DESC LIMIT 1
    """)
    row = cursor.fetchone()
    stats["last_fetch"] = row[0] if row else None

    conn.close()
    return stats
