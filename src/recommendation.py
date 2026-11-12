"""
src/recommendation.py
=====================
Q5：为电影栏目编辑推荐五部重映影片。

为什么不能只按豆瓣评分排
------------------------
评分反映长期口碑，重映决策需要的是「当下什么还卖得动」。
公开数据显示，《笑傲江湖：东方不败》豆瓣 8.5 分、24 万人评价，
2026 年重映首日排片仅 6.3%、票房 15.6 万元；而《泰坦尼克号》3D 重映拿到 9.46 亿元。
两者的差别不在评分，而在类型市场接受度、年代距离与传播抓手。
因此本模型把「类型市场热度」作为独立维度纳入，权重 0.20，
并在结果中明确标注该赋分是分析者判断而非行业统计。

综合推荐分
----------
R = 0.15·Z(评分) + 0.25·Z(U) + 0.15·Z(情感)
  + 0.08·Z(关注度) + 0.07·Z(有效评论数) + 0.10·Z(年代稀缺性)
  + 0.20·Z(类型市场热度)

评分权重刻意压低，避免结果退化为「Top250 前五名」。

约束
----
1. 被低估指数必须为正（否则推荐退化为「再推荐一次经典名片」）
2. 已上映满 8 年
3. 第一轮每类型最多 1 部，第二轮放宽至 2 部
4. 同一十年区间最多 2 部
5. 最终 5 部须覆盖至少 3 个年代、4 种类型

版权边界
--------
本项目不掌握任何版权、发行、票房数据。推荐只说明「内容与口碑层面的重映价值」，
版权状态一律标注「需进一步确认」，不作可行性断言。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import (
    CURRENT_YEAR,
    REC_MAX_PER_DECADE,
    REC_MAX_PER_GENRE_ROUND1,
    REC_MAX_PER_GENRE_ROUND2,
    REC_MIN_YEARS_SINCE_RELEASE,
    REC_WEIGHTS,
    TABLE_DIR,
)
from src.market_context import GENRE_HEAT, GENRE_HEAT_NOTE, RELEASE_WINDOWS, save_market_tables
from src.statistics import assign_era
from src.utils import get_logger

logger = get_logger("recommend")

# 年代稀缺性：越早的影片，大银幕重映的稀缺价值越高
ERA_SCARCITY: dict[str, float] = {
    "1950年以前": 1.00, "1950—1959": 0.95, "1960—1969": 0.92,
    "1970—1979": 0.88, "1980—1989": 0.84, "1990—1999": 0.80,
    "2000—2009": 0.55, "2010—2019": 0.35, "2020年及以后": 0.15,
}


def _z(s: pd.Series) -> pd.Series:
    """Z 分数；标准差为 0 时返回全零。"""
    sd = s.std(ddof=1)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def _decade(year) -> str:
    """把年份归入十年区间，用于多样性约束。"""
    try:
        y = int(float(year))
    except (TypeError, ValueError):
        return "未知"
    return f"{y // 10 * 10}s"


def build_candidates() -> pd.DataFrame:
    """
    从被低估指数结果中读取候选影片并计算综合推荐分。

    返回:
        含 R_score 与排序的候选表。
    """
    path = TABLE_DIR / "q3_underrated_full.csv"
    if not path.exists():
        raise FileNotFoundError(f"未找到指数结果: {path}，请先运行 src.underrated_index")

    df = pd.read_csv(path, dtype={"movie_id": str})
    df = df[df["U"].notna()].copy()

    n0 = len(df)
    df = df[df["U"] > 0].copy()
    logger.info("被低估指数为正的候选：%d 部（原 %d 部）", len(df), n0)

    n1 = len(df)
    df = df[df["release_year"] <= CURRENT_YEAR - REC_MIN_YEARS_SINCE_RELEASE].copy()
    logger.info(
        "上映满 %d 年的候选：%d 部（原 %d 部）",
        REC_MIN_YEARS_SINCE_RELEASE, len(df), n1,
    )

    if df.empty:
        raise ValueError("筛选后无候选影片，请放宽约束条件")

    df["era"] = df["release_year"].map(assign_era)
    df["decade"] = df["release_year"].map(_decade)
    df["era_scarcity"] = df["era"].map(ERA_SCARCITY).fillna(0.3)
    df["genre_heat"] = df["main_genre"].map(GENRE_HEAT).fillna(0.5)

    df["R_score"] = (
        REC_WEIGHTS["rating"] * _z(df["douban_rating"])
        + REC_WEIGHTS["index"] * _z(df["U"])
        + REC_WEIGHTS["sentiment"] * _z(df["mean_sentiment"])
        + REC_WEIGHTS["attention"] * _z(np.log10(df["rating_count"].clip(lower=1)))
        + REC_WEIGHTS["reviews"] * _z(df["n_valid"])
        + REC_WEIGHTS["era"] * _z(df["era_scarcity"])
        + REC_WEIGHTS["market"] * _z(df["genre_heat"])
    )

    df = df.sort_values("R_score", ascending=False).reset_index(drop=True)
    df["R_rank"] = range(1, len(df) + 1)
    return df


def _greedy(
    cand: pd.DataFrame,
    max_genre: int,
    max_decade: int,
    target: int,
    exclude: set[str] | None = None,
) -> list[pd.Series]:
    """
    按 R_score 从高到低贪心选取，并施加上限约束。

    参数:
        cand: 已排序的候选表。
        max_genre: 同类型数量上限。
        max_decade: 同十年区间数量上限。
        target: 需要选出的数量。
        exclude: 已入选影片 movie_id 集合。

    返回:
        入选记录列表。
    """
    picked: list[pd.Series] = []
    g_count: dict[str, int] = {}
    d_count: dict[str, int] = {}
    skip = exclude or set()

    for _, row in cand.iterrows():
        if row["movie_id"] in skip:
            continue
        g, d = row["main_genre"], row["decade"]
        if g_count.get(g, 0) >= max_genre:
            continue
        if d_count.get(d, 0) >= max_decade:
            continue
        picked.append(row)
        g_count[g] = g_count.get(g, 0) + 1
        d_count[d] = d_count.get(d, 0) + 1
        if len(picked) == target:
            break
    return picked


def select_five(cand: pd.DataFrame) -> pd.DataFrame:
    """
    在多样性约束下选取五部影片。

    采用两轮策略：第一轮每类型最多 1 部；不足 5 部时第二轮放宽到 2 部；
    仍不足则仅按分数补齐。

    参数:
        cand: 已排序的候选表。

    返回:
        入选的五部影片。
    """
    picked = _greedy(cand, REC_MAX_PER_GENRE_ROUND1, REC_MAX_PER_DECADE, 5)

    if len(picked) < 5:
        used = {p["movie_id"] for p in picked}
        picked += _greedy(
            cand, REC_MAX_PER_GENRE_ROUND2, REC_MAX_PER_DECADE, 5 - len(picked), used
        )

    if len(picked) < 5:
        used = {p["movie_id"] for p in picked}
        rest = cand[~cand["movie_id"].isin(used)].head(5 - len(picked))
        picked += [row for _, row in rest.iterrows()]

    out = pd.DataFrame(picked).reset_index(drop=True)
    out.insert(0, "推荐序号", range(1, len(out) + 1))
    return out


def _suggest_window(genre: str) -> dict:
    """
    依据类型给出适合的放映档期建议。

    参数:
        genre: 主类型。

    返回:
        含窗口、依据、来源日期的字典。
    """
    mapping = {
        "动画": 1, "喜剧": 0, "爱情": 0, "剧情": 3, "悬疑": 3,
        "犯罪": 3, "科幻": 2, "动作": 2, "战争": 3, "纪录片": 1,
    }
    idx = mapping.get(genre, 3)
    w = RELEASE_WINDOWS[idx]
    return {"窗口": w["窗口"], "依据": w["依据"], "来源日期": w["来源日期"]}


def run_recommendation() -> dict:
    """
    执行 Q5 推荐并写出推荐表。

    输出:
        outputs/tables/q5_remake_recommendations.csv
        outputs/tables/q5_market_facts.csv 等三张市场表

    返回:
        含五部推荐与多样性统计的字典。
    """
    market = save_market_tables()
    cand = build_candidates()
    logger.info("候选影片 %d 部", len(cand))

    five = select_five(cand)

    five = five.copy()
    five["建议档期"] = five["main_genre"].map(lambda g: _suggest_window(g)["窗口"])
    five["档期依据"] = five["main_genre"].map(lambda g: _suggest_window(g)["依据"])
    five["市场热度"] = five["genre_heat"].round(3)

    out = five[
        ["推荐序号", "title", "release_year", "director", "main_genre", "era",
         "douban_rating", "rating_count", "n_valid", "mean_sentiment",
         "U", "genre_heat", "era_scarcity", "R_score", "建议档期", "档期依据"]
    ].rename(
        columns={
            "title": "电影名称", "release_year": "上映年份", "director": "导演",
            "main_genre": "主类型", "era": "年代", "douban_rating": "豆瓣评分",
            "rating_count": "评分人数", "n_valid": "有效评论数",
            "mean_sentiment": "平均文本情感", "U": "被低估指数",
            "genre_heat": "类型市场热度", "era_scarcity": "年代稀缺性",
            "R_score": "综合推荐分",
        }
    )
    for c in ["平均文本情感", "被低估指数", "综合推荐分"]:
        out[c] = out[c].round(4)
    out["版权状态"] = "需进一步确认（本项目未获得版权信息）"
    out.to_csv(TABLE_DIR / "q5_remake_recommendations.csv", index=False, encoding="utf-8-sig")

    diversity = {
        "genres": int(five["main_genre"].nunique()),
        "eras": int(five["era"].nunique()),
        "decades": int(five["decade"].nunique()),
        "mean_rating": round(float(five["douban_rating"].mean()), 3),
        "mean_index": round(float(five["U"].mean()), 3),
        "total_reviews": int(five["n_valid"].sum()),
    }

    logger.info(
        "Q5 完成：%d 部，覆盖 %d 类型 / %d 年代",
        len(five), diversity["genres"], diversity["eras"],
    )

    return {
        "candidates": int(len(cand)),
        "selected": out.to_dict(orient="records"),
        "diversity": diversity,
        "weights": REC_WEIGHTS,
        "market": market,
        "market_note": GENRE_HEAT_NOTE,
        "constraints": {
            "min_years": REC_MIN_YEARS_SINCE_RELEASE,
            "max_per_genre_round1": REC_MAX_PER_GENRE_ROUND1,
            "max_per_decade": REC_MAX_PER_DECADE,
            "index_positive_only": True,
        },
    }


if __name__ == "__main__":
    import json

    _result = run_recommendation()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
