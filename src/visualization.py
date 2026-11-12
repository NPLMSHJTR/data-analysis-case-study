"""
src/visualization.py
====================
图表生成模块。所有图表均由真实计算结果绘制，不含任何手工设定的数值。

图表清单
--------
图 3-1  评论清洗与分级漏斗
图 3-2  评论质量分类构成
图 3-3  双维度处理矩阵热力图
图 4-1  基础方法 vs 改进方法对比
图 5-1  评分分布直方图 + 核密度
图 5-2  评分人数分布（原始与对数）
图 5-3  评分与评分人数散点
图 6-1  年代分布
图 6-2  主类型分布
图 6-3  年代 × 主类型热力图
图 6-4  各年代平均评分
图 7-1  被低估指数前十名
图 7-2  权重敏感性
图 7-3  高评分低关注影片
图 8-1  各星级情感构成
图 8-2  星级与情感散点
图 9-1  五部推荐影片多维指标
图 9-2  类型市场热度
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FuncFormatter

from config import FIG_DIR, FIGURE_SIZE, PALETTE, PROCESSED_DIR, RAW_DIR, TABLE_DIR
from src.statistics import ERA_ORDER, MAIN_GENRES
from src.utils import get_logger, save_figure, setup_chinese_font

logger = get_logger("viz")

sns.set_theme(style="whitegrid", rc={"axes.edgecolor": "#CCCCCC"})
setup_chinese_font()
plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.titlesize": 15,
        "axes.labelsize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "axes.titleweight": "bold",
    }
)

C = PALETTE


def _thousands(x, _pos=None):
    """坐标轴千分位格式化。"""
    return f"{int(x):,}"


# ---------------------------------------------------------------------------
# 第三章：清洗与质量
# ---------------------------------------------------------------------------
def fig_cleaning_funnel() -> Path:
    """图 3-1：从原始评论到进入各分析环节的数量变化。"""
    q = pd.read_csv(TABLE_DIR / "quality_distribution.csv").set_index("标签")["数量"]
    dual = pd.read_csv(PROCESSED_DIR / "reviews_dual.csv", dtype={"movie_id": str})
    disp = dual["disposition"].value_counts()

    raw = int(q.sum())
    stages = [
        "原始评论",
        "结构正常",
        "去重复副本",
        "有效评论(A+B)",
        "进入内容分析",
        "进入情感统计",
    ]
    values = [
        raw,
        raw - int(q.get("X", 0)),
        raw - int(q.get("X", 0)) - int(q.get("D", 0)),
        int(q.get("A", 0) + q.get("B", 0)),
        int(disp.get("content", 0)),
        int(disp.get("content", 0) + disp.get("sentiment", 0) + disp.get("mismatch_only", 0)),
    ]

    fig, ax = plt.subplots(figsize=(9.8, 5.4))
    colors = [C["neutral"], C["cool"], C["primary"], C["accent"], C["secondary"], C["purple"]]
    bars = ax.barh(range(len(stages))[::-1], values, color=colors, alpha=0.9)
    ax.set_yticks(range(len(stages))[::-1])
    ax.set_yticklabels(stages)
    ax.set_xlabel("评论数量")
    ax.set_title("图 3-1  评论清洗与分级的逐层留存")
    for b, v in zip(bars, values):
        ax.text(v + raw * 0.008, b.get_y() + b.get_height() / 2,
                f"{v:,}（{v / raw * 100:.1f}%）", va="center", fontsize=9)
    ax.set_xlim(0, raw * 1.22)
    return save_figure(fig, FIG_DIR / "fig3_1_cleaning_funnel.png")


def fig_quality_distribution() -> Path:
    """图 3-2：内容有效性五类的构成。"""
    q = pd.read_csv(TABLE_DIR / "quality_distribution.csv")
    q = q[q["数量"] > 0]

    fig, ax = plt.subplots(figsize=(9.2, 5.4))
    colors = [C["accent"], C["warm"], C["secondary"], C["neutral"], C["cool"], "#B0B0B0"]
    wedges, _texts, autotexts = ax.pie(
        q["数量"], autopct=lambda p: f"{p:.1f}%",
        colors=colors[: len(q)], startangle=95,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5}, pctdistance=0.78,
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontsize(10)
        t.set_fontweight("bold")
    ax.legend(
        wedges,
        [f"{r['类别']}（{int(r['数量'])} 条）" for _, r in q.iterrows()],
        loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False,
    )
    ax.set_title("图 3-2  评论内容有效性分类构成")
    return save_figure(fig, FIG_DIR / "fig3_2_quality_distribution.png")


def fig_dual_matrix() -> Path:
    """图 3-3：双维度处理矩阵（内容有效性 × 星级一致性）。"""
    cross = pd.read_csv(TABLE_DIR / "consistency_matrix.csv", index_col=0)
    cross = cross.reindex(index=["A", "B"], columns=["一致", "轻度不一致", "严重矛盾", "无法判定"],
                          fill_value=0).fillna(0).astype(int)
    cross.index = ["A 有效评论", "B 低信息量"]

    fig, ax = plt.subplots(figsize=(8.8, 4.4))
    sns.heatmap(
        cross, annot=True, fmt=".0f", cmap="YlOrRd", linewidths=0.8,
        linecolor="white", cbar_kws={"label": "评论数量"}, ax=ax,
    )
    ax.set_xlabel("星级与文本一致性（第二维度）")
    ax.set_ylabel("内容有效性（第一维度）")
    ax.set_title("图 3-3  双维度处理矩阵")
    return save_figure(fig, FIG_DIR / "fig3_3_dual_matrix.png")


# ---------------------------------------------------------------------------
# 第四章：方法对比
# ---------------------------------------------------------------------------
def fig_method_comparison() -> Path:
    """图 4-1：基础方法 vs 改进方法的关键指标对比。"""
    df = pd.read_csv(TABLE_DIR / "method_comparison.csv")
    metrics = ["准确率", "精确率", "召回率", "F1"]
    df = df.dropna(subset=metrics)

    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.0),
                             gridspec_kw={"width_ratios": [1.15, 1]})

    x = np.arange(len(metrics))
    w = 0.36
    base = df[df["方法"].str.startswith("方法一")][metrics].iloc[0]
    impr = df[df["方法"].str.startswith("方法二")][metrics].iloc[0]

    axes[0].bar(x - w / 2, base.values, w, label="方法一：基础清洗", color=C["neutral"], alpha=0.9)
    axes[0].bar(x + w / 2, impr.values, w, label="方法二：改进清洗", color=C["primary"], alpha=0.9)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(metrics)
    axes[0].set_ylim(0, 1.0)
    axes[0].set_ylabel("指标值")
    axes[0].set_title("(a) 人工验证集上的四项指标")
    axes[0].legend(loc="lower right")
    for i, (b, v) in enumerate(zip(base.values, impr.values)):
        axes[0].text(i - w / 2, b + 0.02, f"{b:.3f}", ha="center", fontsize=8.5)
        axes[0].text(i + w / 2, v + 0.02, f"{v:.3f}", ha="center", fontsize=8.5,
                     fontweight="bold", color=C["primary"])

    # (b) 保留规模与误杀率
    labels = ["保留比例", "误杀率"]
    b_vals = [float(df[df["方法"].str.startswith("方法一")]["占全量比例"].iloc[0]),
              float(df[df["方法"].str.startswith("方法一")]["误杀率"].iloc[0])]
    i_vals = [float(df[df["方法"].str.startswith("方法二")]["占全量比例"].iloc[0]),
              float(df[df["方法"].str.startswith("方法二")]["误杀率"].iloc[0])]

    x2 = np.arange(len(labels))
    axes[1].bar(x2 - w / 2, b_vals, w, color=C["neutral"], alpha=0.9, label="方法一")
    axes[1].bar(x2 + w / 2, i_vals, w, color=C["primary"], alpha=0.9, label="方法二")
    axes[1].set_xticks(x2)
    axes[1].set_xticklabels(labels)
    axes[1].set_ylim(0, 1.05)
    axes[1].set_title("(b) 保留规模与误杀代价")
    axes[1].legend(loc="upper right")
    for i, (b, v) in enumerate(zip(b_vals, i_vals)):
        axes[1].text(i - w / 2, b + 0.02, f"{b:.3f}", ha="center", fontsize=8.5)
        axes[1].text(i + w / 2, v + 0.02, f"{v:.3f}", ha="center", fontsize=8.5,
                     fontweight="bold", color=C["primary"])

    fig.suptitle("图 4-1  两套清洗方法的实验对比", fontsize=15, fontweight="bold")
    fig.tight_layout()
    return save_figure(fig, FIG_DIR / "fig4_1_method_comparison.png")


# ---------------------------------------------------------------------------
# 第五章：Q1
# ---------------------------------------------------------------------------
def fig_rating_distribution(movies: pd.DataFrame) -> Path:
    """图 5-1：评分分布直方图与核密度。"""
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    data = movies["douban_rating"].dropna()

    ax.hist(data, bins=np.arange(8.3, 9.81, 0.1), color=C["primary"],
            alpha=0.75, edgecolor="white", linewidth=0.8, label="影片数量")

    from scipy.stats import gaussian_kde
    kde = gaussian_kde(data)
    xs = np.linspace(data.min(), data.max(), 300)
    ax2 = ax.twinx()
    ax2.plot(xs, kde(xs), color=C["secondary"], lw=2.2, label="核密度")
    ax2.set_ylabel("概率密度", color=C["secondary"])
    ax2.tick_params(axis="y", colors=C["secondary"])
    ax2.grid(False)

    ax.axvline(data.mean(), color=C["accent"], ls="--", lw=1.6, label=f"均值 {data.mean():.2f}")
    ax.axvline(data.median(), color=C["warm"], ls=":", lw=1.8, label=f"中位数 {data.median():.2f}")
    ax.set_xlabel("豆瓣评分")
    ax.set_ylabel("影片数量")
    ax.set_title("图 5-1  Top250 影片豆瓣评分分布")
    ax.legend(loc="upper left", frameon=True)
    return save_figure(fig, FIG_DIR / "fig5_1_rating_distribution.png")


def fig_rating_count(movies: pd.DataFrame) -> Path:
    """图 5-2：评分人数的原始尺度与对数尺度分布。"""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    data = movies["rating_count"].dropna()

    axes[0].hist(data, bins=30, color=C["primary"], alpha=0.8, edgecolor="white")
    axes[0].set_xlabel("评分人数")
    axes[0].set_ylabel("影片数量")
    axes[0].set_title("(a) 原始尺度：明显右偏")
    axes[0].xaxis.set_major_formatter(FuncFormatter(_thousands))
    axes[0].tick_params(axis="x", rotation=30)

    logs = np.log10(data)
    axes[1].hist(logs, bins=26, color=C["cool"], alpha=0.85, edgecolor="white")
    axes[1].set_xlabel("评分人数（log10）")
    axes[1].set_ylabel("影片数量")
    axes[1].set_title("(b) 对数尺度：近似对称")
    axes[1].axvline(logs.mean(), color=C["secondary"], ls="--", lw=1.6,
                    label=f"均值 {logs.mean():.2f}")
    axes[1].legend()

    fig.suptitle("图 5-2  Top250 影片评分人数分布", fontsize=15, fontweight="bold")
    fig.tight_layout()
    return save_figure(fig, FIG_DIR / "fig5_2_rating_count.png")


def fig_rating_vs_count(movies: pd.DataFrame) -> Path:
    """图 5-3：评分与评分人数散点（横轴对数）。"""
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    x = movies["rating_count"]
    y = movies["douban_rating"]

    ax.scatter(x, y, s=34, alpha=0.55, color=C["primary"], edgecolor="white", linewidth=0.5)

    lx = np.log10(x)
    coef = np.polyfit(lx, y, 1)
    xs = np.linspace(lx.min(), lx.max(), 100)
    ax.plot(10 ** xs, np.polyval(coef, xs), color=C["secondary"], lw=2, label="对数横轴上的线性拟合")

    from scipy import stats
    r, p = stats.pearsonr(y, lx)
    ax.set_xscale("log")
    ax.set_xlabel("评分人数（对数刻度）")
    ax.set_ylabel("豆瓣评分")
    ax.set_title("图 5-3  豆瓣评分与评分人数的关系")
    ax.legend(title=f"Pearson r = {r:.3f}（p = {p:.2g}）", loc="lower right")
    ax.xaxis.set_major_formatter(FuncFormatter(_thousands))
    return save_figure(fig, FIG_DIR / "fig5_3_rating_vs_count.png")


# ---------------------------------------------------------------------------
# 第六章：Q2
# ---------------------------------------------------------------------------
def fig_era_distribution(movies: pd.DataFrame) -> Path:
    """图 6-1：年代分布。"""
    from src.statistics import assign_era as _era

    era = movies["release_year"].map(_era).value_counts().reindex(ERA_ORDER).fillna(0)

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    bars = ax.bar(range(len(era)), era.values, color=C["primary"], alpha=0.85, edgecolor="white")
    ax.set_xticks(range(len(era)))
    ax.set_xticklabels(era.index, rotation=35, ha="right")
    ax.set_ylabel("影片数量")
    ax.set_title("图 6-1  Top250 影片年代分布")
    for b, v in zip(bars, era.values):
        if v > 0:
            ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{int(v)}", ha="center", fontsize=9)
    ax.set_ylim(0, era.max() * 1.18)
    return save_figure(fig, FIG_DIR / "fig6_1_era_distribution.png")


def fig_genre_distribution(movies: pd.DataFrame) -> Path:
    """图 6-2：主类型分布。"""
    from src.statistics import assign_main_genre as _genre

    series = movies["genres"].map(lambda g: _genre(g)[0])
    genre = series.value_counts().reindex(MAIN_GENRES).fillna(0)

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    bars = ax.barh(range(len(genre))[::-1], genre.values, color=C["accent"], alpha=0.85)
    ax.set_yticks(range(len(genre))[::-1])
    ax.set_yticklabels(genre.index)
    ax.set_xlabel("影片数量")
    ax.set_title("图 6-2  Top250 影片主类型分布")
    for b, v in zip(bars, genre.values):
        if v > 0:
            ax.text(v + 0.8, b.get_y() + b.get_height() / 2, f"{int(v)}", va="center", fontsize=9)
    ax.set_xlim(0, genre.max() * 1.15)
    return save_figure(fig, FIG_DIR / "fig6_2_genre_distribution.png")


def fig_era_genre_heatmap() -> Path:
    """图 6-3：年代 × 主类型热力图。"""
    cross = pd.read_csv(TABLE_DIR / "q2_era_genre_crosstab.csv", index_col=0)
    cross = cross.reindex(index=ERA_ORDER, columns=MAIN_GENRES, fill_value=0).fillna(0)

    fig, ax = plt.subplots(figsize=(11, 6.2))
    sns.heatmap(cross, annot=True, fmt=".0f", cmap="Blues", linewidths=0.6,
                linecolor="white", cbar_kws={"label": "影片数量"}, ax=ax)
    ax.set_xlabel("主类型")
    ax.set_ylabel("年代")
    ax.set_title("图 6-3  年代 × 主类型交叉热力图（单位：部）")
    ax.tick_params(axis="x", rotation=30)
    return save_figure(fig, FIG_DIR / "fig6_3_era_genre_heatmap.png")


def fig_era_rating() -> Path:
    """图 6-4：各年代平均评分。"""
    era = pd.read_csv(TABLE_DIR / "q2_era_rating.csv", index_col=0)
    era = era.reindex(ERA_ORDER).dropna(subset=["mean"])

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    ax.plot(era.index, era["mean"], marker="o", lw=2.2, color=C["primary"], markersize=7, label="平均评分")
    ax.fill_between(era.index, era["mean"] - era["std"].fillna(0),
                    era["mean"] + era["std"].fillna(0),
                    alpha=0.18, color=C["primary"], label="±1 标准差")
    ax.set_ylabel("豆瓣评分")
    ax.set_title("图 6-4  不同年代影片的平均评分")
    ax.tick_params(axis="x", rotation=35)
    ax.legend()
    for x, y, n in zip(era.index, era["mean"], era["count"]):
        ax.annotate(f"n={int(n)}", (x, y), textcoords="offset points",
                    xytext=(0, 9), ha="center", fontsize=8, color=C["neutral"])
    return save_figure(fig, FIG_DIR / "fig6_4_era_rating.png")


# ---------------------------------------------------------------------------
# 第七章：Q3
# ---------------------------------------------------------------------------
def fig_underrated_top10() -> Path:
    """图 7-1：被低估指数前十名。"""
    t = pd.read_csv(TABLE_DIR / "q3_underrated_top10.csv").sort_values("被低估指数")

    fig, ax = plt.subplots(figsize=(9.6, 6))
    colors = [C["secondary"] if i >= len(t) - 3 else C["primary"] for i in range(len(t))]
    bars = ax.barh(t["电影"], t["被低估指数"], color=colors, alpha=0.9)
    ax.set_xlabel("被低估指数 U")
    ax.set_title("图 7-1  被低估指数前十名")
    for b, v in zip(bars, t["被低估指数"]):
        ax.text(v + 0.02, b.get_y() + b.get_height() / 2, f"{v:.3f}", va="center", fontsize=9)
    ax.set_xlim(0, t["被低估指数"].max() * 1.16)
    return save_figure(fig, FIG_DIR / "fig7_1_underrated_top10.png")


def fig_weight_sensitivity() -> Path:
    """图 7-2：五组权重下前十名的稳定性。"""
    sens = pd.read_csv(TABLE_DIR / "q3_weight_sensitivity.csv")

    fig, ax = plt.subplots(figsize=(10.2, 5.0))
    x = np.arange(len(sens))
    bars = ax.bar(x, sens["前十重合数"], color=C["cool"], alpha=0.9, width=0.55)
    ax.set_xticks(x)
    ax.set_xticklabels(sens["权重组合"], rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("与基准前十重合数（部）")
    ax.set_ylim(0, 11)
    ax.axhline(10, color=C["neutral"], ls="--", lw=1, label="完全重合（10 部）")
    ax.set_title("图 7-2  不同权重下前十名的重合情况")

    ax2 = ax.twinx()
    ax2.plot(x, sens["与基准秩相关"], color=C["secondary"], marker="o", lw=2, label="秩相关系数")
    ax2.set_ylabel("Spearman 秩相关", color=C["secondary"])
    ax2.set_ylim(0.5, 1.02)
    ax2.tick_params(axis="y", colors=C["secondary"])
    ax2.grid(False)

    for i, v in enumerate(sens["前十重合数"]):
        ax.text(i, v + 0.25, f"{int(v)}", ha="center", fontsize=9)
    ax.legend(loc="lower left")
    return save_figure(fig, FIG_DIR / "fig7_2_weight_sensitivity.png")


def fig_high_rating_low_attention() -> Path:
    """图 7-3：高评分但评分人数相对较少的影片。"""
    t = pd.read_csv(TABLE_DIR / "q3_high_rating_low_attention.csv").sort_values("评分人数")

    fig, ax = plt.subplots(figsize=(9.6, 6))
    bars = ax.barh(t["电影"], t["评分人数"], color=C["cool"], alpha=0.9)
    ax.set_xlabel("评分人数")
    ax.set_title("图 7-3  高评分但评分人数相对较少的影片（前十）")
    ax.xaxis.set_major_formatter(FuncFormatter(_thousands))
    for b, v, r in zip(bars, t["评分人数"], t["豆瓣评分"]):
        ax.text(v * 1.01, b.get_y() + b.get_height() / 2, f"{int(v):,}（{r} 分）",
                va="center", fontsize=8.5)
    ax.set_xlim(0, t["评分人数"].max() * 1.30)
    return save_figure(fig, FIG_DIR / "fig7_3_high_rating_low_attention.png")


# ---------------------------------------------------------------------------
# 第八章：Q4
# ---------------------------------------------------------------------------
def fig_star_sentiment_stacked() -> Path:
    """图 8-1：各星级内部的情感构成（堆叠百分比）。"""
    share = pd.read_csv(TABLE_DIR / "q4_star_sentiment_distribution.csv", index_col=0)
    share = share.reindex(columns=["正面占比%", "中性占比%", "负面占比%"]).fillna(0)

    fig, ax = plt.subplots(figsize=(9.4, 5.4))
    x = np.arange(len(share))
    bottom = np.zeros(len(share))
    for col, color, name in [
        ("正面占比%", C["accent"], "正面"),
        ("中性占比%", C["neutral"], "中性"),
        ("负面占比%", C["secondary"], "负面"),
    ]:
        vals = share[col].values.astype(float)
        ax.bar(x, vals, bottom=bottom, color=color, alpha=0.9, label=name, edgecolor="white")
        for i, v in enumerate(vals):
            if v >= 6:
                ax.text(i, bottom[i] + v / 2, f"{v:.1f}%", ha="center", va="center",
                        fontsize=8.5, color="white", fontweight="bold")
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(s)} 星" for s in share.index])
    ax.set_ylabel("占比（%）")
    ax.set_ylim(0, 100)
    ax.set_title("图 8-1  各星级内部的情感标签构成")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False)
    return save_figure(fig, FIG_DIR / "fig8_1_star_sentiment.png")


def fig_star_vs_sentiment() -> Path:
    """图 8-2：星级与情感分的散点与箱线。"""
    df = pd.read_csv(PROCESSED_DIR / "reviews_dual.csv", dtype={"movie_id": str})
    df = df[(df["quality_label"] == "A") & df["sentiment_score"].notna()]

    fig, ax = plt.subplots(figsize=(9.4, 5.6))
    data = [df.loc[df["rating"] == r, "sentiment_score"].dropna().values for r in range(1, 6)]
    bp = ax.boxplot(data, tick_labels=[f"{r}星" for r in range(1, 6)], patch_artist=True,
                    widths=0.55, showfliers=False)
    for patch, color in zip(bp["boxes"], [C["secondary"], C["warm"], C["neutral"],
                                          C["cool"], C["accent"]]):
        patch.set_facecolor(color)
        patch.set_alpha(0.65)

    for i, vals in enumerate(data, start=1):
        jitter = np.random.default_rng(20261109).normal(0, 0.045, size=len(vals))
        ax.scatter(np.full(len(vals), i) + jitter, vals, s=6, alpha=0.14, color=C["primary"])

    ax.axhline(0, color=C["neutral"], lw=1, ls=":")
    ax.set_xlabel("用户星级")
    ax.set_ylabel("文本情感分（-1 负面 → +1 正面）")
    ax.set_title("图 8-2  各星级下的文本情感分分布")
    return save_figure(fig, FIG_DIR / "fig8_2_star_vs_sentiment.png")


# ---------------------------------------------------------------------------
# 第九章：Q5
# ---------------------------------------------------------------------------
def fig_recommendation_scorecard() -> Path:
    """图 9-1：五部推荐影片的多维指标。"""
    t = pd.read_csv(TABLE_DIR / "q5_remake_recommendations.csv")

    fig, axes = plt.subplots(1, 4, figsize=(15.5, 4.6))
    metrics = [
        ("豆瓣评分", "豆瓣评分"), ("被低估指数", "被低估指数"),
        ("类型市场热度", "类型市场热度"), ("综合推荐分", "综合推荐分"),
    ]
    for ax, (col, title) in zip(axes, metrics):
        vals = t[col].astype(float)
        colors = [C["secondary"] if i == 0 else C["primary"] for i in range(len(t))]
        ax.bar(range(len(t)), vals, color=colors, alpha=0.9)
        ax.set_xticks(range(len(t)))
        ax.set_xticklabels([n if len(n) <= 5 else n[:5] + "…" for n in t["电影名称"]],
                           rotation=42, ha="right", fontsize=8.5)
        ax.set_title(title, fontsize=11)
        for i, v in enumerate(vals):
            ax.text(i, v + max(vals) * 0.02, f"{v:.2f}", ha="center", fontsize=7.5)

    fig.suptitle("图 9-1  五部重映推荐影片的多维指标对比", fontsize=15, fontweight="bold")
    fig.tight_layout()
    return save_figure(fig, FIG_DIR / "fig9_1_recommendation_scorecard.png")


def fig_genre_heat() -> Path:
    """图 9-2：类型市场热度赋分。"""
    heat = pd.read_csv(TABLE_DIR / "q5_genre_heat.csv").sort_values("市场热度")

    fig, ax = plt.subplots(figsize=(9.4, 5.2))
    colors = [C["accent"] if v >= 0.75 else (C["warm"] if v >= 0.55 else C["secondary"])
              for v in heat["市场热度"]]
    bars = ax.barh(heat["主类型"], heat["市场热度"], color=colors, alpha=0.9)
    ax.set_xlabel("市场热度赋分（0—1）")
    ax.set_xlim(0, 1.05)
    ax.set_title("图 9-2  各主类型的市场热度赋分（分析者主观判断）")
    for b, v in zip(bars, heat["市场热度"]):
        ax.text(v + 0.012, b.get_y() + b.get_height() / 2, f"{v:.2f}", va="center", fontsize=9)
    return save_figure(fig, FIG_DIR / "fig9_2_genre_heat.png")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def run_all() -> list[str]:
    """
    生成全部图表。

    返回:
        已生成文件的路径列表。
    """
    movies = pd.read_csv(RAW_DIR / "top250_raw.csv", dtype={"movie_id": str})
    for col in ["douban_rating", "rating_count", "release_year"]:
        movies[col] = pd.to_numeric(movies[col], errors="coerce")

    tasks = [
        ("图3-1 清洗漏斗", fig_cleaning_funnel),
        ("图3-2 质量分类", fig_quality_distribution),
        ("图3-3 双维度矩阵", fig_dual_matrix),
        ("图4-1 方法对比", fig_method_comparison),
        ("图5-1 评分分布", lambda: fig_rating_distribution(movies)),
        ("图5-2 评分人数", lambda: fig_rating_count(movies)),
        ("图5-3 评分与人数", lambda: fig_rating_vs_count(movies)),
        ("图6-1 年代分布", lambda: fig_era_distribution(movies)),
        ("图6-2 类型分布", lambda: fig_genre_distribution(movies)),
        ("图6-3 年代×类型", fig_era_genre_heatmap),
        ("图6-4 年代评分", fig_era_rating),
        ("图7-1 低估指数前十", fig_underrated_top10),
        ("图7-2 权重敏感性", fig_weight_sensitivity),
        ("图7-3 高评分低关注", fig_high_rating_low_attention),
        ("图8-1 星级情感构成", fig_star_sentiment_stacked),
        ("图8-2 星级与情感", fig_star_vs_sentiment),
        ("图9-1 推荐评分卡", fig_recommendation_scorecard),
        ("图9-2 类型热度", fig_genre_heat),
    ]

    paths: list[str] = []
    for name, fn in tasks:
        try:
            paths.append(str(fn()))
            logger.info("已生成 %s", name)
        except Exception as exc:
            logger.error("生成 %s 失败: %s", name, exc)

    logger.info("图表生成完成：%d / %d", len(paths), len(tasks))
    return paths


if __name__ == "__main__":
    import json

    _result = run_all()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
