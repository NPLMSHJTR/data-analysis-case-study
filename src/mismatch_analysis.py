"""
src/mismatch_analysis.py
========================
Q4：短评星级与文本情感偏差的系统性分析。

不一致程度的数值定义
--------------------
    star_norm = (rating - 3) / 2        1星=-1, 3星=0, 5星=+1
    gap       = star_norm - sentiment_score
    abs_gap   = |gap| / 2               归一到 [0, 1]

gap > 0 表示星级高于文本情感（打的分比写的字更正面）
gap < 0 表示星级低于文本情感

四类重点样本（对应任务书的四种情况）
----------------------------------
1. 高星级 + 负面文字（≥4 星，文本判负）
2. 低星级 + 正面文字（≤2 星，文本判正）
3. 三星 + 极端正面文字（3 星，情感分 ≥ 0.6）
4. 三星 + 极端负面文字（3 星，情感分 ≤ −0.6）

系统性偏差的判定
----------------
不只看 20 条例子，而是计算：
- 星级与情感分的 Pearson / Spearman 相关
- 各星级内部的情感构成
- 两个方向上不一致发生率是否对称
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from config import PROCESSED_DIR, TABLE_DIR
from src.utils import get_logger

logger = get_logger("mismatch")

STAR_LABEL = {1: "很差", 2: "较差", 3: "还行", 4: "推荐", 5: "力荐"}

# 明显不一致的门槛（与一致性模块保持一致）
ABS_GAP_THRESHOLD = 0.55
MIN_CONFIDENCE = 0.25


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算星级归一值、差距与不一致度。

    参数:
        df: 含 rating 与 sentiment_score 的评论表。

    返回:
        追加 star_norm / gap / abs_gap 的表，已剔除缺失值。
    """
    out = df.copy()
    out["rating"] = pd.to_numeric(out["rating"], errors="coerce")
    out["sentiment_score"] = pd.to_numeric(out["sentiment_score"], errors="coerce")
    out["sentiment_confidence"] = pd.to_numeric(
        out["sentiment_confidence"], errors="coerce"
    )
    out = out.dropna(subset=["rating", "sentiment_score", "sentiment_confidence"])

    out["star_norm"] = (out["rating"] - 3) / 2
    out["gap"] = out["star_norm"] - out["sentiment_score"]
    out["abs_gap"] = (out["gap"].abs() / 2).round(4)
    return out


def run_mismatch_analysis() -> dict:
    """
    执行 Q4 的统计分析与四类样本抽取。

    输出:
        outputs/tables/q4_correlation.csv
        outputs/tables/q4_star_sentiment_distribution.csv
        outputs/tables/q4_mismatch_rates.csv
        outputs/tables/q4_cases_pool.csv（候选池，供人工复核）

    返回:
        含相关系数、交叉构成、发生率与候选样本的字典。
    """
    path = PROCESSED_DIR / "reviews_dual.csv"
    if not path.exists():
        raise FileNotFoundError(f"未找到双维度结果: {path}")

    df = pd.read_csv(path, dtype={"movie_id": str, "review_id": str})
    # 只在 A 类（有效内容）且非严重矛盾的样本上做一致性研究
    df = df[df["quality_label"] == "A"].copy()
    df = prepare(df)
    logger.info("参与 Q4 分析的有效评论：%d 条", len(df))

    # --- 1. 相关系数 ---------------------------------------------------
    pearson_r, pearson_p = stats.pearsonr(df["rating"], df["sentiment_score"])
    spearman_r, spearman_p = stats.spearmanr(df["rating"], df["sentiment_score"])

    corr = pd.DataFrame(
        [
            {"方法": "Pearson（星级 vs 情感分）",
             "系数": round(float(pearson_r), 4), "p值": float(f"{pearson_p:.3g}")},
            {"方法": "Spearman（星级 vs 情感分）",
             "系数": round(float(spearman_r), 4), "p值": float(f"{spearman_p:.3g}")},
        ]
    )
    corr.to_csv(TABLE_DIR / "q4_correlation.csv", index=False, encoding="utf-8-sig")

    # --- 2. 各星级的情感构成 -------------------------------------------
    cross = pd.crosstab(df["rating"], df["sentiment_label"])
    cross = cross.reindex(columns=["pos", "neu", "neg"], fill_value=0).fillna(0).astype(int)
    cross.to_csv(TABLE_DIR / "q4_star_sentiment_counts.csv", encoding="utf-8-sig")

    share = (cross.div(cross.sum(axis=1).replace(0, np.nan), axis=0) * 100).round(2)
    share_out = share.copy()
    share_out.columns = ["正面占比%", "中性占比%", "负面占比%"]
    share_out.index.name = "星级"
    share_out.reset_index().to_csv(
        TABLE_DIR / "q4_star_sentiment_distribution.csv",
        index=False, encoding="utf-8-sig",
    )

    # --- 3. 两个方向的发生率 -------------------------------------------
    high = df[df["rating"] >= 4]
    low = df[df["rating"] <= 2]
    high_neg = high[high["sentiment_label"] == "neg"]
    low_pos = low[low["sentiment_label"] == "pos"]

    rates = pd.DataFrame(
        [
            {"指标": "四星及以上评论数", "数值": len(high),
             "占比": round(len(high) / len(df), 4)},
            {"指标": "其中文本判为负面（高星低情感）", "数值": len(high_neg),
             "占比": round(len(high_neg) / max(1, len(high)), 4)},
            {"指标": "二星及以下评论数", "数值": len(low),
             "占比": round(len(low) / len(df), 4)},
            {"指标": "其中文本判为正面（低星高情感）", "数值": len(low_pos),
             "占比": round(len(low_pos) / max(1, len(low)), 4)},
            {"指标": "满足明显不一致门槛的评论数",
             "数值": int(((df["abs_gap"] >= ABS_GAP_THRESHOLD)
                          & (df["sentiment_confidence"] >= MIN_CONFIDENCE)).sum()),
             "占比": round(float(((df["abs_gap"] >= ABS_GAP_THRESHOLD)
                                  & (df["sentiment_confidence"] >= MIN_CONFIDENCE)).mean()), 4)},
        ]
    )
    rates.to_csv(TABLE_DIR / "q4_mismatch_rates.csv", index=False, encoding="utf-8-sig")

    # --- 4. 四类重点样本池 ---------------------------------------------
    def _pick(mask: pd.Series, n: int, tag: str) -> pd.DataFrame:
        sub = df[mask & (df["sentiment_confidence"] >= MIN_CONFIDENCE)].copy()
        sub = sub.sort_values("abs_gap", ascending=False)
        # 同片最多取 1 条，保证样本分散
        sub = sub.groupby("movie_name", group_keys=False).head(2).head(n)
        sub["case_type"] = tag
        return sub

    # 候选池刻意放宽：每类多抽，同片允许 2 条。
    # 目的是给人工复核留足选择空间——最终 20 条由 mismatch_cases 模块按
    # 具体片名与文本前缀定位，因此池子必须覆盖足够多的候选。
    pools = [
        _pick((df["rating"] >= 4) & (df["sentiment_label"] == "neg"), 40, "高星负面"),
        _pick((df["rating"] <= 2) & (df["sentiment_label"] == "pos"), 40, "低星正面"),
        _pick((df["rating"] == 3) & (df["sentiment_score"] >= 0.60), 15, "三星极端正面"),
        _pick((df["rating"] == 3) & (df["sentiment_score"] <= -0.60), 15, "三星极端负面"),
    ]
    pool = pd.concat([p for p in pools if len(p)], ignore_index=True)
    cols = ["case_type", "movie_name", "rating", "review_text", "sentiment_label",
            "sentiment_score", "sentiment_confidence", "gap", "abs_gap",
            "sentiment_hits", "review_id"]
    pool = pool[[c for c in cols if c in pool.columns]]
    pool.to_csv(TABLE_DIR / "q4_cases_pool.csv", index=False, encoding="utf-8-sig")

    result = {
        "n_reviews": int(len(df)),
        "pearson_r": round(float(pearson_r), 4),
        "pearson_p": float(f"{pearson_p:.3g}"),
        "spearman_r": round(float(spearman_r), 4),
        "spearman_p": float(f"{spearman_p:.3g}"),
        "high_star_neg": int(len(high_neg)),
        "high_star_neg_rate": round(len(high_neg) / max(1, len(high)), 4),
        "low_star_pos": int(len(low_pos)),
        "low_star_pos_rate": round(len(low_pos) / max(1, len(low)), 4),
        "asymmetry_ratio": round(
            (len(low_pos) / max(1, len(low))) / max(1e-9, len(high_neg) / max(1, len(high))), 2
        ),
        "star_sentiment_share": share.to_dict(),
        "pool_size": int(len(pool)),
        "pool_by_type": pool["case_type"].value_counts().to_dict(),
    }

    logger.info(
        "Q4 完成：Pearson r=%.3f，高星负面 %d 条（%.2f%%），低星正面 %d 条（%.2f%%）",
        pearson_r, len(high_neg), result["high_star_neg_rate"] * 100,
        len(low_pos), result["low_star_pos_rate"] * 100,
    )
    return result


if __name__ == "__main__":
    import json

    _result = run_mismatch_analysis()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
