#!/usr/bin/env bash
# 不經 Docker、直接在本機啟動伺服器（與 Dockerfile 的 CMD 相同）。
# 用法：./run.sh
set -euo pipefail
cd "$(dirname "$0")"

# 優先使用專案的虛擬環境；沒有就建一個並裝依賴
if [ ! -x .venv/bin/uvicorn ]; then
  echo "建立虛擬環境並安裝依賴……"
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 3000
