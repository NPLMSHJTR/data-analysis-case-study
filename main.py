"""
main.py
=======
项目主程序：一键完成从数据采集到报告生成的全流程。

设计原则
--------
1. 分阶段执行，任一阶段失败不中断后续可独立完成的阶段；
2. 每阶段的成功/失败与耗时写入日志与 run_summary.json；
3. 已有原始数据默认复用，避免重复请求公开站点；
4. 全程使用 logging，不使用 print 输出运行信息（仅摘要表用 print 便于快速查看）。

运行
----
    python main.py

强制重新抓取榜单：
    Windows:  set DOUBAN_FORCE_REFETCH=1 && python main.py
    Linux/Mac: DOUBAN_FORCE_REFETCH=1 python main.py
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import OUTPUT_DIR, PROJECT_NAME, PROJECT_VERSION  # noqa: E402
from src.utils import get_logger, set_random_seed  # noqa: E402

logger = get_logger("main")
SUMMARY_FILE = OUTPUT_DIR / "run_summary.json"


def run_stage(name: str, func, results: dict) -> bool:
    """
    执行单个阶段并记录结果。

    参数:
        name: 阶段名称。
        func: 无参可调用对象。
        results: 汇总字典，原地写入。

    返回:
        True 表示成功。
    """
    logger.info("=" * 68)
    logger.info("阶段开始：%s", name)
    start = time.perf_counter()
    try:
        out = func()
        elapsed = time.perf_counter() - start
        results[name] = {
            "status": "ok",
            "seconds": round(elapsed, 2),
            "result": out if isinstance(out, (dict, list, str, int, float)) else "done",
        }
        logger.info("阶段完成：%s（用时 %.1fs）", name, elapsed)
        return True
    except Exception as exc:
        elapsed = time.perf_counter() - start
        results[name] = {
            "status": "failed",
            "seconds": round(elapsed, 2),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-1500:],
        }
        logger.error("阶段失败：%s —— %s", name, exc)
        return False


def run_pipeline() -> dict:
    """
    按顺序执行全部阶段。

    返回:
        各阶段结果汇总。
    """
    set_random_seed()

    results: dict = {
        "project": PROJECT_NAME,
        "version": PROJECT_VERSION,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    from src import acquisition, cleaning, quality_classification
    from src import sentiment, consistency_check, method_comparison
    from src import statistics, underrated_index, mismatch_analysis
    from src import recommendation, visualization, code_screenshot
    from src import mismatch_cases, report_generator, ppt_generator

    # --- 1. 数据采集 ---------------------------------------------------
    if not run_stage("01_数据采集", acquisition.run_acquisition, results):
        logger.error("数据采集失败，流程终止")
        results["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return results
    if results["01_数据采集"]["result"].get("movies", {}).get("status") != "ok":
        logger.error("榜单数据缺失，流程终止")
        results["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return results

    # --- 2. 文本清洗 ---------------------------------------------------
    run_stage("02_文本清洗", cleaning.run_cleaning, results)

    # --- 3. 内容有效性分级 ---------------------------------------------
    run_stage("03_内容分级", quality_classification.run_classification, results)

    # --- 4. 情感分析 ---------------------------------------------------
    def _sentiment() -> dict:
        """情感分析并评估。"""
        stats = sentiment.run_sentiment()
        stats["evaluation"] = sentiment.evaluate_sentiment()
        return stats

    run_stage("04_情感分析", _sentiment, results)

    # --- 5. 一致性判定（第二维度）--------------------------------------
    run_stage("05_一致性判定", consistency_check.run_consistency_check, results)

    # --- 6. 方法对比实验 -----------------------------------------------
    run_stage("06_方法对比", method_comparison.run_method_comparison, results)

    # --- 7. Q1 / Q2 ----------------------------------------------------
    def _stats() -> dict:
        """执行 Q1 与 Q2。"""
        movies = statistics.load_movies()
        return {
            "q1": statistics.analyze_q1(movies),
            "q2": statistics.analyze_q2(movies),
        }

    run_stage("07_统计分析_Q1Q2", _stats, results)

    # --- 8. Q3 ---------------------------------------------------------
    run_stage("08_被低估指数_Q3", underrated_index.run_underrated_index, results)

    # --- 9. Q4 ---------------------------------------------------------
    def _mismatch() -> dict:
        """Q4 统计，并重建最终 20 条样本表。"""
        stats = mismatch_analysis.run_mismatch_analysis()
        stats["cases"] = mismatch_cases.build_final_cases()
        return stats

    run_stage("09_不一致分析_Q4", _mismatch, results)

    # --- 10. Q5 --------------------------------------------------------
    run_stage("10_重映推荐_Q5", recommendation.run_recommendation, results)

    # --- 11. 图表 ------------------------------------------------------
    run_stage("11_图表生成", visualization.run_all, results)

    # --- 12. 代码截图 --------------------------------------------------
    run_stage("12_代码截图", code_screenshot.run_all, results)

    # --- 13. Word ------------------------------------------------------
    run_stage("13_Word报告", report_generator.main, results)

    # --- 14. PPT -------------------------------------------------------
    run_stage("14_PPT报告", ppt_generator.main, results)

    results["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return results


def print_summary(results: dict) -> None:
    """打印阶段摘要（仅用于终端快速查看）。"""
    print()
    print("=" * 68)
    print("运行摘要")
    print("=" * 68)
    for name, info in results.items():
        if not isinstance(info, dict) or "status" not in info:
            continue
        flag = "成功" if info["status"] == "ok" else "失败"
        print(f"  [{flag}] {name:<22s} {info.get('seconds', 0):>7.1f}s")
        if info["status"] != "ok":
            print(f"         原因: {info.get('error', '')[:110]}")
    print("=" * 68)


def main() -> int:
    """
    入口函数。

    返回:
        0 表示全部阶段成功，1 表示存在失败阶段。
    """
    logger.info("项目启动：%s（v%s）", PROJECT_NAME, PROJECT_VERSION)
    logger.info("工作目录：%s", BASE_DIR)

    results = run_pipeline()
    print_summary(results)

    SUMMARY_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("运行摘要已写入: %s", SUMMARY_FILE)

    failed = [
        k for k, v in results.items()
        if isinstance(v, dict) and v.get("status") == "failed"
    ]
    if failed:
        logger.warning("存在失败阶段：%s", "、".join(failed))
        return 1

    logger.info("全部阶段执行完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())