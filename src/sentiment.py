"""
src/sentiment.py
================
中文电影短评的情感分析模块。

方法说明
--------
采用「领域情感词典 + 否定/程度/转折规则」的可解释方案，理由有三：

1. 运行环境无法保证下载 HuggingFace 预训练权重；
2. 每一步判断都可追溯到具体词与规则，便于在报告中解释成因；
3. 最关键：情感判定完全不使用星级作为输入。若用星级训练情感模型，
   再检验「星级与文本是否一致」，偏差必然趋近于零，Q4 将失去意义。

输出字段
--------
sentiment_score      连续情感分 [-1, 1]，正为正面
sentiment_label      pos / neu / neg
sentiment_confidence [0, 1]，由命中词数量与分数绝对值共同决定
sentiment_hits       命中词（前缀「否定」表示被反转），便于人工复核
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from config import NEG_THRESHOLD, POS_THRESHOLD, PROCESSED_DIR, TABLE_DIR
from src.utils import get_logger

logger = get_logger("sentiment")

# ---------------------------------------------------------------------------
# 一、领域情感词典
# ---------------------------------------------------------------------------
# 权重：1.0 一般，1.5 较强，2.0 极强。针对电影短评场景整理。
POSITIVE_WORDS: dict[str, float] = {
    # 总体评价
    "好看": 1.5, "精彩": 1.5, "出色": 1.4, "优秀": 1.4, "完美": 1.6, "经典": 1.3,
    "震撼": 1.6, "惊艳": 1.5, "神作": 1.8, "佳作": 1.4, "杰作": 1.6, "伟大": 1.6,
    "牛逼": 1.5, "牛": 1.0, "厉害": 1.2, "棒": 1.3, "赞": 1.2, "好评": 1.3,
    "满分": 1.5, "力荐": 1.5, "推荐": 1.0, "值得": 1.0, "良心": 1.2,
    "用心": 1.1, "真诚": 1.1, "扎实": 1.0, "耐看": 1.2, "百看不厌": 1.6,
    "回味": 1.1, "教科书": 1.2, "教科书级": 1.4, "有诚意": 1.2,
    # 情绪反应
    "感动": 1.4, "温暖": 1.2, "治愈": 1.4, "动人": 1.3, "催泪": 1.3,
    "泪目": 1.2, "破防": 1.2, "喜欢": 1.1, "喜爱": 1.2, "热爱": 1.3,
    "享受": 1.2, "过瘾": 1.3, "尽兴": 1.2, "带感": 1.2, "上头": 1.1,
    "燃": 1.1, "爽": 1.1, "舒服": 1.0, "美好": 1.2, "温馨": 1.2, "浪漫": 1.1,
    "可爱": 1.0, "有趣": 1.0, "幽默": 1.0, "搞笑": 1.0, "欢乐": 1.1,
    "共鸣": 1.3, "陶醉": 1.2, "沉浸": 1.1, "好玩": 1.0, "出彩": 1.2,
    # 视听与剧作
    "唯美": 1.2, "漂亮": 1.0, "美": 0.8, "细腻": 1.2, "精致": 1.1,
    "深刻": 1.3, "有深度": 1.3, "高级": 1.1, "流畅": 1.0, "紧凑": 1.0,
    "巧妙": 1.2, "聪明": 1.0, "有质感": 1.1, "有味道": 1.0, "大气": 1.1,
    "厚重": 1.0, "饱满": 1.0, "立体": 0.9, "鲜活": 1.1, "生动": 1.1,
    "自然": 0.9, "真实": 1.0, "克制": 0.9, "高级感": 1.2, "氛围感": 1.0,
    "一枝独秀": 1.2, "独树一帜": 1.3, "亮眼": 1.1, "叫绝": 1.4,
    "叹为观止": 1.6, "值回票价": 1.3, "大饱眼福": 1.3,
    "敬佩": 1.1, "佩服": 1.0, "钦佩": 1.1, "叹服": 1.3, "服气": 1.0,
    "五体投地": 1.5, "跪了": 1.2, "心服口服": 1.3,
    # 网络用语
    "yyds": 1.5, "绝了": 1.3, "封神": 1.5, "神了": 1.4, "爱了": 1.2,
    "心动": 1.1, "awsl": 1.2,
}

NEGATIVE_WORDS: dict[str, float] = {
    # 总体评价
    "难看": 1.5, "糟糕": 1.4, "差劲": 1.4, "烂": 1.5, "垃圾": 1.8, "稀烂": 1.8,
    "失败": 1.3, "失望": 1.4, "遗憾": 1.0, "可惜": 0.9, "后悔": 1.2,
    "浪费时间": 1.6, "不值": 1.3, "平庸": 1.2, "俗套": 1.1, "老套": 1.1,
    "无聊": 1.4, "乏味": 1.3, "沉闷": 1.3, "拖沓": 1.3, "冗长": 1.3,
    "混乱": 1.2, "尴尬": 1.3, "做作": 1.3, "浮夸": 1.2, "虚伪": 1.2,
    "生硬": 1.2, "牵强": 1.2, "单薄": 1.1, "空洞": 1.2, "肤浅": 1.2,
    "幼稚": 1.1, "低幼": 1.1, "狗血": 1.2, "无脑": 1.3, "烂尾": 1.5,
    "崩": 1.2, "崩坏": 1.4, "拉胯": 1.4, "翻车": 1.4, "尬": 1.1,
    "出戏": 1.2, "跳戏": 1.2, "油腻": 1.1, "烂片": 1.6, "过誉": 1.3,
    "名不副实": 1.4, "吹过头": 1.4, "粗制滥造": 1.6, "敷衍": 1.4,
    "草率": 1.2, "糊弄": 1.4, "用力过猛": 1.3, "套路": 0.9, "流水线": 1.1,
    "圈钱": 1.4, "乏善可陈": 1.3, "味同嚼蜡": 1.4, "如坐针毡": 1.4,
    "不忍直视": 1.4, "惨不忍睹": 1.5, "不知所云": 1.4, "莫名其妙": 1.2,
    "白开水": 1.1, "平淡": 0.8, "温吞": 1.0, "没意思": 1.3, "无感": 1.2,
    # 情绪反应
    "讨厌": 1.3, "反感": 1.3, "厌恶": 1.5, "恶心": 1.6, "难受": 1.2,
    "压抑": 1.0, "沉重": 0.8, "痛苦": 1.2, "煎熬": 1.2, "折磨": 1.3,
    "看不下去": 1.5, "看不进去": 1.4, "无语": 1.1, "离谱": 1.2,
    "不适": 1.1, "生理不适": 1.5, "反胃": 1.5, "尴尬癌": 1.3, "闷": 1.0,
    # 剧作与制作
    "逻辑漏洞": 1.3, "漏洞百出": 1.4, "毫无逻辑": 1.5, "故弄玄虚": 1.3,
    "装腔作势": 1.3, "画蛇添足": 1.2, "虎头蛇尾": 1.3, "高开低走": 1.3,
    "刻意": 1.1, "煽情": 0.9, "做戏": 1.1, "端着": 1.1, "面瘫": 1.3,
    # 网络用语
    "劝退": 1.3, "辣眼睛": 1.4, "毁三观": 1.4, "年度最差": 1.7,
    "不敢恭维": 1.3, "一言难尽": 1.2,
}

# 否定词。注意两点：
# 1) 「非常」「无比」中的「非」「无」是程度强调而非否定，故单字「无」「非」不入表；
# 2) 「两小无猜」等成语中的「无」不构成否定，由白名单处理。
NEGATIONS: tuple[str, ...] = (
    "不", "没", "没有", "未", "别", "莫", "勿", "甭",
    "毫无", "并未", "不是", "不算", "称不上", "谈不上", "难以", "无法",
    "不怎么", "不太", "不够", "并不", "毫不", "从未", "绝不", "不要", "不会",
)

# 程度强调词：出现在否定窗口内时应取消否定判定
EMPHASIS_OVERRIDE: tuple[str, ...] = (
    "非常", "无比", "无与伦比", "非一般", "不得了", "不行", "不要太好",
)

# 含「无」「不」但不表否定的成语或固定搭配
IDIOM_WHITELIST: tuple[str, ...] = (
    "两小无猜", "无一遗漏", "无厘头", "无所谓", "无处不在", "无与伦比",
    "无可奈何", "一事无成", "不知不觉", "不由", "不禁", "忍不住",
    "恨不得", "了不起", "对不起", "说不定",
)

DEGREE_WORDS: dict[str, float] = {
    "极其": 1.8, "极度": 1.8, "非常": 1.7, "特别": 1.6, "十分": 1.6,
    "格外": 1.5, "相当": 1.5, "无比": 1.7, "万分": 1.7, "太": 1.6,
    "超": 1.5, "巨": 1.5, "贼": 1.4, "真": 1.3, "很": 1.4, "挺": 1.2,
    "蛮": 1.2, "最": 1.5, "更": 1.2, "尤其": 1.4, "实在": 1.3,
}

TURN_WORDS: tuple[str, ...] = ("但是", "但", "然而", "不过", "可是", "却", "只是", "可惜")
SENT_SPLIT = re.compile(r"[。！？!?；;\n]+")

_MAX_WORD_LEN = max(
    max(len(w) for w in POSITIVE_WORDS),
    max(len(w) for w in NEGATIVE_WORDS),
)


# ---------------------------------------------------------------------------
# 二、核心逻辑
# ---------------------------------------------------------------------------
def _scan_lexicon(text: str) -> list[tuple[int, str, float, int]]:
    """
    在文本中做最长匹配扫描，返回命中的情感词及位置与极性。

    最长优先匹配可避免「不错」被「错」误判、「不喜欢」被「喜欢」误判
    这类典型的子串错误。

    参数:
        text: 待扫描文本。

    返回:
        (位置, 词, 权重, 极性) 列表，极性 +1 正面，-1 负面。
    """
    hits: list[tuple[int, str, float, int]] = []
    i, n = 0, len(text)
    while i < n:
        matched = False
        for length in range(min(_MAX_WORD_LEN, n - i), 0, -1):
            piece = text[i : i + length]
            if piece in POSITIVE_WORDS:
                hits.append((i, piece, POSITIVE_WORDS[piece], 1))
                i += length
                matched = True
                break
            if piece in NEGATIVE_WORDS:
                hits.append((i, piece, NEGATIVE_WORDS[piece], -1))
                i += length
                matched = True
                break
        if not matched:
            i += 1
    return hits


def _has_negation(prefix: str) -> bool:
    """
    判断情感词之前的片段是否构成否定。

    依次排除三类误判：成语白名单、程度强调词、双重否定。

    参数:
        prefix: 情感词之前的有限窗口文本。

    返回:
        True 表示应反转极性。
    """
    if not prefix:
        return False
    if any(idiom in prefix for idiom in IDIOM_WHITELIST):
        return False
    if any(emp in prefix for emp in EMPHASIS_OVERRIDE):
        return False
    if sum(prefix.count(n) for n in ("不", "没", "未")) >= 2:
        return False
    return any(neg in prefix for neg in NEGATIONS)


def _degree_factor(prefix: str) -> float:
    """返回情感词前片段中程度副词带来的强度系数（取最大值）。"""
    factor = 1.0
    for word, val in DEGREE_WORDS.items():
        if word in prefix:
            factor = max(factor, val)
    return factor


def analyze_text(text: str, use_fallback: bool = True) -> dict:
    """
    对单条评论做情感判定。

    评分流程：
    1. 按标点分句，转折词之后的句子权重 ×1.5（用户常在前半段铺垫、后半段下结论）；
    2. 每个情感词做否定检查（前 3 字窗口）与程度放大；
    3. 句子得分累加后用 tanh 压缩到 [-1, 1]，避免长文本分数爆炸；
    4. 依据阈值划分 pos/neu/neg。

    回退机制（改进点）
    -----------------
    词典法的主要短板是「未命中任何情感词」——大量靠具体名词与叙述表达态度的
    评论（如「吴镇宇一枝独秀」「每次都会哭着看完」）拿不到分数，导致一致性
    分析里出现大量「无法判定」样本。开启 use_fallback 后，未命中的文本改用
    朴素贝叶斯情感库（snownlp）做极端值判定：只有其极性分高于 0.80 或低于
    0.20 时才给出 pos/neg，其余仍判中性。这样既补上了部分覆盖，
    又避免其在中性区间的低区分度污染结果。

    参数:
        text: 已清洗的评论文本。
        use_fallback: 词典未命中时是否启用朴素贝叶斯回退。

    返回:
        含 score/label/confidence/hits/method 的字典。
    """
    empty = {
        "sentiment_score": 0.0,
        "sentiment_label": "neu",
        "sentiment_confidence": 0.0,
        "sentiment_hits": "",
        "sentiment_method": "none",
    }
    if not isinstance(text, str) or not text.strip():
        return empty

    sentences = [s for s in SENT_SPLIT.split(text) if s.strip()]
    if not sentences:
        return empty

    total = 0.0
    hit_words: list[str] = []
    n_hits = 0

    for sent in sentences:
        hits = _scan_lexicon(sent)
        if not hits:
            continue

        turn_pos = -1
        for tw in TURN_WORDS:
            p = sent.find(tw)
            if p != -1 and (turn_pos == -1 or p < turn_pos):
                turn_pos = p
        sent_weight = 1.5 if turn_pos != -1 else 1.0

        sent_score = 0.0
        for pos, word, weight, polarity in hits:
            prefix = sent[max(0, pos - 3) : pos]
            value = weight * polarity
            if _has_negation(prefix):
                value = -value * 0.9
            value *= _degree_factor(prefix)
            sent_score += value
            hit_words.append(("否定" if value < 0 else "") + word)
            n_hits += 1

        total += sent_score * sent_weight

    if n_hits == 0:
        if use_fallback:
            return _fallback_predict(text)
        return empty

    normalized = total / math.sqrt(n_hits + 1)
    score = math.tanh(normalized / 1.6)

    if score >= POS_THRESHOLD:
        label = "pos"
    elif score <= NEG_THRESHOLD:
        label = "neg"
    else:
        label = "neu"

    confidence = min(1.0, abs(score) * 0.7 + min(n_hits, 8) / 8 * 0.3)

    return {
        "sentiment_score": round(float(score), 4),
        "sentiment_label": label,
        "sentiment_confidence": round(float(confidence), 4),
        "sentiment_hits": "|".join(dict.fromkeys(hit_words))[:120],
        "sentiment_method": "lexicon",
    }


def _fallback_predict(text: str) -> dict:
    """
    词典未命中时的回退判定：用朴素贝叶斯情感库做极端值判断。

    仅在极性分极端（>0.80 或 <0.20）时给出方向，其余判为中性。
    置信度按偏离 0.5 的幅度折算，刻意压低以标记其为「弱证据」。

    参数:
        text: 评论文本。

    返回:
        与 analyze_text 同结构的字典，method 标记为 fallback。
    """
    try:
        from snownlp import SnowNLP

        p = float(SnowNLP(text).sentiments)
    except Exception:
        return {
            "sentiment_score": 0.0, "sentiment_label": "neu",
            "sentiment_confidence": 0.0, "sentiment_hits": "",
            "sentiment_method": "none",
        }

    if p > 0.80:
        label, score = "pos", (p - 0.5) * 1.2
    elif p < 0.20:
        label, score = "neg", -(0.5 - p) * 1.2
    else:
        label, score = "neu", 0.0

    score = max(-1.0, min(1.0, score))
    # 弱证据：置信度上限 0.45，确保它低于词典法的典型置信度
    confidence = min(0.45, abs(p - 0.5) * 0.9) if label != "neu" else 0.0

    return {
        "sentiment_score": round(float(score), 4),
        "sentiment_label": label,
        "sentiment_confidence": round(float(confidence), 4),
        "sentiment_hits": f"fallback:{p:.2f}",
        "sentiment_method": "fallback",
    }


def run_sentiment() -> dict:
    """
    对 A、B 两类评论（可纳入情感统计者）执行情感分析。

    输入: data/processed/reviews_labeled.csv
    输出: data/processed/reviews_scored.csv

    返回:
        含样本量与标签分布的统计字典。
    """
    path = PROCESSED_DIR / "reviews_labeled.csv"
    if not path.exists():
        raise FileNotFoundError(f"未找到分级结果: {path}，请先运行 src.quality_classification")

    df = pd.read_csv(path, dtype={"movie_id": str, "review_id": str})
    df["clean_text"] = df["clean_text"].fillna("")

    mask = df["quality_label"].isin(["A", "B"])
    res = pd.DataFrame(
        [analyze_text(t) for t in df.loc[mask, "clean_text"]],
        index=df.index[mask],
    )

    for col in ["sentiment_score", "sentiment_confidence"]:
        df[col] = np.nan
    for col in ["sentiment_label", "sentiment_hits", "sentiment_method"]:
        df[col] = ""
    for col in res.columns:
        df.loc[res.index, col] = res[col]

    df.to_csv(PROCESSED_DIR / "reviews_scored.csv", index=False, encoding="utf-8-sig")

    valid = df[df["quality_label"] == "A"]
    dist = valid["sentiment_label"].value_counts().to_dict()

    stats = {
        "analyzed": int(mask.sum()),
        "a_class": int(len(valid)),
        "distribution_a": dist,
        "mean_score_a": round(float(valid["sentiment_score"].mean()), 4),
        "method": "领域情感词典 + 否定/程度/转折规则",
    }
    logger.info(
        "情感分析完成：%d 条，A 类分布 %s，均值 %.3f",
        stats["analyzed"], dist, stats["mean_score_a"],
    )
    return stats


def evaluate_sentiment() -> dict:
    """
    以人工标注的 human_sentiment 为基准评估情感分类效果。

    输入: data/processed/manual_validation.csv
    输出: outputs/tables/sentiment_eval_*.csv

    返回:
        含准确率、分项指标与混淆矩阵的字典。
    """
    from sklearn.metrics import (
        accuracy_score, confusion_matrix, precision_recall_fscore_support,
    )

    path = PROCESSED_DIR / "manual_validation.csv"
    if not path.exists():
        logger.warning("未找到人工验证集，跳过情感评估")
        return {"error": "no_validation_set"}

    df = pd.read_csv(path, dtype={"review_id": str})
    df = df[
        df["human_sentiment"].notna()
        & (df["human_sentiment"].astype(str).str.strip() != "")
    ]
    if df.empty:
        logger.warning("人工情感标注为空，跳过评估")
        return {"error": "no_human_sentiment"}

    y_pred = [
        analyze_text(t, use_fallback=True)["sentiment_label"]
        for t in df["clean_text"].fillna("")
    ]
    y_true = df["human_sentiment"].astype(str).str.strip().tolist()

    labels = ["pos", "neu", "neg"]
    acc = accuracy_score(y_true, y_pred)
    p, r, f1, sup = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=labels)

    per = pd.DataFrame(
        {
            "情感": labels,
            "精确率": np.round(p, 4),
            "召回率": np.round(r, 4),
            "F1": np.round(f1, 4),
            "样本数": sup,
        }
    )
    per.to_csv(TABLE_DIR / "sentiment_eval_by_class.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(cm, index=labels, columns=labels).to_csv(
        TABLE_DIR / "sentiment_eval_confusion.csv", encoding="utf-8-sig"
    )
    pd.DataFrame(
        [
            {"指标": "样本量", "数值": len(df)},
            {"指标": "总体准确率", "数值": round(float(acc), 4)},
            {"指标": "宏平均F1", "数值": round(float(np.mean(f1)), 4)},
        ]
    ).to_csv(TABLE_DIR / "sentiment_eval_overall.csv", index=False, encoding="utf-8-sig")

    logger.info("情感评估完成：n=%d，准确率 %.2f%%", len(df), acc * 100)
    return {
        "n": int(len(df)),
        "accuracy": round(float(acc), 4),
        "macro_f1": round(float(np.mean(f1)), 4),
        "per_class": per.to_dict(orient="records"),
        "confusion_matrix": cm.tolist(),
    }


if __name__ == "__main__":
    import json

    _result = run_sentiment()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
