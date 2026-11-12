"""
tests/test_cleaning.py
======================
文本清洗与内容分级的单元测试。

覆盖：文本规范化、噪声识别、广告识别、四档分类的边界情况。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.cleaning import clean_text, is_pure_noise  # noqa: E402
from src.quality_classification import classify_by_rules, is_ad  # noqa: E402


class TestCleanText:
    """clean_text 的行为。"""

    def test_removes_html(self):
        """HTML 标签应被清除。"""
        assert clean_text("<p>好看</p>") == "好看"

    def test_removes_url(self):
        """URL 应被清除。"""
        assert "http" not in clean_text("推荐 https://example.com 这部片")

    def test_unescape_entities(self):
        """HTML 实体应还原。"""
        assert clean_text("A&nbsp;B") == "A B"

    def test_collapse_space(self):
        """连续空白应合并。"""
        assert clean_text("好看    很感人") == "好看 很感人"

    def test_non_string(self):
        """非字符串输入返回空串而不抛异常。"""
        assert clean_text(None) == ""
        assert clean_text(123) == ""

    def test_keep_punctuation(self):
        """标点承载情绪，不应被删除。"""
        assert clean_text("太棒了！！！") == "太棒了！！！"


class TestNoise:
    """纯噪声识别。"""

    @pytest.mark.parametrize("t", ["哈哈哈哈", "666666", "。。。", "😭😭😭", "12345", "顶顶顶", "yyds"])
    def test_noise(self, t):
        """纯填充内容应判为噪声。"""
        assert is_pure_noise(t) is True

    @pytest.mark.parametrize("t", ["剧情很棒", "摄影很美，但节奏拖沓", "经典"])
    def test_not_noise(self, t):
        """有实义的内容不判噪声。"""
        assert is_pure_noise(t) is False


class TestAd:
    """广告识别。"""

    def test_wechat(self):
        """含微信号应判广告。"""
        assert is_ad("加微信 xxx 领取优惠券") is True

    def test_blog(self):
        """个人博客引流应判广告。"""
        assert is_ad("更多电影评论，我的博客：blog.sina.com.cn/abc") is True

    def test_normal_platform_mention(self):
        """正常影评提到平台名不判广告。"""
        assert is_ad("电影里提到了拼多多和外卖小哥的处境") is False


class TestClassify:
    """内容分级的边界测试。"""

    def test_short_negative_kept(self):
        """「烂片」应保留为低信息量而非剔除——这是本项目的核心原则。"""
        label, reason = classify_by_rules("烂片")
        assert label == "B"
        assert "好恶" in reason

    def test_short_with_aspect(self):
        """含要素词的短句应判有效。"""
        assert classify_by_rules("摄影很棒")[0] == "A"

    def test_vague(self):
        """无要素的短词判待人工判断。"""
        assert classify_by_rules("牵强")[0] == "E"

    def test_empty(self):
        """空文本判剔除。"""
        assert classify_by_rules("")[0] == "X"

    def test_long_text(self):
        """有篇幅的观描述判有效。"""
        label, _ = classify_by_rules("整部片子的叙事节奏控制得很好，结尾尤其克制")
        assert label == "A"

    def test_critique_is_valid(self):
        """低星客观批评必须判为有效评论。"""
        text = "叙事结构混乱，人物动机缺乏铺垫，后半段节奏拖沓"
        assert classify_by_rules(text)[0] == "A"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))