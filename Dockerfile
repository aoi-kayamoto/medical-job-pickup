# ─── ベースイメージ ───
FROM python:3.11-slim

# 日本語ロケール・タイムゾーン設定
ENV LANG=ja_JP.UTF-8 \
    TZ=Asia/Tokyo \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 作業ディレクトリ
WORKDIR /app

# 必要な最小限のシステムライブラリ（lxml用など）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリ本体をコピー
COPY . .

# データ永続化用ディレクトリ
VOLUME ["/app/data"]

EXPOSE 8765

CMD ["python", "main.py"]
