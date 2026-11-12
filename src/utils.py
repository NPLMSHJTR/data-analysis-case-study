"""
src/utils.py
============
公共工具模块：日志、中文字体、文件读写、格式化。

所有其他模块通过本模块获取 logger 与绘图环境，保证日志格式与字体设置一致。
"""

from __future__ import annotations

import logging
import math
import random
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np

from config import FONT_CANDIDATES, FIGURE_DPI, LOG_DIR, LOG_LEVEL, RANDOM_SEED

matplotlib.use("Agg")  # 无界面后端，保证在 PyCharm 与服务端环境均可出图
import matplotlib.pyplot as plt  # noqa: E402

_LOGGER_NAME = "douban"
_LOGGER_READY = False


def get_logger(name: str | None = None) -> logging.Logger:
    """
    获取统一配置的日志记录器。

    首次调用时初始化：输出到控制台与 outputs/logs/pipeline.log，重复调用不会重复添加 handler。
    刻意不使用任何 print 语句输出运行信息，全部经由 logging。

    参数:
        name: 子日志器名称，一般传模块名。

    返回:
        配置完成的 Logger。
    """
    global _LOGGER_READY
    logger = logging.getLogger(_LOGGER_NAME if name is None else f"{_LOGGER_NAME}.{name}")

    if not _LOGGER_READY:
        root = logging.getLogger(_LOGGER_NAME)
        root.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        root.addHandler(console)

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(LOG_DIR / "pipeline.log", mode="a", encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)

        root.propagate = False
        _LOGGER_READY = True

    return logger


def set_random_seed(seed: int = RANDOM_SEED) -> None:
    """
    固定 random 与 numpy 的随机种子，保证抽样与模型实验可复现。

    参数:
        seed: 随机种子。
    """
    random.seed(seed)
    np.random.seed(seed)


def setup_chinese_font() -> str:
    """
    为 matplotlib 配置可用中文字体。

    依次尝试配置中的候选字体，返回实际生效的字体名。
    若全部不可用则回退到默认字体并记录警告（图表中文会显示为方框）。

    返回:
        实际使用的字体名称。
    """
    import matplotlib.font_manager as fm

    available = {f.name for f in fm.fontManager.ttflist}
    chosen = next((f for f in FONT_CANDIDATES if f in available), None)

    plt.rcParams["font.sans-serif"] = ([chosen] if chosen else []) + ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.autolayout"] = True
    plt.rcParams["savefig.bbox"] = "tight"

    logger = get_logger("utils")
    if chosen:
        logger.debug("启用中文字体: %s", chosen)
    else:
        logger.warning("未找到候选中文字体，图表中文可能显示异常")
    return chosen or "DejaVu Sans"


def timestamp(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """返回当前本地时间的格式化字符串。"""
    return datetime.now().strftime(fmt)


def save_figure(fig, path: Path, dpi: int | None = None) -> Path:
    """
    保存 matplotlib 图形并关闭，避免内存泄漏。

    参数:
        fig: matplotlib Figure 对象。
        path: 目标路径。
        dpi: 分辨率，默认取配置值。

    返回:
        保存后的路径。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi or FIGURE_DPI, facecolor="white")
    plt.close(fig)
    get_logger("utils").info("图表已保存: %s", path.name)
    return path


def fmt_int(n) -> str:
    """把数字格式化为带千分位的字符串；无法转换时返回 NA。"""
    try:
        return f"{int(round(float(n))):,}"
    except (TypeError, ValueError):
        return "NA"


def fmt_pct(x, digits: int = 2) -> str:
    """把比例格式化为百分比字符串。"""
    try:
        return f"{float(x) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "NA"


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    """
    安全除法，分母为 0 或非法时返回默认值。

    参数:
        a: 分子。
        b: 分母。
        default: 分母非法时的返回值。

    返回:
        除法结果。
    """
    try:
        if b == 0 or not math.isfinite(b):
            return default
        out = a / b
        return out if math.isfinite(out) else default
    except (TypeError, ZeroDivisionError):
        return default


def ensure_dir(path: Path) -> Path:
    """确保目录存在并返回该目录。"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path