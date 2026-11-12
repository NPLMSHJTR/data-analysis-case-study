"""
src/method_comparison.py
========================
方法对比实验：基础清洗法 vs 改进清洗法。

这是本项目「创新点是否有效」的证据所在。任务书要求：
只有改进方法在独立人工验证集上表现更好，才可以声称方法有所改进；
若没有提高，必须分析原因，不能编造优势。

两套方法的定义
--------------
方法一（基础清洗法）
    - 删除空评论
    - 删除完全重复评论
    - 删除命中广告特征的评论
    - 其余全部保留，一律视为「可用评论」
    - 不做长度、噪声、相似度、星级一致性的任何判断

方法二（改进清洗法）
    - 在方法一基础上，增加：
      · 纯噪声识别（纯表情/数字/填充词）
      · 高度相似检测（TF-IDF 余弦 ≥ 0.92）
      · 内容有效性分级（A/B/C/D/E）
      · 星级与文本一致性判定（第二维度）
      · 严重矛盾样本单独隔离

评价维度
--------
1. 保留评论数量与比例
2. 有效评论比例（相对人工认定的「有效」而言）
3. 相对人工标注的 Precision / Recall / F1
4. 不一致评论识别率（人工认定为矛盾、且被方法标记出来的比例）
5. 各影片的有效评论覆盖率

一致性口径说明
--------------
人工标注只有 human_label（内容质量 A—E），没有独立的「一致性」列。
因此「不一致识别率」采用如下可比口径：
    真值：人工判为 A（有效）但最终被方法判为「严重矛盾/不可用」的样本
          这类样本人工认为内容有效、可通过，方法认为有问题
本报告只用它衡量「方法是否过度排斥」，不宣称它能准确识别矛盾。
这一口径的局限在结果解释中明确说明。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import PROCESSED_DIR, TABLE_DIR
from src.cleaning import is_pure_noise
from src.quality_classification import is_ad
from src.utils import get_logger

logger = get_logger("comparison")

# 各标签是否被视为「可用评论」
BASELINE_VALID = {"A", "B", "C", "D", "E"}          # 方法一：除 X 外全保留
IMPROVED_VALID = {"A", "B"}                          # 方法二：仅 A/B


def _baseline_decision(row) -> str:
    """
    方法一的判定：只剔除空文本、完全重复与广告，其余全部保留。

    参数:
        row: 含 clean_text / is_duplicate 的行。

    返回:
        "valid" 或 "reject"。
    """
    text = row["clean_text"]
    if not isinstance(text, str) or not text.strip():
        return "reject"
    if bool(row.get("is_duplicate", False)):
        return "reject"
    if is_ad(text):
        return "reject"
    return "valid"


def _improved_decision(row) -> str:
    """
    方法二的判定：在方法一基础上叠加噪声、相似度与内容分级。

    参数:
        row: 含 quality_label 的行。

    返回:
        "valid" 或 "reject"。
    """
    return "valid" if row["quality_label"] in IMPROVED_VALID else "reject"


def run_method_comparison() -> dict:
    """
    执行两套方法的对比实验。

    输入: data/processed/reviews_dual.csv（含质量标签与一致性）
          data/processed/manual_validation.csv（人工基准）
    输出: outputs/tables/method_comparison.csv
          outputs/tables/method_comparison_by_movie.csv

    返回:
        含两套方法各项指标的字典。
    """
    from sklearn.metrics import precision_recall_fscore_support

    dual_path = PROCESSED_DIR / "reviews_dual.csv"
    if not dual_path.exists():
        raise FileNotFoundError(f"未找到双维度结果: {dual_path}")

    df = pd.read_csv(dual_path, dtype={"movie_id": str, "review_id": str})
    df["clean_text"] = df["clean_text"].fillna("")

    # --- 1. 全量层面的取舍规模 ----------------------------------------
    df["baseline_ok"] = [(_baseline_decision(r) == "valid") for _, r in df.iterrows()]
    df["improved_ok"] = [(_improved_decision(r) == "valid") for _, r in df.iterrows()]

    n_total = len(df)
    n_base = int(df["baseline_ok"].sum())
    n_impr = int(df["improved_ok"].sum())

    # --- 2. 在人工验证集上评估 ----------------------------------------
    mv_path = PROCESSED_DIR / "manual_validation.csv"
    if not mv_path.exists():
        logger.warning("未找到人工验证集，仅输出规模对比")
        mv = None
    else:
        mv = pd.read_csv(mv_path, dtype={"review_id": str})
        mv = mv[
            mv["human_label"].notna()
            & (mv["human_label"].astype(str).str.strip() != "")
        ].copy()

    metrics: dict[str, dict] = {}

    if mv is not None and len(mv):
        ids = set(mv["review_id"])
        sub = df[df["review_id"].isin(ids)].copy()
        sub = sub.merge(
            mv[["review_id", "human_label", "human_sentiment"]], on="review_id", how="inner"
        )

        # 人工真值：是否为「有效评论」。任务书中 A 与 B 都算可保留，
        # 但「有效」在严格意义上指 A，这里采用严格口径（只有 A 算有效），
        # 因为方法对比要检验「能否筛出真正有内容价值的评论」。
        y_true = (sub["human_label"] == "A").astype(int).to_numpy()

        for name, col, valid_set in [
            ("方法一_基础清洗", "baseline_ok", None),
            ("方法二_改进清洗", "improved_ok", None),
        ]:
            if col == "baseline_ok":
                y_pred = sub["baseline_ok"].to_numpy().astype(int)
            else:
                y_pred = sub["improved_ok"].to_numpy().astype(int)

            p, r, f1, _ = precision_recall_fscore_support(
                y_true, y_pred, average="binary", zero_division=0
            )
            acc = float((y_true == y_pred).mean())
            metrics[name] = {
                "准确率": round(acc, 4),
                "精确率": round(float(p), 4),
                "召回率": round(float(r), 4),
                "F1": round(float(f1), 4),
                "保留数": int(y_pred.sum()),
                "样本数": int(len(y_pred)),
            }

        # --- 3. 「过度排斥」率：人工认为有效但被方法剔除 ----------------
        # 用于检验改进方法是否误杀了人工认为可用的评论
        for name, col in [("方法一_基础清洗", "baseline_ok"), ("方法二_改进清洗", "improved_ok")]:
            rej = sub[(sub["human_label"] == "A") & (~sub[col])]
            metrics[name]["误杀人工有效评论数"] = int(len(rej))
            metrics[name]["误杀率"] = round(len(rej) / max(1, (sub["human_label"] == "A").sum()), 4)

        # --- 4. 不一致识别能力（补充指标）------------------------------
        # 口径：人工认为内容有效，但方法二因「严重矛盾」将其隔离的比例。
        # 这一指标衡量方法二能否在保留有效内容的同时把矛盾样本挑出来，
        # 但不代表它能准确判定「矛盾」本身（人工未提供独立的一致性标注）。
        conf_mis = sub[
            (sub["human_label"] == "A") & (sub["consistency"] == "严重矛盾")
        ]
        metrics["方法二_改进清洗"]["矛盾隔离数"] = int(len(conf_mis))
        metrics["方法二_改进清洗"]["矛盾隔离率"] = round(
            len(conf_mis) / max(1, int((sub["human_label"] == "A").sum())), 4
        )
        metrics["方法一_基础清洗"]["矛盾隔离数"] = 0
        metrics["方法一_基础清洗"]["矛盾隔离率"] = 0.0
    else:
        logger.warning("人工验证集为空，无法计算分类指标")

    # --- 5. 影片层面的覆盖率差异 --------------------------------------
    per_movie = (
        df.groupby("movie_id")
        .agg(
            n_total=("review_id", "count"),
            n_baseline=("baseline_ok", "sum"),
            n_improved=("improved_ok", "sum"),
        )
        .reset_index()
    )
    per_movie["baseline_rate"] = (per_movie["n_baseline"] / per_movie["n_total"]).round(4)
    per_movie["improved_rate"] = (per_movie["n_improved"] / per_movie["n_total"]).round(4)
    per_movie["rate_diff"] = (per_movie["improved_rate"] - per_movie["baseline_rate"]).round(4)
    per_movie.to_csv(
        TABLE_DIR / "method_comparison_by_movie.csv", index=False, encoding="utf-8-sig"
    )

    # --- 6. 汇总表 ----------------------------------------------------
    rows = []
    for name in ["方法一_基础清洗", "方法二_改进清洗"]:
        m = metrics.get(name, {})
        rows.append(
            {
                "方法": name,
                "保留评论数": m.get("保留数", n_base if name.startswith("方法一") else n_impr),
                "占全量比例": round(
                    (n_base if name.startswith("方法一") else n_impr) / n_total, 4
                ),
                "准确率": m.get("准确率", np.nan),
                "精确率": m.get("精确率", np.nan),
                "召回率": m.get("召回率", np.nan),
                "F1": m.get("F1", np.nan),
                "误杀率": m.get("误杀率", np.nan),
            }
        )
    comp = pd.DataFrame(rows)
    comp.to_csv(TABLE_DIR / "method_comparison.csv", index=False, encoding="utf-8-sig")

    # --- 7. 结论判定 --------------------------------------------------
    verdict = "无法判定"
    if "方法一_基础清洗" in metrics and "方法二_改进清洗" in metrics:
        f1_base = metrics["方法一_基础清洗"]["F1"]
        f1_impr = metrics["方法二_改进清洗"]["F1"]
        if f1_impr > f1_base + 0.02:
            verdict = "改进方法在 F1 上更优"
        elif abs(f1_impr - f1_base) <= 0.02:
            verdict = "两方法在 F1 上接近"
        else:
            verdict = "改进方法在 F1 上未占优"

    result = {
        "total_reviews": n_total,
        "baseline_kept": n_base,
        "improved_kept": n_impr,
        "baseline_rate": round(n_base / n_total, 4),
        "improved_rate": round(n_impr / n_total, 4),
        "metrics": metrics,
        "verdict": verdict,
        "avg_rate_baseline": round(float(per_movie["baseline_rate"].mean()), 4),
        "avg_rate_improved": round(float(per_movie["improved_rate"].mean()), 4),
    }

    logger.info(
        "方法对比完成：方法一保留 %d（%.2f%%），方法二保留 %d（%.2f%%）；%s",
        n_base, n_base / n_total * 100, n_impr, n_impr / n_total * 100, verdict,
    )
    return result


if __name__ == "__main__":
    import json

    _result = run_method_comparison()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
