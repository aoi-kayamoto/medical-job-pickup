"""
FastAPI バックエンド + 毎日自動スクレイピングスケジューラー
"""
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import schedule
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
    # バックグラウンドスレッドでスケジューラー起動
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("メディフリ案件ピックアップツール起動完了")
    yield
    logger.info("サーバー停止")


# ─────────────────────────────────────
# FastAPI アプリ
# ─────────────────────────────────────
app = FastAPI(
    title="メディフリ案件ピックアップ",
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
    bookmarked: bool = Query(False),
    search: str = Query(""),
    category: str = Query(""),
):
    jobs = get_jobs(
        limit=limit,
        offset=offset,
        source=source if source != "all" else None,
        only_bookmarked=bookmarked,
        search=search if search else None,
        category=category if category else None,
    )
    total = get_job_count(
        source=source if source != "all" else None,
        only_bookmarked=bookmarked,
        search=search if search else None,
        category=category if category else None,
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
    """手動でスクレイピングを実行"""
    def run_in_bg():
        run_all_scrapers()

    thread = threading.Thread(target=run_in_bg, daemon=True)
    thread.start()
    return {"status": "started", "message": "バックグラウンドでスクレイピングを開始しました"}


@app.post("/api/jobs/{job_id}/bookmark")
def api_bookmark(job_id: int):
    toggle_bookmark(job_id)
    return {"status": "ok"}


@app.post("/api/jobs/{job_id}/dismiss")
def api_dismiss(job_id: int):
    dismiss_job(job_id)
    return {"status": "ok"}


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
