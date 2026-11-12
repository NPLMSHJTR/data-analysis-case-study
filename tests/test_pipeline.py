"""
tests/test_pipeline.py
======================
流程完整性与产物一致性测试。

检查关键文件是否存在、字段是否齐全、报告数字与 CSV 是否一致。
需先运行过 python main.py，否则相关测试会被跳过。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import (
    FIG_DIR, PROCESSED_DIR, RAW_DIR, REPORT_DIR, SCREENSHOT_DIR, TABLE_DIR,
)


def _ok(path: Path) -> bool:
    """判断文件存在且非空。"""
    return path.exists() and path.stat().st_size > 0


class TestRaw:
    """原始数据。"""

    def test_top250(self):
        """榜单应有 250 条且 rank 连续。"""
        p = RAW_DIR / "top250_raw.csv"
        if not _ok(p):
            pytest.skip("尚未运行数据采集")
        df = pd.read_csv(p, dtype={"movie_id": str})
        assert len(df) == 250
        assert sorted(df["rank"].tolist()) == list(range(1, 251))

    def test_columns(self):
        """榜单表应含任务书要求的核心字段。"""
        p = RAW_DIR / "top250_raw.csv"
        if not _ok(p):
            pytest.skip("尚未运行数据采集")
        df = pd.read_csv(p)
        for c in ["movie_id", "title", "rank", "douban_rating", "rating_count",
                  "release_year", "country", "director", "genres", "collect_time", "source"]:
            assert c in df.columns

    def test_rating_range(self):
        """评分应在合理区间。"""
        p = RAW_DIR / "top250_raw.csv"
        if not _ok(p):
            pytest.skip("尚未运行数据采集")
        df = pd.read_csv(p)
        assert df["douban_rating"].between(0, 10).all()


class TestProcessed:
    """处理结果。"""

    def test_labels_valid(self):
        """质量标签取值应在允许集合内。"""
        p = PROCESSED_DIR / "reviews_labeled.csv"
        if not _ok(p):
            pytest.skip("尚未运行分级")
        df = pd.read_csv(p, dtype={"movie_id": str})
        assert df["quality_label"].isin(["A", "B", "C", "D", "E", "X"]).all()

    def test_labels_mutually_exclusive(self):
        """每条评论只能有一个最终标签。"""
        p = PROCESSED_DIR / "reviews_labeled.csv"
        if not _ok(p):
            pytest.skip("尚未运行分级")
        df = pd.read_csv(p, dtype={"movie_id": str})
        q = pd.read_csv(TABLE_DIR / "quality_distribution.csv")
        assert int(q["数量"].sum()) == len(df)

    def test_consistency_values(self):
        """一致性标签取值应在允许集合内（A/B 类有值）。"""
        p = PROCESSED_DIR / "reviews_dual.csv"
        if not _ok(p):
            pytest.skip("尚未运行一致性判定")
        df = pd.read_csv(p, dtype={"movie_id": str})
        ab = df[df["quality_label"].isin(["A", "B"])]
        allowed = {"一致", "轻度不一致", "严重矛盾", "无法判定"}
        assert set(ab["consistency"].dropna().unique()).issubset(allowed)

    def test_disposition_complete(self):
        """每条评论都应有最终处置。"""
        p = PROCESSED_DIR / "reviews_dual.csv"
        if not _ok(p):
            pytest.skip("尚未运行一致性判定")
        df = pd.read_csv(p, dtype={"movie_id": str})
        assert df["disposition"].notna().all()
        allowed = {"content", "sentiment", "mismatch_only", "excluded", "manual"}
        assert set(df["disposition"].unique()).issubset(allowed)


class TestOutputs:
    """产出文件。"""

    def test_figures(self):
        """至少 18 张图表。"""
        figs = list(FIG_DIR.glob("*.png"))
        if not figs:
            pytest.skip("尚未运行图表生成")
        assert len(figs) >= 18

    def test_screenshots(self):
        """至少 10 张代码截图。"""
        shots = list(SCREENSHOT_DIR.glob("*.png"))
        if not shots:
            pytest.skip("尚未运行代码截图")
        assert len(shots) >= 10

    def test_word(self):
        """Word 报告可被 python-docx 打开且篇幅合理。"""
        files = list(REPORT_DIR.glob("*.docx"))
        if not files:
            pytest.skip("尚未生成 Word")
        from docx import Document

        doc = Document(str(files[0]))
        assert len(doc.paragraphs) > 300
        assert len(doc.tables) > 20

    def test_ppt(self):
        """PPT 页数在 18—22 之间。"""
        files = list(REPORT_DIR.glob("*.pptx"))
        if not files:
            pytest.skip("尚未生成 PPT")
        from pptx import Presentation

        prs = Presentation(str(files[0]))
        assert 18 <= len(prs.slides) <= 22

    def test_key_tables(self):
        """关键统计表齐备。"""
        need = [
            "quality_distribution.csv",
            "consistency_matrix.csv",
            "method_comparison.csv",
            "q1_descriptive.csv",
            "q2_era_genre_crosstab.csv",
            "q3_underrated_top10.csv",
            "q4_mismatch_20cases.csv",
            "q5_remake_recommendations.csv",
            "q5_market_facts.csv",
        ]
        missing = [f for f in need if not _ok(TABLE_DIR / f)]
        if len(missing) == len(need):
            pytest.skip("尚未运行分析流程")
        assert not missing, f"缺少表格: {missing}"


class TestConsistency:
    """报告数字与数据文件的一致性。"""

    def test_quality_counts_match(self):
        """质量分布的 A 类数量应与标签表一致。"""
        lab = PROCESSED_DIR / "reviews_labeled.csv"
        q = TABLE_DIR / "quality_distribution.csv"
        if not (_ok(lab) and _ok(q)):
            pytest.skip("尚未生成相关文件")
        df = pd.read_csv(lab, dtype={"movie_id": str})
        dist = pd.read_csv(q)
        a_row = dist[dist["标签"] == "A"]
        if a_row.empty:
            pytest.skip("分布表无 A 类")
        assert int(a_row.iloc[0]["数量"]) == int((df["quality_label"] == "A").sum())

    def test_top10_monotonic(self):
        """被低估指数前十名应单调递减。"""
        p = TABLE_DIR / "q3_underrated_top10.csv"
        if not _ok(p):
            pytest.skip("尚未生成指数表")
        t = pd.read_csv(p).sort_values("排名")
        vals = t["被低估指数"].tolist()
        assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))

    def test_recommendation_diversity(self):
        """五部推荐应覆盖至少 4 种类型。"""
        p = TABLE_DIR / "q5_remake_recommendations.csv"
        if not _ok(p):
            pytest.skip("尚未生成推荐表")
        t = pd.read_csv(p)
        assert len(t) == 5
        assert t["主类型"].nunique() >= 4


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))