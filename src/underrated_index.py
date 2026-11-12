"""
src/underrated_index.py
=======================
Q3：构建可解释的「被低估指数」并给出排名。

原始公式（老师给出的基础方法）
------------------------------
    U = 0.50 × Z(S − R) + 0.30 × Z(H) − 0.20 × Z(P)

原始方法的两个问题（本项目的改进点）
-----------------------------------
问题一：R 的尺度不匹配
    把 10 分制评分线性映射到 [−1, 1]（9.5 分 → +0.9）后，
    中文短评的平均情感分通常只有 0.2—0.4，很难达到 0.9。
    结果是所有高分影片的 S − R 必然为负，
    指数退化为「评分越高越被高估」的机械结论，失去区分力。
改进：S 与 R 各自做样本内 Z 分数标准化后再相减，
    比较发生在「排名」层面而非「绝对刻度」层面。
    同时保留原始刻度差 gap_raw 供读者直观核对，但不参与计算。

问题二：H 不可得
    原设 H 为「有用率 = 有用数 /（有用数 + 没用数）」，
    本项目使用的公开数据集只提供有用数，无没用数。
    按任务书「不得编造」的要求，重新定义为：
        H = Z( ln(1 + 该片有效评论的平均有用数) )
    该指标衡量「既有评论被其他用户认可的程度」，与原意一致但粒度更粗：
    无法区分高赞与高踩，也无法排除时间累积效应（早期评论天然易获赞）。

第三个改进：有效样本与矛盾样本的隔离
    原方法直接用「全部评论」算 S。本项目只使用 A 类有效评论，
    并剔除被判定为「严重矛盾」的样本（星级与文本方向相反），
    避免自相矛盾的评论污染影片的文本情感均值。

方向说明
--------
U 越高：文本口碑相对评分更占优、评论认同度更高、关注度相对更低，
       即越可能被市场低估。
U 越低：文本情感弱于评分，或关注度过高。
U 只是本研究自定义的相对排序指标，不是豆瓣官方指标，
也不构成对影片质量的最终判断。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import (
    MIN_REVIEWS_FOR_INDEX,
    TABLE_DIR,
    WEIGHT_ATTENTION,
    WEIGHT_SENSITIVITY_GRID,
    WEIGHT_SENTIMENT_GAP,
    WEIGHT_USEFUL,
)
from src.statistics import build_movie_features
from src.utils import get_logger

logger = get_logger("index")


def _zscore(s: pd.Series) -> pd.Series:
    """
    计算 Z 分数；标准差为 0 时返回全零，避免除零。

    参数:
        s: 数值序列。

    返回:
        标准化后的序列。
    """
    sd = s.std(ddof=1)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def compute_index(
    df: pd.DataFrame,
    w_gap: float = WEIGHT_SENTIMENT_GAP,
    w_useful: float = WEIGHT_USEFUL,
    w_attention: float = WEIGHT_ATTENTION,
) -> pd.DataFrame:
    """
    按给定权重计算被低估指数 U。

    参数:
        df: 含 mean_sentiment / douban_rating / H_raw / P_raw 的特征表。
        w_gap: 文本口碑超出量的权重。
        w_useful: 有用性的权重。
        w_attention: 关注度的权重（公式中取负号）。

    返回:
        追加 S_z / R_z / gap / z_* / U / 分项贡献 的表。
    """
    out = df.copy()

    out["S_z"] = _zscore(out["mean_sentiment"])
    out["R_z"] = _zscore(out["douban_rating"])
    out["gap"] = out["S_z"] - out["R_z"]

    out["z_gap"] = _zscore(out["gap"])
    out["z_useful"] = _zscore(out["H_raw"])
    out["z_attention"] = _zscore(out["P_raw"])

    out["U"] = (
        w_gap * out["z_gap"]
        + w_useful * out["z_useful"]
        - w_attention * out["z_attention"]
    )
    out["contrib_gap"] = w_gap * out["z_gap"]
    out["contrib_useful"] = w_useful * out["z_useful"]
    out["contrib_attention"] = -w_attention * out["z_attention"]
    return out


def _reason(row: pd.Series) -> str:
    """
    依据分项贡献生成该影片被低估的主要原因。

    措辞采用「样本内相对比较」的口径，因为决定排名的是分项在同侪中的相对位置。

    参数:
        row: 含分项贡献的影片记录。

    返回:
        简短中文原因说明。
    """
    parts: list[str] = []
    if row["contrib_gap"] > 0.15:
        parts.append("文本情感排名高于评分排名")
    elif row["contrib_gap"] < -0.15:
        parts.append("文本情感排名低于评分排名")

    if row["contrib_attention"] > 0.15:
        parts.append("评分人数在同侪中偏少")
    elif row["contrib_attention"] < -0.15:
        parts.append("评分人数在同侪中偏多")

    if row["contrib_useful"] > 0.15:
        parts.append("评论平均获赞多于同侪")

    return "；".join(parts) if parts else "三项指标接近样本均值"


def run_underrated_index() -> dict:
    """
    执行 Q3 全部计算：指数、前十、三类补充榜单、权重敏感性。

    输出:
        outputs/tables/q3_underrated_top10.csv 等 6 个表

    返回:
        含各榜单与稳健性结论的字典。
    """
    feats = build_movie_features()

    eligible = feats[feats["n_valid"] >= MIN_REVIEWS_FOR_INDEX].copy()
    logger.info(
        "达到 %d 条有效评论门槛的影片：%d 部（全样本 %d 部）",
        MIN_REVIEWS_FOR_INDEX, len(eligible), len(feats),
    )
    if eligible.empty:
        raise ValueError("没有影片达到有效评论门槛，无法计算指数")

    scored = compute_index(eligible)
    scored["reason"] = scored.apply(_reason, axis=1)
    scored = scored.sort_values("U", ascending=False).reset_index(drop=True)
    scored["U_rank"] = range(1, len(scored) + 1)

    # 全量输出（未达门槛者 U 置空）
    full = feats.copy().merge(
        scored[["movie_id", "U", "U_rank", "z_gap", "z_useful", "z_attention",
                "contrib_gap", "contrib_useful", "contrib_attention", "reason"]],
        on="movie_id", how="left",
    )
    full["low_confidence"] = full["n_valid"] < MIN_REVIEWS_FOR_INDEX
    full.to_csv(TABLE_DIR / "q3_underrated_full.csv", index=False, encoding="utf-8-sig")

    # --- 前十名 -------------------------------------------------------
    top10 = scored.head(10).copy()
    top10["sentiment_se"] = top10["std_sentiment"] / np.sqrt(
        top10["n_valid"].clip(lower=1)
    )
    top10_out = top10[
        ["U_rank", "title", "release_year", "main_genre", "douban_rating",
         "rating_count", "n_valid", "mean_sentiment", "sentiment_se",
         "mean_useful", "gap", "gap_raw", "U", "reason"]
    ].rename(
        columns={
            "U_rank": "排名", "title": "电影", "release_year": "上映年份",
            "main_genre": "主类型", "douban_rating": "豆瓣评分",
            "rating_count": "评分人数", "n_valid": "有效评论数",
            "mean_sentiment": "平均文本情感", "sentiment_se": "情感标准误",
            "mean_useful": "平均有用数", "gap": "情感-评分差(标准化)",
            "gap_raw": "情感-评分绝对差", "U": "被低估指数", "reason": "主要原因",
        }
    )
    for c in ["平均文本情感", "情感标准误", "情感-评分差(标准化)",
              "情感-评分绝对差", "被低估指数"]:
        top10_out[c] = top10_out[c].round(4)
    top10_out.to_csv(TABLE_DIR / "q3_underrated_top10.csv", index=False, encoding="utf-8-sig")

    # --- 补充榜单一：高评分但关注度较低 --------------------------------
    r_hi = scored["douban_rating"].quantile(0.60)
    c_lo = scored["rating_count"].quantile(0.40)
    c_hi = scored["rating_count"].quantile(0.60)
    low_attn = (
        scored[(scored["douban_rating"] >= r_hi) & (scored["rating_count"] <= c_lo)]
        .sort_values(["douban_rating", "rating_count"], ascending=[False, True])
        .head(10)
    )
    low_attn[
        ["title", "release_year", "main_genre", "douban_rating", "rating_count",
         "n_valid", "mean_sentiment"]
    ].rename(columns={
        "title": "电影", "release_year": "上映年份", "main_genre": "主类型",
        "douban_rating": "豆瓣评分", "rating_count": "评分人数",
        "n_valid": "有效评论数", "mean_sentiment": "平均文本情感",
    }).to_csv(TABLE_DIR / "q3_high_rating_low_attention.csv",
              index=False, encoding="utf-8-sig")

    # --- 补充榜单二：高评分且高关注度 ----------------------------------
    high_attn = (
        scored[(scored["douban_rating"] >= r_hi) & (scored["rating_count"] >= c_hi)]
        .sort_values(["douban_rating", "rating_count"], ascending=False)
        .head(10)
    )
    high_attn[
        ["title", "release_year", "main_genre", "douban_rating", "rating_count",
         "n_valid", "mean_sentiment"]
    ].rename(columns={
        "title": "电影", "release_year": "上映年份", "main_genre": "主类型",
        "douban_rating": "豆瓣评分", "rating_count": "评分人数",
        "n_valid": "有效评论数", "mean_sentiment": "平均文本情感",
    }).to_csv(TABLE_DIR / "q3_high_rating_high_attention.csv",
              index=False, encoding="utf-8-sig")

    # --- 补充榜单三：文本情感明显高于评分预期 --------------------------
    gap_top = scored.sort_values("gap_raw", ascending=False).head(10)
    gap_top[
        ["title", "main_genre", "douban_rating", "rating_count",
         "n_valid", "mean_sentiment", "gap_raw"]
    ].rename(columns={
        "title": "电影", "main_genre": "主类型", "douban_rating": "豆瓣评分",
        "rating_count": "评分人数", "n_valid": "有效评论数",
        "mean_sentiment": "平均文本情感", "gap_raw": "情感-评分绝对差",
    }).to_csv(TABLE_DIR / "q3_sentiment_above_rating.csv",
              index=False, encoding="utf-8-sig")

    # --- 权重敏感性分析（5 组）----------------------------------------
    base_key = WEIGHT_SENSITIVITY_GRID[0]
    rank_maps: dict[tuple, pd.Series] = {}
    top_sets: dict[tuple, set] = {}
    sens_rows: list[dict] = []

    for wg, wu, wa in WEIGHT_SENSITIVITY_GRID:
        tmp = compute_index(eligible, wg, wu, wa)
        tmp = tmp.sort_values("U", ascending=False).reset_index(drop=True)
        tmp["rank"] = range(1, len(tmp) + 1)
        key = (wg, wu, wa)
        rank_maps[key] = tmp.set_index("movie_id")["rank"]
        top_sets[key] = set(tmp.head(10)["movie_id"])

    base_rank = rank_maps[base_key]
    base_top = top_sets[base_key]

    for wg, wu, wa in WEIGHT_SENSITIVITY_GRID:
        key = (wg, wu, wa)
        cur = rank_maps[key]
        rho = base_rank.corr(cur, method="spearman")
        tmp_names = (
            compute_index(eligible, wg, wu, wa)
            .sort_values("U", ascending=False).head(10)["title"].tolist()
        )
        sens_rows.append(
            {
                "权重组合": f"({wg:.2f}, {wu:.2f}, {wa:.2f})",
                "说明": _weight_desc(wg, wu, wa),
                "前十重合数": len(base_top & top_sets[key]),
                "与基准秩相关": round(float(rho), 4),
                "前十影片": "、".join(tmp_names),
            }
        )

    sens_df = pd.DataFrame(sens_rows)
    sens_df.to_csv(TABLE_DIR / "q3_weight_sensitivity.csv", index=False, encoding="utf-8-sig")

    # --- 共线性检查 ---------------------------------------------------
    from scipy.stats import spearmanr

    collinearity = float(
        spearmanr(scored["P_raw"], scored["H_raw"]).statistic
    )

    t1 = top10.iloc[0]
    logger.info(
        "Q3 完成：参评 %d 部，第一名《%s》U=%.3f；最低秩相关 %.3f",
        len(eligible), t1["title"], t1["U"], sens_df["与基准秩相关"].min(),
    )

    return {
        "eligible": int(len(eligible)),
        "total": int(len(feats)),
        "top10": top10_out.to_dict(orient="records"),
        "low_attention": low_attn["title"].tolist(),
        "high_attention": high_attn["title"].tolist(),
        "gap_top": gap_top["title"].tolist(),
        "weights": {"gap": WEIGHT_SENTIMENT_GAP, "useful": WEIGHT_USEFUL,
                    "attention": WEIGHT_ATTENTION},
        "sensitivity": sens_df.to_dict(orient="records"),
        "min_rank_corr": round(float(sens_df["与基准秩相关"].min()), 4),
        "collinearity_P_H": round(collinearity, 4),
        "threshold": MIN_REVIEWS_FOR_INDEX,
        "adjustments": [
            "S 与 R 各自做样本内 Z 标准化后再相减，避免高分片 U 恒为负",
            "H 由「有用率」改为「平均有用数的对数」，因数据无没用数",
            "S 只用 A 类有效评论，并剔除严重矛盾样本",
        ],
    }


def _weight_desc(wg: float, wu: float, wa: float) -> str:
    """为权重组合生成简短的中文说明。"""
    if (wg, wu, wa) == (0.50, 0.30, 0.20):
        return "基准：以文本口碑为主，兼顾有用性与关注度"
    if abs(wg - 0.70) < 1e-9:
        return "强化文本口碑差值"
    if abs(wu - 0.40) < 1e-9:
        return "强化评论有用性"
    if abs(wg - 0.34) < 1e-9:
        return "三项等权"
    if abs(wa - 0.25) < 1e-9:
        return "强化关注度惩罚"
    return "备选组合"


if __name__ == "__main__":
    import json

    _result = run_underrated_index()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
