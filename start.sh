#!/usr/bin/env bash
# ─── メディフリ案件ピックアップツール 起動スクリプト ───

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🏥 メディフリ案件ピックアップツール"
echo "================================"

# 仮想環境の確認・作成
if [ ! -d ".venv" ]; then
  echo "📦 仮想環境を作成中..."
  python3 -m venv .venv
fi

# 依存関係インストール
echo "📥 依存パッケージを確認中..."
source .venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "✅ 起動完了！ブラウザで http://127.0.0.1:8765 を開いてください"
echo "🕗 毎朝 08:00 に自動取得されます"
echo "   （Ctrl+C で停止）"
echo ""

python main.py
