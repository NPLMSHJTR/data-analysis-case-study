"""
tests/test_docs_consistency.py
==============================
文档与代码的一致性检查。

起因
----
文档里写着「每层可单独运行 python -m src.模块名」，但实际只有两个模块带
`if __name__ == "__main__"`，照着文档敲会静默什么都不发生。
这类「文档说了但代码没做」的问题不会报错，只能靠检查兜住。

本文件检查三件事：
1. 文档里点名的每个模块，都必须真的能 `python -m` 跑；
2. 文档里引用的表格/图表数量与实际产物一致；
3. config.py 里的关键配置项确实存在（文档让用户去改这些）。
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# 文档（README + usage.md）声称可单独运行的模块
RUNNABLE_MODULES = [
    "acquisition", "cleaning", "quality_classification", "sentiment",
    "consistency_check", "method_comparison", "statistics",
    "underrated_index", "mismatch_analysis", "recommendation",
    "visualization", "code_screenshot", "mismatch_cases",
    "report_generator", "ppt_generator",
]


@pytest.mark.parametrize("module", RUNNABLE_MODULES)
def test_module_has_main_guard(module):
    """每个被文档点名的模块都要有命令行入口。"""
    path = ROOT / "src" / f"{module}.py"
    assert path.exists(), f"src/{module}.py 不存在"
    text = path.read_text(encoding="utf-8")
    assert '__name__ == "__main__"' in text, (
        f"src/{module}.py 缺少 `if __name__ == \"__main__\"` 入口，"
        f"文档里写的 `python -m src.{module}` 会静默无输出"
    )


@pytest.mark.parametrize("module", RUNNABLE_MODULES)
def test_module_importable(module):
    """模块能被导入，且入口函数存在。"""
    mod = importlib.import_module(f"src.{module}")
    assert mod is not None


def test_usage_doc_exists():
    """使用手册必须存在且不是空壳。"""
    p = DOCS / "usage.md"
    assert p.exists(), "docs/usage.md 缺失"
    text = p.read_text(encoding="utf-8")
    assert len(text) > 5000, "使用手册内容过短，疑似未写完"
    # 手册应覆盖这几件事
    for kw in ["python main.py", "pip install", "config.py", "报错"]:
        assert kw in text, f"使用手册缺少关键内容：{kw}"


def test_readme_links_usage_doc():
    """README 必须指向使用手册，否则没人会找到它。"""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/usage.md" in text, "README 里没有使用手册的链接"


def test_usage_doc_module_commands_valid():
    """
    手册里出现的 `python -m src.xxx` 命令，模块必须真实存在。

    防止文档里写了不存在的模块名。
    """
    text = (DOCS / "usage.md").read_text(encoding="utf-8")
    found = set(re.findall(r"python -m src\.([a-z_]+)", text))
    assert found, "手册里没有任何 `python -m src.xxx` 命令"

    for name in found:
        path = ROOT / "src" / f"{name}.py"
        assert path.exists(), f"手册里写的 `python -m src.{name}` 找不到对应文件"


def test_documented_counts_match_outputs():
    """
    文档里写的表格/图表数量与磁盘上的实际文件数一致。

    只在产物已生成时检查，避免在干净环境下误报。
    """
    table_dir = ROOT / "outputs" / "tables"
    fig_dir = ROOT / "outputs" / "figures"
    if not table_dir.exists() or not fig_dir.exists():
        pytest.skip("产物尚未生成")

    n_tables = len(list(table_dir.glob("*.csv")))
    n_figs = len(list(fig_dir.glob("*.png")))
    if n_tables == 0:
        pytest.skip("统计表为空")

    text = (DOCS / "usage.md").read_text(encoding="utf-8")
    assert f"{n_figs} 张" in text or f"{n_figs} 个" in text, (
        f"手册没提到图表数量 {n_figs}"
    )
    assert f"{n_tables} 个" in text or f"{n_tables} 张" in text, (
        f"手册没提到统计表数量 {n_tables}"
    )


def test_config_keys_referenced_by_docs():
    """
    手册让用户去改的配置项，必须在 config.py 里真实存在。

    改错名字去找一个不存在的键，用户会卡住。
    """
    import config

    keys = [
        "COVER_INFO", "REVIEW_DIRNAME", "REVIEW_FILE_PREFIX",
        "CONSISTENCY_TOLERANT_GAP", "CONSISTENCY_SEVERE_GAP",
        "MIN_CONFIDENCE_FOR_CONSISTENCY",
        "WEIGHT_SENTIMENT_GAP", "WEIGHT_USEFUL", "WEIGHT_ATTENTION",
        "WEIGHT_SENSITIVITY_GRID",
        "REC_WEIGHTS", "REC_MIN_YEARS_SINCE_RELEASE",
        "RANDOM_SEED", "REQUEST_DELAY",
    ]
    for k in keys:
        assert hasattr(config, k), f"config.py 缺少文档中提到的配置项：{k}"


def test_cover_info_has_all_fields():
    """封面字段齐全，缺了会显示空白。"""
    import config

    for k in ["课程名称", "项目名称", "姓名", "班级", "学号", "指导教师"]:
        assert k in config.COVER_INFO, f"COVER_INFO 缺字段：{k}"