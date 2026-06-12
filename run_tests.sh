#!/bin/bash
# Telme - 一键测试 & 性能分析脚本
set -e

cd "$(dirname "$0")"

echo "=== 1. 激活虚拟环境 ==="
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "=== 2. 重新安装（确保代码更新生效） ==="
pip install -e ".[dev]" --quiet

echo ""
echo "=========================================="
echo "=== 3. 功能测试 ==="
echo "=========================================="
pytest tests/test_server_api.py tests/test_crypto.py tests/test_database.py -v --tb=short 2>&1 | tail -60

echo ""
echo "=========================================="
echo "=== 4. 安全性测试 ==="
echo "=========================================="
pytest tests/test_security.py -v --tb=short 2>&1 | tail -40

echo ""
echo "=========================================="
echo "=== 5. 压力测试 (含性能计时) ==="
echo "=========================================="
pytest tests/test_stress.py -v -s --tb=short --durations=0 2>&1 | tail -50

echo ""
echo "=========================================="
echo "=== 6. 全部测试汇总 ==="
echo "=========================================="
pytest tests/ --tb=short -q 2>&1 | tail -10

echo ""
echo "=== 完成! ==="
