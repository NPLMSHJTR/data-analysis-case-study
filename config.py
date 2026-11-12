"""
config.py
=========
豆瓣电影 Top250 数据分析课程项目 —— 全局配置。

本模块集中管理路径、随机种子、采集参数、分类阈值与图表样式。
所有其他模块统一从此处导入配置，避免路径与魔法数字散落各处。
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 一、路径
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent

DATA_DIR: Path = BASE_DIR / "data"
RAW_DIR: Path = DATA_DIR / "raw"
INTERIM_DIR: Path = DATA_DIR / "interim"
PROCESSED_DIR: Path = DATA_DIR / "processed"
EXTERNAL_DIR: Path = DATA_DIR / "external"

OUTPUT_DIR: Path = BASE_DIR / "outputs"
FIG_DIR: Path = OUTPUT_DIR / "figures"
TABLE_DIR: Path = OUTPUT_DIR / "tables"
REPORT_DIR: Path = OUTPUT_DIR / "reports"
LOG_DIR: Path = OUTPUT_DIR / "logs"
SCREENSHOT_DIR: Path = OUTPUT_DIR / "screenshots"

DOCS_DIR: Path = BASE_DIR / "docs"

for _d in (
    DATA_DIR, RAW_DIR, INTERIM_DIR, PROCESSED_DIR, EXTERNAL_DIR,
    OUTPUT_DIR, FIG_DIR, TABLE_DIR, REPORT_DIR, LOG_DIR, SCREENSHOT_DIR, DOCS_DIR,
):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 二、可复现性
# ---------------------------------------------------------------------------
RANDOM_SEED: int = 20261109

# ---------------------------------------------------------------------------
# 三、数据采集
# ---------------------------------------------------------------------------
DOUBAN_TOP250_URL: str = "https://movie.douban.com/top250"
TOP250_PAGE_SIZE: int = 25
TOP250_TOTAL_PAGES: int = 10

REQUEST_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_DELAY: float = 2.0        # 页间延时（秒）
REQUEST_TIMEOUT: int = 25
REQUEST_RETRY: int = 3

REVIEW_DIRNAME: str = "douban_top250_reviews"
REVIEW_FILE_PREFIX: str = "douban_movie_xsk_1-5"

# ---------------------------------------------------------------------------
# 四、评论质量与一致性判定阈值
# ---------------------------------------------------------------------------
MIN_MEANINGFUL_LENGTH: int = 4        # 低于此长度需依赖好恶判断词
MAX_REVIEW_LENGTH: int = 1000
SIMILARITY_THRESHOLD: float = 0.92    # TF-IDF 余弦相似度阈值
MIN_REVIEWS_FOR_INDEX: int = 30       # 被低估指数的最低有效评论数
MANUAL_VALIDATION_SIZE: int = 300

# 情感标签阈值（词典法）
POS_THRESHOLD: float = 0.12
NEG_THRESHOLD: float = -0.12

# 星级与文本一致性的判定门槛
# 一致：星级归一值与情感分方向相同、且差距不大
CONSISTENCY_TOLERANT_GAP: float = 0.55   # |star_norm - sentiment| 小于此值视为一致
CONSISTENCY_SEVERE_GAP: float = 1.10     # 大于此值视为严重矛盾
MIN_CONFIDENCE_FOR_CONSISTENCY: float = 0.25  # 情感置信度低于此值时不参与一致性统计

# ---------------------------------------------------------------------------
# 五、被低估指数权重（基准 + 敏感性分析网格）
# ---------------------------------------------------------------------------
WEIGHT_SENTIMENT_GAP: float = 0.50
WEIGHT_USEFUL: float = 0.30
WEIGHT_ATTENTION: float = 0.20

WEIGHT_SENSITIVITY_GRID: list[tuple[float, float, float]] = [
    (0.50, 0.30, 0.20),  # 基准：均衡，以文本口碑为主
    (0.70, 0.20, 0.10),  # 强化文本口碑差值
    (0.40, 0.40, 0.20),  # 强化评论有用性
    (0.34, 0.33, 0.33),  # 等权
    (0.60, 0.15, 0.25),  # 强化关注度惩罚
]

# 关注度权重的正向/负向方向说明见 underrated_index 模块文档字符串

# ---------------------------------------------------------------------------
# 六、重映推荐的评分权重与约束
# ---------------------------------------------------------------------------
REC_WEIGHTS: dict[str, float] = {
    "rating": 0.15,       # 口碑基础（刻意压低，避免退化为榜单重排）
    "index": 0.25,        # 被低估指数
    "sentiment": 0.15,    # 文本情感强度
    "attention": 0.08,    # 评分人数（受众规模）
    "reviews": 0.07,      # 有效评论数（宣传素材量）
    "era": 0.10,          # 年代稀缺性
    "market": 0.20,       # 类型市场热度（来自公开行业数据）
}

REC_MAX_PER_GENRE_ROUND1: int = 1     # 第一轮：每类型最多 1 部
REC_MAX_PER_GENRE_ROUND2: int = 2     # 第二轮放宽
REC_MAX_PER_DECADE: int = 2
REC_MIN_YEARS_SINCE_RELEASE: int = 8  # 重映需已上映满 8 年
CURRENT_YEAR: int = 2026

# ---------------------------------------------------------------------------
# 七、图表样式
# ---------------------------------------------------------------------------
FIGURE_DPI: int = 160
FIGURE_SIZE: tuple[float, float] = (9.0, 5.4)

FONT_CANDIDATES: list[str] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
    "Source Han Sans CN", "WenQuanYi Zen Hei", "Arial Unicode MS",
]

PALETTE: dict[str, str] = {
    "primary": "#2E5E8C",
    "secondary": "#C0504D",
    "accent": "#4F8A5B",
    "neutral": "#7F7F7F",
    "warm": "#E0A458",
    "cool": "#5B8FA8",
    "purple": "#7B6D8D",
    "teal": "#4A9A96",
}

# ---------------------------------------------------------------------------
# 八、运行控制
# ---------------------------------------------------------------------------
FORCE_REFETCH: bool = os.environ.get("DOUBAN_FORCE_REFETCH", "0") == "1"
LOG_LEVEL: str = os.environ.get("DOUBAN_LOG_LEVEL", "INFO")

PROJECT_NAME: str = "豆瓣电影 Top250 数据分析课程项目"
PROJECT_VERSION: str = "2.0.0"

# 报告封面信息（学生可自行修改）
COVER_INFO: dict[str, str] = {
    "课程名称": "Python 数据分析",
    "项目名称": "豆瓣电影 Top250 数据分析：评论质量识别与口碑价值挖掘",
    "姓名": "",
    "班级": "",
    "学号": "",
    "指导教师": "",
}


def describe_paths() -> str:
    """返回关键路径摘要，供日志与文档使用。"""
    return (
        f"项目根目录: {BASE_DIR}\n"
        f"原始数据: {RAW_DIR}\n"
        f"处理后数据: {PROCESSED_DIR}\n"
        f"图表: {FIG_DIR}\n"
        f"表格: {TABLE_DIR}\n"
        f"报告: {REPORT_DIR}\n"
        f"日志: {LOG_DIR}"
    )