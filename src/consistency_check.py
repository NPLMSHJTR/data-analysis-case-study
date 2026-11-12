"""
src/consistency_check.py
========================
双维度评价体系（第二维度）：星级与文本情感的一致性判定。

问题背景
--------
只判断「评论有没有内容」是不够的。一条五星评论可能写着「剧情无聊，浪费时间」，
一条一星评论可能写着「叙事结构混乱，人物动机缺乏铺垫，后半段拖沓」。
后者的文字其实是对影片的有效批评，属于有价值的内容；
前者则构成评分与文字的逻辑矛盾。

因此本项目在「内容有效性」之外增加第二个维度，形成处理矩阵。

星级归一与不一致度
------------------
    star_norm = (rating - 3) / 2        1星=-1, 3星=0, 5星=+1
    gap       = star_norm - sentiment_score
    abs_gap   = |gap|

判定四档（阈值见 config）：
    一致         abs_gap < 0.55
    轻度不一致   0.55 ≤ abs_gap < 1.10
    严重矛盾     abs_gap ≥ 1.10
    无法判定     情感置信度 < 0.25（模型本身没把握，不参与一致性统计）

双维度处理矩阵
--------------
| 内容有效性 | 一致性     | 最终处理                         |
|-----------|-----------|----------------------------------|
| A         | 一致       | 进入内容分析与情感统计            |
| A         | 轻度不一致  | 进入内容分析，标记不一致，情感统计单独看 |
| A         | 严重矛盾    | 保留原始记录，不进入一致性统计，单独成表 |
| B         | 任意       | 仅进入整体情感统计，不进入内容分析 |
| C         | 任意       | 剔除                              |
| D         | 任意       | 标记疑似异常，不进入统计           |
| E         | 任意       | 待人工判断，不进入统计            |
| X         | 任意       | 剔除                              |

特别处理：低星 + 客观批评
------------------------
一星评论如果写的是「叙事混乱、动机缺乏铺垫、节奏拖沓」，
这属于情况二「差评但内容客观指出不足」，是有价值的批评性评论，
必须纳入有效评论，不能因低星就当脏数据。
本模块通过「是否含电影要素词」识别这类评论，并单独统计其数量。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import (
    CONSISTENCY_SEVERE_GAP,
    CONSISTENCY_TOLERANT_GAP,
    MIN_CONFIDENCE_FOR_CONSISTENCY,
    PROCESSED_DIR,
    TABLE_DIR,
)
from src.quality_classification import has_film_aspect
from src.utils import get_logger

logger = get_logger("consistency")

CONSISTENCY_LABELS = ["一致", "轻度不一致", "严重矛盾", "无法判定"]


def star_to_norm(rating) -> float:
    """
    把 1—5 星线性映射到 [-1, 1]。

    参数:
        rating: 星级，可为数值或字符串。

    返回:
        归一值；无法解析时返回 NaN。
    """
    try:
        r = float(rating)
    except (TypeError, ValueError):
        return float("nan")
    if not 1 <= r <= 5:
        return float("nan")
    return (r - 3) / 2


def label_consistency(gap: float, confidence: float) -> tuple[str, str]:
    """
    依据差距与置信度给出一致性标签与说明。

    参数:
        gap: star_norm - sentiment_score。
        confidence: 情感判定置信度。

    返回:
        (一致性标签, 说明) 二元组。
    """
    if not np.isfinite(gap):
        return "无法判定", "星级或情感分缺失"
    if not np.isfinite(confidence) or confidence < MIN_CONFIDENCE_FOR_CONSISTENCY:
        return "无法判定", "情感判定置信度过低，不参与一致性统计"

    a = abs(gap)
    if a < CONSISTENCY_TOLERANT_GAP:
        return "一致", "星级与文本情感方向相符"
    if a < CONSISTENCY_SEVERE_GAP:
        return "轻度不一致", "星级与文本情感存在可见差异"
    return "严重矛盾", "星级与文本情感方向明显相反"


def build_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算星级归一值、差距与一致性标签。

    参数:
        df: 含 rating / sentiment_score / sentiment_confidence / quality_label 的表。

    返回:
        追加 star_norm / gap / abs_gap / consistency 列的新表。
    """
    out = df.copy()
    out["rating"] = pd.to_numeric(out["rating"], errors="coerce")
    out["sentiment_score"] = pd.to_numeric(out["sentiment_score"], errors="coerce")
    out["sentiment_confidence"] = pd.to_numeric(
        out["sentiment_confidence"], errors="coerce"
    )

    out["star_norm"] = out["rating"].map(star_to_norm)
    out["gap"] = out["star_norm"] - out["sentiment_score"]
    out["abs_gap"] = out["gap"].abs()

    pairs = [
        label_consistency(g, c)
        for g, c in zip(out["gap"], out["sentiment_confidence"].fillna(0))
    ]
    out["consistency"] = [p[0] for p in pairs]
    out["consistency_reason"] = [p[1] for p in pairs]
    return out


def apply_dual_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    依据双维度处理矩阵给出每条评论的最终处置方式。

    处置取值：
        content       进入内容分析（A 且不严重矛盾）
        sentiment     进入情感统计（A/B）
        mismatch_only 仅进入矛盾样本表（A 且严重矛盾）
        excluded      完全排除（C/D/E/X）
        manual        待人工判断（一致性为「无法判定」但内容有效）

    参数:
        df: 已含 quality_label 与 consistency 的表。

    返回:
        追加 disposition 列的表。
    """
    out = df.copy()

    def _decide(row) -> str:
        q = row["quality_label"]
        c = row["consistency"]
        if q not in ("A", "B"):
            return "excluded"
        if c == "无法判定":
            return "manual" if q == "A" else "sentiment"
        if q == "B":
            return "sentiment"
        if c == "严重矛盾":
            return "mismatch_only"
        return "content"

    out["disposition"] = out.apply(_decide, axis=1)
    return out


def run_consistency_check() -> dict:
    """
    执行一致性判定并写出双维度结果表。

    输入: data/processed/reviews_scored.csv
    输出: data/processed/reviews_dual.csv
          outputs/tables/consistency_matrix.csv（双维度交叉计数）
          outputs/tables/consistency_by_star.csv（各星级的一致性构成）

    返回:
        含各一致性档位计数、严重矛盾数、低星客观批评数的字典。
    """
    path = PROCESSED_DIR / "reviews_scored.csv"
    if not path.exists():
        raise FileNotFoundError(f"未找到情感结果: {path}，请先运行 src.sentiment")

    df = pd.read_csv(path, dtype={"movie_id": str, "review_id": str})
    df["clean_text"] = df["clean_text"].fillna("")

    # 只在可纳入情感统计的评论上判定一致性
    scored = df[df["quality_label"].isin(["A", "B"])].copy()
    scored = build_matrix(scored)

    # 合并回全量
    for col in ["star_norm", "gap", "abs_gap", "consistency", "consistency_reason"]:
        df[col] = np.nan if col in ("star_norm", "gap", "abs_gap") else ""
    for col in ["star_norm", "gap", "abs_gap", "consistency", "consistency_reason"]:
        df.loc[scored.index, col] = scored[col]

    df["consistency"] = df["consistency"].fillna("")
    df = apply_dual_matrix(df)

    df.to_csv(PROCESSED_DIR / "reviews_dual.csv", index=False, encoding="utf-8-sig")

    # --- 双维度交叉表 -------------------------------------------------
    a_b = df[df["quality_label"].isin(["A", "B"])]
    cross = pd.crosstab(a_b["quality_label"], a_b["consistency"])
    cross = cross.reindex(
        index=["A", "B"], columns=CONSISTENCY_LABELS, fill_value=0
    ).fillna(0).astype(int)
    cross.to_csv(TABLE_DIR / "consistency_matrix.csv", encoding="utf-8-sig")

    # --- 各星级的一致性构成 -------------------------------------------
    by_star = pd.crosstab(df["rating"], df["consistency"])
    by_star = by_star.reindex(columns=CONSISTENCY_LABELS, fill_value=0).fillna(0).astype(int)
    by_star.to_csv(TABLE_DIR / "consistency_by_star.csv", encoding="utf-8-sig")

    # --- 严重矛盾样本 -------------------------------------------------
    severe = df[(df["quality_label"] == "A") & (df["consistency"] == "严重矛盾")].copy()
    severe.to_csv(
        PROCESSED_DIR / "severe_mismatch_pool.csv", index=False, encoding="utf-8-sig"
    )

    # --- 低星客观批评（情况二）----------------------------------------
    # 低星（≤2）但文本含电影要素词，说明用户在具体指出缺点
    low_star = df[(df["quality_label"] == "A") & (df["rating"] <= 2)].copy()
    low_star["is_objective_critique"] = low_star["clean_text"].map(has_film_aspect)
    n_critique = int(low_star["is_objective_critique"].sum())
    low_star[low_star["is_objective_critique"]].to_csv(
        PROCESSED_DIR / "low_star_critique.csv", index=False, encoding="utf-8-sig"
    )

    counts = df["consistency"].value_counts().to_dict()
    disp = df["disposition"].value_counts().to_dict()

    stats = {
        "total": int(len(df)),
        "consistency_counts": counts,
        "disposition_counts": disp,
        "severe_mismatch": int(len(severe)),
        "low_star_total": int(len(low_star)),
        "low_star_objective_critique": n_critique,
        "low_star_critique_rate": round(n_critique / len(low_star), 4) if len(low_star) else 0,
        "high_star_negative": int(
            (
                (df["rating"] >= 4)
                & (df["quality_label"] == "A")
                & (df["sentiment_label"] == "neg")
            ).sum()
        ),
        "low_star_positive": int(
            (
                (df["rating"] <= 2)
                & (df["quality_label"] == "A")
                & (df["sentiment_label"] == "pos")
            ).sum()
        ),
    }
    logger.info(
        "一致性判定完成：一致 %d，轻度不一致 %d，严重矛盾 %d，无法判定 %d；"
        "低星客观批评 %d 条",
        counts.get("一致", 0), counts.get("轻度不一致", 0),
        counts.get("严重矛盾", 0), counts.get("无法判定", 0), n_critique,
    )
    return stats


if __name__ == "__main__":
    import json

    _result = run_consistency_check()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
