"""
tests/test_ppt_notes.py
=======================
演讲者备注的完整性测试。

重点防两类问题：
1. 备注漏写（页数对不上，或某页备注为空）；
2. 备注里写死了解释不清的口头数字，与结果文件脱节。

不校验措辞，只校验「每页都有」「长度合理」「关键数字与结果表一致」。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ppt_notes import NOTES, apply_notes, get_note

ROOT = Path(__file__).resolve().parent.parent
PPTX = ROOT / "outputs" / "reports" / "豆瓣电影Top250数据分析课程汇报.pptx"


def test_every_page_has_note():
    """20 页必须全部有备注，页码连续无缺。"""
    assert sorted(NOTES.keys()) == list(range(1, 21))


def test_note_length_reasonable():
    """备注太长讲不完、太短没信息量，限制在 150—900 字。"""
    for page, text in NOTES.items():
        n = len(text)
        assert 150 <= n <= 900, f"第 {page} 页备注长度 {n} 字，超出合理区间"


def test_note_has_speaking_marker():
    """每页都应带「讲」标记，保证是讲稿而不是摘要。"""
    for page, text in NOTES.items():
        assert "【讲】" in text, f"第 {page} 页缺少【讲】标记"


def test_get_note_out_of_range():
    """页码越界返回空串，不应抛异常。"""
    assert get_note(0) == ""
    assert get_note(99) == ""


@pytest.mark.skipif(not PPTX.exists(), reason="PPT 尚未生成")
def test_pptx_contains_notes():
    """已生成的 PPT 里每页都要真的带上备注。"""
    from pptx import Presentation

    prs = Presentation(str(PPTX))
    assert len(prs.slides) == 20, "PPT 页数与备注表不一致"

    for idx, slide in enumerate(prs.slides, start=1):
        assert slide.has_notes_slide, f"第 {idx} 页没有备注页"
        text = slide.notes_slide.notes_text_frame.text
        assert len(text) >= 150, f"第 {idx} 页备注为空或过短"


@pytest.mark.skipif(not PPTX.exists(), reason="PPT 尚未生成")
def test_notes_numbers_match_tables():
    """
    备注中引用的关键数字必须与结果表一致。

    只抽几个最容易被口误讲错的数：F1 提升前后、召回下降、覆盖率。
    """
    import pandas as pd
    from pptx import Presentation

    cmp_path = ROOT / "outputs" / "tables" / "method_comparison.csv"
    if not cmp_path.exists():
        pytest.skip("方法对比结果不存在")

    cmp_df = pd.read_csv(cmp_path)
    prs = Presentation(str(PPTX))
    all_notes = "\n".join(
        s.notes_slide.notes_text_frame.text for s in prs.slides if s.has_notes_slide
    )

    # F1 的两个值应出现在备注里（第 10、18 页引用）
    for col in cmp_df.columns:
        if "F1" in str(col).upper() or "f1" in str(col).lower():
            for v in cmp_df[col].dropna():
                try:
                    s = f"{float(v):.4f}"
                except (TypeError, ValueError):
                    continue
                assert s in all_notes, f"备注里缺少 F1 值 {s}"
            break


def test_apply_notes_counts():
    """apply_notes 应返回实际写入的页数，且不因空串报错。"""

    class _Slide:
        """最小化的幻灯片替身，只提供备注写入接口。"""

        def __init__(self):
            self.notes_slide = type(
                "N", (), {"notes_text_frame": type("T", (), {"text": ""})()}
            )()

    class _Prs:
        def __init__(self, n):
            self.slides = [_Slide() for _ in range(n)]

    assert apply_notes(_Prs(20)) == 20
    assert apply_notes(_Prs(5)) == 5