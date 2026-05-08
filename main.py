"""
FastAPI バックエンド + 毎日自動スクレイピングスケジューラー
配布版の安定した構成 + 医療案件・詐欺表示機能を統合
"""
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import schedule
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from database import (
    dismiss_job,
    get_fetch_logs,
    get_job_count,
    get_jobs,
    get_stats,
    init_db,
    toggle_bookmark,
)
from scrapers import run_all_scrapers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# スクレイピングの二重起動防止ロック（配布版の安定設計）
_fetch_lock = threading.Lock()


# ─────────────────────────────────────
# スケジューラー
# ─────────────────────────────────────
def run_scheduler():
    """毎朝8:00に自動スクレイピング"""
    schedule.every().day.at("08:00").do(run_all_scrapers)
    logger.info("スケジューラー起動: 毎朝 08:00 に自動取得")
    while True:
        schedule.run_pending()
        time.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("医療案件ピックアップツール起動完了")
    yield
    logger.info("サーバー停止")


# ─────────────────────────────────────
# FastAPI アプリ
# ─────────────────────────────────────
app = FastAPI(
    title="医療案件ピックアップ",
    description="看護師向けクラウドソーシング案件を自動収集するツール",
    lifespan=lifespan,
)


# ─────────────────────────────────────
# API エンドポイント
# ─────────────────────────────────────
@app.get("/api/jobs")
def api_get_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source: str = Query("all"),
    tier: str = Query("all"),
    bookmarked: bool = Query(False),
    search: str = Query(""),
    scam: bool = Query(False),
):
    source_val = source if source != "all" else None
    tier_val = tier if tier != "all" else None
    jobs = get_jobs(
        limit=limit,
        offset=offset,
        source=source_val,
        tier=tier_val,
        only_bookmarked=bookmarked,
        search=search if search else None,
        show_scam=scam,
    )
    total = get_job_count(
        source=source_val,
        tier=tier_val,
        only_bookmarked=bookmarked,
        search=search if search else None,
        show_scam=scam,
    )
    return {"jobs": jobs, "total": total}


@app.get("/api/stats")
def api_stats():
    return get_stats()


@app.get("/api/logs")
def api_logs():
    return get_fetch_logs(30)


@app.post("/api/fetch")
def api_fetch():
    """手動でスクレイピングを実行（二重起動防止付き）"""
    if not _fetch_lock.acquire(blocking=False):
        return JSONResponse(
            status_code=409,
            content={"status": "busy", "message": "現在スクレイピング中です。しばらくお待ちください。"}
        )

    def run_in_bg():
        try:
            run_all_scrapers()
        finally:
            _fetch_lock.release()

    thread = threading.Thread(target=run_in_bg, daemon=True)
    thread.start()
    return {"status": "started", "message": "バックグラウンドでスクレイピングを開始しました"}


@app.post("/api/jobs/{job_id}/bookmark")
def api_bookmark(job_id: int):
    try:
        toggle_bookmark(job_id)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jobs/{job_id}/dismiss")
def api_dismiss(job_id: int):
    try:
        dismiss_job(job_id)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────
# フロントエンド（index.html を返す）
# ─────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def root():
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>index.html が見つかりません</h1>", status_code=404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
