"""
tools/add_module_cli.py
=======================
为各分析模块补齐命令行入口。

背景
----
README 与 PPT 都写着「每层可单独运行（python -m src.模块名）」，
但实际只有 report_generator / ppt_generator 带 `if __name__ == "__main__"`，
其余模块导入后不会执行任何东西。文档与代码不一致会误导使用者，
所以这里统一补上入口。

做法
----
每个模块的入口都是同一个形状：调它的 run_* 函数，把返回的 dict 打印成 JSON。
因此用一个脚本批量追加即可，不需要逐个人工写。

注意
----
脚本可重复执行：已存在入口的模块会跳过，不会重复追加。

用法:
    python tools/add_module_cli.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# 模块名 → (入口函数名, 中文说明)
ENTRYPOINTS: dict[str, tuple[str, str]] = {
    "acquisition": ("run_acquisition", "数据采集"),
    "cleaning": ("run_cleaning", "文本清洗与重复检测"),
    "quality_classification": ("run_classification", "内容有效性分级"),
    "sentiment": ("run_sentiment", "情感分析"),
    "consistency_check": ("run_consistency_check", "星级一致性判定"),
    "method_comparison": ("run_method_comparison", "基础方法与改进方法对比"),
    "underrated_index": ("run_underrated_index", "被低估指数"),
    "mismatch_analysis": ("run_mismatch_analysis", "星级与文本不一致统计"),
    "recommendation": ("run_recommendation", "重映推荐"),
    "visualization": ("run_all", "全部图表"),
    "code_screenshot": ("run_all", "核心代码截图"),
    "mismatch_cases": ("build_final_cases", "Q4 最终 20 条样本"),
}

TEMPLATE = '''

if __name__ == "__main__":
    import json

    _result = {func}()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
'''


def has_main_guard(text: str) -> bool:
    """判断模块是否已有命令行入口。"""
    return '__name__ == "__main__"' in text


def add_entry(module: str, func: str, label: str) -> bool:
    """
    为单个模块追加命令行入口。

    参数:
        module: 模块名（不含 .py）。
        func: 要调用的入口函数名。
        label: 中文说明，用于日志。

    返回:
        True 表示本次写入成功；False 表示跳过。
    """
    path = SRC / f"{module}.py"
    if not path.exists():
        print(f"[跳过] {module}.py 不存在")
        return False

    text = path.read_text(encoding="utf-8")
    if has_main_guard(text):
        print(f"[跳过] {module}.py 已有入口")
        return False

    # 确认函数确实存在，避免写出一个跑不起来的入口
    if not re.search(rf"^def {re.escape(func)}\(", text, re.M):
        print(f"[跳过] {module}.py 里找不到函数 {func}()")
        return False

    path.write_text(text.rstrip("\n") + "\n" + TEMPLATE.format(func=func), encoding="utf-8")
    print(f"[写入] {module}.py → {func}()（{label}）")
    return True


def main() -> int:
    """为全部模块补齐入口。"""
    n = 0
    for module, (func, label) in ENTRYPOINTS.items():
        if add_entry(module, func, label):
            n += 1
    print(f"\n共写入 {n} 个入口")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())