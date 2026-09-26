#!/bin/sh
# 容器入口：
#   serve   启动裁决 API（默认）
#   verify  一次性校验：代码测试 -> 构建（字节码编译）-> 裁决 API 冒烟，
#           以退出码报告全部结果
set -eu

case "${1:-serve}" in
  serve)
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  verify)
    echo "================ [1/3] 代码测试 (pytest) ================"
    python -m pytest tests/ -q

    echo "================ [2/3] 构建检查 (compileall) ================"
    python -m compileall -q app
    python -c "from app.main import app; print('应用装配成功:', app.title)"

    echo "================ [3/3] 裁决 API 冒烟 ================"
    BASE_URL="${BASE_URL:-http://web:8000}" python scripts/smoke.py

    echo
    echo "VERIFY OK: 测试、构建与裁决 API 冒烟全部通过"
    ;;
  *)
    exec "$@"
    ;;
esac
