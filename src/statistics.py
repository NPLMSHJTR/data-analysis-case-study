"""
src/statistics.py
=================
描述统计与结构分析（Q1、Q2）。

口径声明
--------
1. rating_count 是豆瓣页面的「评价人数」，指参与打分的用户数，
   不等于观影人数。全文统一称「评分人数」。
2. 不预设数据服从正态分布。偏度、峰度只作形态描述，不作推断前提。
3. 只有一个时间点的榜单快照，因此 Q2 只能做横截面结构分析。
   任何「占比变化」都需要至少两个时间节点，本项目不具备该条件，
   相关结论标注为数据不足。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from config import RAW_DIR, TABLE_DIR
from src.utils import get_logger

logger = get_logger("stats")

# 年代分组：左闭右开，最后一组为 2020 及以后
ERA_BINS: list[tuple[int, int, str]] = [
    (0, 1949, "1950年以前"),
    (1950, 1959, "1950—1959"),
    (1960, 1969, "1960—1969"),
    (1970, 1979, "1970—1979"),
    (1980, 1989, "1980—1989"),
    (1990, 1999, "1990—1999"),
    (2000, 2009, "2000—2009"),
    (2010, 2019, "2010—2019"),
    (2020, 2100, "2020年及以后"),
]
ERA_ORDER = [e[2] for e in ERA_BINS]

MAIN_GENRES: list[str] = [
    "剧情", "喜剧", "爱情", "动作", "科幻", "悬疑",
    "犯罪", "动画", "战争", "纪录片", "其他",
]

# 首个类型不在候选集合时的固定优先级（分析前确定，事后不调整）
GENRE_PRIORITY: list[str] = [
    "动画", "纪录片", "科幻", "悬疑", "犯罪", "战争",
    "动作", "爱情", "喜剧", "剧情",
]


def assign_era(year) -> str:
    """
    按上映年份归入年代分组。

    参数:
        year: 年份，可为字符串或数值。

    返回:
        年代标签；无法解析时返回「未知」。
    """
    try:
        y = int(float(year))
    except (TypeError, ValueError):
        return "未知"
    for lo, hi, label in ERA_BINS:
        if lo <= y <= hi:
            return label
    return "未知"


def assign_main_genre(genres) -> tuple[str, str]:
    """
    依据固定规则判定影片主类型。

    判定顺序：
    1. 取类型串按空格切分，保留原始顺序；
    2. 首个类型在候选集合内 → 直接作为主类型；
    3. 否则按 GENRE_PRIORITY 固定优先级在全部类型中挑第一个命中的；
    4. 全部未命中 → 记为「其他」。

    参数:
        genres: 形如「犯罪 剧情」的类型串。

    返回:
        (主类型, 判定依据) 二元组。
    """
    if not isinstance(genres, str) or not genres.strip():
        return "其他", "类型缺失"

    parts = [g for g in genres.replace("/", " ").split() if g]
    if not parts:
        return "其他", "类型缺失"

    if parts[0] in MAIN_GENRES and parts[0] != "其他":
        return parts[0], "来源首个类型"

    for g in GENRE_PRIORITY:
        if g in parts:
            return g, "按预设优先级"

    return "其他", "未命中候选类型"


def load_movies() -> pd.DataFrame:
    """
    读取 Top250 榜单并做类型转换。

    返回:
        电影 DataFrame，数值列已转为数值型。
    """
    path = RAW_DIR / "top250_raw.csv"
    if not path.exists():
        raise FileNotFoundError(f"未找到榜单数据: {path}")
    df = pd.read_csv(path, dtype={"movie_id": str})
    for col in ["douban_rating", "rating_count", "release_year"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _describe(series: pd.Series) -> dict:
    """
    计算一组数值的描述统计量。

    参数:
        series: 数值序列。

    返回:
        含均值、中位数、众数、标准差、四分位数、偏度、峰度的字典。
    """
    s = pd.to_numeric(series, errors="coerce").dropna()
    mode_vals = s.mode()
    return {
        "n": int(s.size),
        "mean": round(float(s.mean()), 4),
        "median": round(float(s.median()), 4),
        "mode": round(float(mode_vals.iloc[0]), 4) if len(mode_vals) else np.nan,
        "std": round(float(s.std(ddof=1)), 4),
        "min": round(float(s.min()), 4),
        "q1": round(float(s.quantile(0.25)), 4),
        "q3": round(float(s.quantile(0.75)), 4),
        "max": round(float(s.max()), 4),
        "iqr": round(float(s.quantile(0.75) - s.quantile(0.25)), 4),
        "skewness": round(float(stats.skew(s, bias=False)), 4),
        "kurtosis": round(float(stats.kurtosis(s, bias=False, fisher=True)), 4),
    }


def analyze_q1(movies: pd.DataFrame) -> dict:
    """
    完成 Q1：评分与评分人数的分布形态、集中区间与相关性。

    参数:
        movies: Top250 电影表。

    返回:
        含描述统计、集中区间与相关系数的字典，并写出 CSV。
    """
    df = movies.copy()
    df["log_rating_count"] = np.log10(df["rating_count"])

    r_stats = _describe(df["douban_rating"])
    c_stats = _describe(df["rating_count"])
    l_stats = _describe(df["log_rating_count"])

    pearson_r, pearson_p = stats.pearsonr(df["douban_rating"], df["rating_count"])
    spearman_r, spearman_p = stats.spearmanr(df["douban_rating"], df["rating_count"])
    pearson_log_r, pearson_log_p = stats.pearsonr(
        df["douban_rating"], df["log_rating_count"]
    )

    # 集中区间用四分位距界定，避免受极值影响
    r_lo, r_hi = r_stats["q1"], r_stats["q3"]
    c_lo, c_hi = c_stats["q1"], c_stats["q3"]
    in_rating = float(df["douban_rating"].between(r_lo, r_hi).mean())
    in_count = float(df["rating_count"].between(c_lo, c_hi).mean())

    # 评分档位频数（0.5 分一档）
    df["rating_bin"] = (df["douban_rating"] * 2).round() / 2
    (
        df["rating_bin"].value_counts().sort_index()
        .rename_axis("rating").reset_index(name="count")
    ).to_csv(TABLE_DIR / "q1_rating_histogram.csv", index=False, encoding="utf-8-sig")

    desc = pd.DataFrame(
        [
            {"指标": "样本量", "豆瓣评分": f"{r_stats['n']}", "评分人数": f"{c_stats['n']}"},
            {"指标": "均值", "豆瓣评分": f"{r_stats['mean']:.4f}", "评分人数": f"{c_stats['mean']:,.2f}"},
            {"指标": "中位数", "豆瓣评分": f"{r_stats['median']:.3f}", "评分人数": f"{c_stats['median']:,.1f}"},
            {"指标": "众数", "豆瓣评分": f"{r_stats['mode']:.1f}", "评分人数": f"{c_stats['mode']:,.0f}"},
            {"指标": "标准差", "豆瓣评分": f"{r_stats['std']:.4f}", "评分人数": f"{c_stats['std']:,.2f}"},
            {"指标": "最小值", "豆瓣评分": f"{r_stats['min']:.1f}", "评分人数": f"{c_stats['min']:,.0f}"},
            {"指标": "下四分位 Q1", "豆瓣评分": f"{r_stats['q1']:.3f}", "评分人数": f"{c_stats['q1']:,.1f}"},
            {"指标": "上四分位 Q3", "豆瓣评分": f"{r_stats['q3']:.3f}", "评分人数": f"{c_stats['q3']:,.1f}"},
            {"指标": "最大值", "豆瓣评分": f"{r_stats['max']:.1f}", "评分人数": f"{c_stats['max']:,.0f}"},
            {"指标": "四分位距 IQR", "豆瓣评分": f"{r_stats['iqr']:.4f}", "评分人数": f"{c_stats['iqr']:,.1f}"},
            {"指标": "偏度", "豆瓣评分": f"{r_stats['skewness']:.4f}", "评分人数": f"{c_stats['skewness']:.4f}"},
            {"指标": "峰度（超额）", "豆瓣评分": f"{r_stats['kurtosis']:.4f}", "评分人数": f"{c_stats['kurtosis']:.4f}"},
            {"指标": "偏度（log10 评分人数）", "豆瓣评分": "—", "评分人数": f"{l_stats['skewness']:.4f}"},
            {"指标": "峰度（log10 评分人数）", "豆瓣评分": "—", "评分人数": f"{l_stats['kurtosis']:.4f}"},
        ]
    )
    desc.to_csv(TABLE_DIR / "q1_descriptive.csv", index=False, encoding="utf-8-sig")

    corr = pd.DataFrame(
        [
            {"方法": "Pearson（原始评分人数）", "系数": round(float(pearson_r), 4), "p值": float(f"{pearson_p:.4g}")},
            {"方法": "Spearman", "系数": round(float(spearman_r), 4), "p值": float(f"{spearman_p:.4g}")},
            {"方法": "Pearson（评分人数取对数）", "系数": round(float(pearson_log_r), 4), "p值": float(f"{pearson_log_p:.4g}")},
        ]
    )
    corr.to_csv(TABLE_DIR / "q1_correlation.csv", index=False, encoding="utf-8-sig")

    logger.info(
        "Q1 完成：评分均值 %.2f、偏度 %.2f；评分人数偏度 %.2f，对数后 %.4f",
        r_stats["mean"], r_stats["skewness"], c_stats["skewness"], l_stats["skewness"],
    )

    return {
        "rating": r_stats,
        "rating_count": c_stats,
        "log_count": l_stats,
        "pearson_r": round(float(pearson_r), 4),
        "pearson_p": float(f"{pearson_p:.4g}"),
        "spearman_r": round(float(spearman_r), 4),
        "spearman_p": float(f"{spearman_p:.4g}"),
        "pearson_log_r": round(float(pearson_log_r), 4),
        "pearson_log_p": float(f"{pearson_log_p:.4g}"),
        "rating_interval": [r_lo, r_hi],
        "rating_share": round(in_rating, 4),
        "count_interval": [c_lo, c_hi],
        "count_share": round(in_count, 4),
    }


def analyze_q2(movies: pd.DataFrame) -> dict:
    """
    完成 Q2：年代与主类型的交叉结构（单时点横截面）。

    参数:
        movies: Top250 电影表。

    返回:
        含交叉表、占比、分布与限制说明的字典，并写出 CSV。
    """
    df = movies.copy()
    df["era"] = df["release_year"].map(assign_era)
    assigned = df["genres"].map(assign_main_genre)
    df["main_genre"] = [a[0] for a in assigned]
    df["genre_rule"] = [a[1] for a in assigned]
    total = len(df)

    era_counts = df["era"].value_counts().reindex(ERA_ORDER).fillna(0).astype(int)
    era_tab = pd.DataFrame(
        {"年代": ERA_ORDER, "影片数": era_counts.values,
         "占比": [round(v / total, 4) for v in era_counts.values]}
    )
    era_tab.to_csv(TABLE_DIR / "q2_era_distribution.csv", index=False, encoding="utf-8-sig")

    genre_counts = df["main_genre"].value_counts().reindex(MAIN_GENRES).fillna(0).astype(int)
    genre_tab = pd.DataFrame(
        {"主类型": MAIN_GENRES, "影片数": genre_counts.values,
         "占比": [round(v / total, 4) for v in genre_counts.values]}
    )
    genre_tab.to_csv(TABLE_DIR / "q2_genre_distribution.csv", index=False, encoding="utf-8-sig")

    cross = pd.crosstab(df["era"], df["main_genre"])
    cross = cross.reindex(index=ERA_ORDER, columns=MAIN_GENRES, fill_value=0)
    cross.to_csv(TABLE_DIR / "q2_era_genre_crosstab.csv", encoding="utf-8-sig")

    row_sums = cross.sum(axis=1).replace(0, np.nan)
    (cross.div(row_sums, axis=0) * 100).round(2).to_csv(
        TABLE_DIR / "q2_share_by_era.csv", encoding="utf-8-sig"
    )
    (cross / total * 100).round(2).to_csv(
        TABLE_DIR / "q2_share_of_total.csv", encoding="utf-8-sig"
    )

    long = cross.stack().reset_index()
    long.columns = ["era", "main_genre", "count"]
    long["share_of_total_pct"] = (long["count"] / total * 100).round(2)
    long = long.sort_values("count", ascending=False).reset_index(drop=True)
    long.to_csv(TABLE_DIR / "q2_era_genre_long.csv", index=False, encoding="utf-8-sig")

    era_rating = (
        df.groupby("era")["douban_rating"]
        .agg(["count", "mean", "median", "std"])
        .reindex(ERA_ORDER)
        .round(3)
    )
    era_rating.to_csv(TABLE_DIR / "q2_era_rating.csv", encoding="utf-8-sig")

    top = long.iloc[0]
    logger.info(
        "Q2 完成：最大组合 %s × %s（%d 部，占 %.2f%%）",
        top["era"], top["main_genre"], int(top["count"]), top["share_of_total_pct"],
    )

    return {
        "total": total,
        "era_counts": era_counts.to_dict(),
        "genre_counts": genre_counts.to_dict(),
        "top_combo": {
            "era": str(top["era"]),
            "genre": str(top["main_genre"]),
            "count": int(top["count"]),
            "share_pct": float(top["share_of_total_pct"]),
        },
        "genre_rule_distribution": df["genre_rule"].value_counts().to_dict(),
        "era_rating_mean": era_rating["mean"].to_dict(),
        "temporal_available": False,
        "temporal_note": (
            "本项目仅获得单一时间点的 Top250 榜单快照，缺少第二个时间节点，"
            "无法计算占比变化幅度，也无法识别变化最大与最小的组合。"
            "该部分结论标记为数据不足，不作推测性表述。"
        ),
    }


def build_movie_features() -> pd.DataFrame:
    """
    汇总每部影片的情感、评分、关注度与有用性指标，供被低估指数使用。

    仅统计进入内容分析的评论（disposition 为 content / mismatch_only 之外的 A 类）。

    返回:
        每部影片一行的特征表。
    """
    from config import PROCESSED_DIR

    movies = load_movies()
    reviews = pd.read_csv(
        PROCESSED_DIR / "reviews_dual.csv", dtype={"movie_id": str}
    )

    # 只取 A 类有效评论；严重矛盾样本单独隔离，不进入影片的情感均值
    valid = reviews[
        (reviews["quality_label"] == "A")
        & (reviews["consistency"].fillna("") != "严重矛盾")
    ].copy()

    valid["sentiment_score"] = pd.to_numeric(valid["sentiment_score"], errors="coerce")
    valid["useful_count"] = pd.to_numeric(valid["useful_count"], errors="coerce").fillna(0)

    agg = (
        valid.groupby("movie_id")
        .agg(
            n_valid=("review_id", "count"),
            mean_sentiment=("sentiment_score", "mean"),
            std_sentiment=("sentiment_score", "std"),
            mean_useful=("useful_count", "mean"),
            median_useful=("useful_count", "median"),
            pos_share=("sentiment_label", lambda s: float((s == "pos").mean())),
            neg_share=("sentiment_label", lambda s: float((s == "neg").mean())),
            mean_confidence=("sentiment_confidence", "mean"),
        )
        .reset_index()
    )

    df = movies.merge(agg, on="movie_id", how="left")
    df["n_valid"] = df["n_valid"].fillna(0).astype(int)
    df["era"] = df["release_year"].map(assign_era)
    df["main_genre"] = [assign_main_genre(g)[0] for g in df["genres"]]

    # 原始刻度差：仅用于展示
    df["R_linear"] = (2 * df["douban_rating"] - 15) / 5
    df["gap_raw"] = df["mean_sentiment"] - df["R_linear"]

    # 关注度与有用性
    df["P_raw"] = np.log10(df["rating_count"].clip(lower=1))
    df["H_raw"] = np.log1p(df["mean_useful"].clip(lower=0))

    return df

if __name__ == "__main__":
    import json

    # Q1 与 Q2 都需要影片表作为输入，所以这里先 load_movies 再分发，
    # 不能像其他模块那样直接调无参的 run_* 函数。
    _movies = load_movies()
    _result = {
        "q1": analyze_q1(_movies),
        "q2": analyze_q2(_movies),
    }
    print(json.dumps(_result, ensure_ascii=False, indent=2))
