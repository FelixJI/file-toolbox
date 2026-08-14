"""测试用例数不回退门禁(G3)。

统计 pytest 收集到的用例数,低于基线则失败(非零退出)。
目的:防止误删测试导致用例数悄悄下降(line coverage 无法发现「整类边界用例被删」)。

用法:
    uv run --extra dev python scripts/check_test_count.py           # 默认基线
    uv run --extra dev python scripts/check_test_count.py 1500      # 临时指定基线

更新基线:新增测试后,运行一次确认实际数,把本脚本的 DEFAULT_MIN 改为新值并提交。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# CI(如 GitHub Actions windows-latest,英文区域)控制台默认 cp1252,
# 无法编码脚本里的中文/✓/✗ 字符 → print 抛 UnicodeEncodeError。
# 把标准流重配为 UTF-8,使脚本不依赖控制台代码页(reconfigure 原地生效)。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

_REPO_ROOT = Path(__file__).resolve().parents[1]

# 基线:删除自研 ZIP 更新器与 Setup bridge 测试后的实际用例数。
# 超过此数即通过;低于则失败提醒「测试被删除」。
DEFAULT_MIN = 1524


def collect_test_count() -> int:
    """运行 pytest --co -q 收集用例,解析末行 'N tests collected' 返回 N。"""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--co", "-q"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    # pytest --co -q 末行形如 "1441 tests collected" 或 "1441 tests, ... selected"
    out = (result.stdout + result.stderr).strip().splitlines()
    for line in reversed(out):
        line = line.strip()
        if "test" in line and "collected" in line:
            # 取首个整数
            for token in line.split():
                if token.isdigit():
                    return int(token)
            break
    # 兜底:若解析失败,把输出拼回便于排查
    print("⚠️ 无法解析用例数,pytest 输出末尾:", file=sys.stderr)
    print("\n".join(out[-5:]), file=sys.stderr)
    return -1


def main() -> int:
    min_required = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MIN
    count = collect_test_count()
    if count < 0:
        print("✗ 无法统计用例数,检查 pytest 是否可用", file=sys.stderr)
        return 2
    print(f"收集到 {count} 个用例(基线 ≥ {min_required})")
    if count < min_required:
        print(
            f"✗ 用例数 {count} 低于基线 {min_required} —— 测试疑似被删除。"
            "若为有意精简,请同步下调 scripts/check_test_count.py 的 DEFAULT_MIN。",
            file=sys.stderr,
        )
        return 1
    print("✓ 用例数达标")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
