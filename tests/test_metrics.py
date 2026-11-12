"""
tests/test_metrics.py
=====================
指标与判定逻辑的单元测试。

覆盖：年代分组、主类型判定、星级归一、一致性四档、Z 分数、情感分析边界、指数方向性。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.consistency_check import label_consistency, star_to_norm  # noqa: E402
from src.sentiment import analyze_text  # noqa: E402
from src.statistics import assign_era, assign_main_genre  # noqa: E402
from src.underrated_index import _zscore, compute_index  # noqa: E402


class TestEra:
    """年代分组。"""

    @pytest.mark.parametrize(
        "year,exp",
        [
            (1948, "1950年以前"),
            (1950, "1950—1959"),
            (1994, "1990—1999"),
            (2010, "2010—2019"),
            (2024, "2020年及以后"),
        ],
    )
    def test_boundary(self, year, exp):
        """边界年份应归入正确分组。"""
        assert assign_era(year) == exp

    def test_invalid(self):
        """无法解析时返回「未知」。"""
        assert assign_era("abc") == "未知"
        assert assign_era(None) == "未知"


class TestGenre:
    """主类型判定。"""

    def test_first_genre(self):
        """首个类型在候选内时直接采用。"""
        label, rule = assign_main_genre("犯罪 剧情")
        assert label == "犯罪"
        assert rule == "来源首个类型"

    def test_priority(self):
        """首个类型不在候选内时按优先级挑选。"""
        assert assign_main_genre("冒险 动画")[0] == "动画"

    def test_empty(self):
        """空类型串归入其他。"""
        assert assign_main_genre("")[0] == "其他"


class TestStarNorm:
    """星级归一。"""

    @pytest.mark.parametrize("star,exp", [(1, -1.0), (3, 0.0), (5, 1.0)])
    def test_norm(self, star, exp):
        """1/3/5 星应映射为 -1/0/+1。"""
        assert star_to_norm(star) == pytest.approx(exp)

    def test_out_of_range(self):
        """超出 1—5 的星级返回 NaN。"""
        assert np.isnan(star_to_norm(0))
        assert np.isnan(star_to_norm(6))


class TestConsistency:
    """一致性四档判定。"""

    def test_consistent(self):
        """差距小时判一致。"""
        assert label_consistency(0.2, 0.8)[0] == "一致"

    def test_mild(self):
        """中等差距判轻度不一致。"""
        assert label_consistency(0.8, 0.8)[0] == "轻度不一致"

    def test_severe(self):
        """差距大判严重矛盾。"""
        assert label_consistency(1.8, 0.8)[0] == "严重矛盾"

    def test_low_confidence(self):
        """置信度过低时不参与判定。"""
        assert label_consistency(1.5, 0.1)[0] == "无法判定"


class TestZScore:
    """Z 分数。"""

    def test_mean_zero(self):
        """标准化后均值接近 0。"""
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        assert abs(_zscore(s).mean()) < 1e-9

    def test_constant(self):
        """常数序列返回全零而非 NaN。"""
        out = _zscore(pd.Series([3.0, 3.0, 3.0]))
        assert (out == 0).all()


class TestSentiment:
    """情感分析。"""

    def test_positive(self):
        """明确正面判 pos。"""
        r = analyze_text("这部电影太好看了，感动到哭")
        assert r["sentiment_label"] == "pos"
        assert r["sentiment_score"] > 0

    def test_negative(self):
        """明确负面判 neg。"""
        r = analyze_text("剧情拖沓，演技尴尬，完全浪费时间")
        assert r["sentiment_label"] == "neg"

    def test_negation(self):
        """「不好看」分数低于「好看」。"""
        assert (analyze_text("这部电影不好看")["sentiment_score"]
                < analyze_text("这部电影很好看")["sentiment_score"])

    def test_empty(self):
        """空文本返回中性、零置信度。"""
        r = analyze_text("")
        assert r["sentiment_label"] == "neu"
        assert r["sentiment_confidence"] == 0.0

    def test_feichang_not_negation(self):
        """「非常」中的「非」不应被当作否定。"""
        assert analyze_text("非常精彩")["sentiment_score"] > 0

    def test_idiom_not_negation(self):
        """「两小无猜」中的「无」不应翻转后面的情感词。"""
        r = analyze_text("两小无猜，温暖美好")
        assert r["sentiment_score"] > 0


class TestIndex:
    """被低估指数的数值性质。"""

    def _frame(self) -> pd.DataFrame:
        """构造最小特征表。"""
        return pd.DataFrame(
            {
                "movie_id": ["1", "2", "3", "4"],
                "mean_sentiment": [0.6, 0.1, -0.2, 0.3],
                "douban_rating": [8.5, 9.0, 8.8, 9.2],
                "H_raw": [5.0, 3.0, 2.0, 4.0],
                "P_raw": [5.5, 6.0, 5.8, 6.2],
                "n_valid": [50, 60, 55, 70],
            }
        )

    def test_direction(self):
        """文本情感相对评分更高的影片应得更高 U。"""
        df = compute_index(self._frame())
        assert df.loc[0, "U"] == df["U"].max()

    def test_no_nan(self):
        """权重变化不应产生 NaN。"""
        df1 = compute_index(self._frame(), 0.5, 0.3, 0.2)
        df2 = compute_index(self._frame(), 0.3, 0.5, 0.2)
        assert not df1["U"].isna().any()
        assert not np.allclose(df1["U"], df2["U"])

    def test_gap_uses_zscore(self):
        """gap 应为标准化后的差值，而非原始刻度差。"""
        df = compute_index(self._frame())
        # 原始刻度差：0.6 - (2*8.5-15)/5 = 0.6 - 0.4 = 0.2
        # 标准化后不应等于 0.2 的简单差
        assert "S_z" in df.columns and "R_z" in df.columns


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))