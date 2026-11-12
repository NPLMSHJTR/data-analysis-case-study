"""
src/quality_classification.py
=============================
评论内容有效性分级模块（双维度体系的第一维度）。

分类体系（A—E，另设 X 剔除）
--------------------------
A  有效评论：对剧情、人物、表演、视听语言、主题等有可辨识评价，
   或对影片优缺点作出有依据的判断（含批评性评论）。
B  低信息量：纯表情、纯数字、纯情绪填充，或仅表态而无具体信息。
   注意：B 类不等于无效。「烂片」表达明确负面态度，可进入整体情感统计，
   但不进入高质量内容分析。
C  无关评论：广告引流、与影片无关的个人内容。
D  疑似异常：同片内完全重复或高度相似的副本。只标记「疑似」，
   不断言发布者是水军。
E  待人工判断：语义模糊、反讽、黑话、多层含义，规则无法确定。
X  剔除：字段错位、空文本等结构性损坏。

标签优先级（高→低）：X → C → D → E → B → A
--------------------------------------------
优先级依据「排除优先于归类」：字段不可信则无需谈内容；是广告则无需判情绪；
是重复副本则副本本身不单独计价。这样保证一条评论只得到一个最终标签。
"""

from __future__ import annotations

import re

import pandas as pd

from config import MIN_MEANINGFUL_LENGTH, PROCESSED_DIR, TABLE_DIR
from src.cleaning import is_pure_noise
from src.utils import get_logger

logger = get_logger("quality")

LABEL_NAMES: dict[str, str] = {
    "A": "有效评论",
    "B": "低信息量",
    "C": "无关评论",
    "D": "疑似异常",
    "E": "待人工判断",
    "X": "剔除",
}

# ---------------------------------------------------------------------------
# 词典与正则
# ---------------------------------------------------------------------------
# 广告与营销特征：只在出现明确引流、交易、刷量意图时判为 C 类。
# 刻意不把「淘宝」「拼多多」等平台名单独列为特征，因为正常影评也会提及。
AD_PATTERNS: list[str] = [
    r"加\s*微\s*信", r"加\s*[vV]\s*[信号]?", r"微信号", r"weixin", r"wechat",
    r"优惠\s*券", r"代\s*购", r"刷\s*单", r"兼\s*职", r"日\s*赚",
    r"扫码", r"二维码", r"私\s*聊", r"免费\s*领", r"低价\s*出",
    r"点击\s*链接", r"复制\s*链接", r"关注\s*公众号", r"看\s*片\s*加",
    r"资源\s*分\s*享", r"代\s*写", r"论文\s*代",
    r"blog\.sina\.com\.cn", r"mp\.weixin\.qq\.com", r"taobao\.com", r"tmall\.com",
    r"更多\s*电影\s*评论", r"欢迎\s*访问\s*我的",
]

# 电影评价要素词：出现即说明评论在谈论影片本身的构成
FILM_ASPECT_WORDS: list[str] = [
    # 剧作
    "剧情", "剧本", "故事", "叙事", "情节", "桥段", "设定", "结局", "结尾", "开头",
    "节奏", "铺垫", "反转", "改编", "原著", "主线", "支线", "逻辑", "人设",
    # 人物与表演
    "人物", "角色", "主角", "配角", "演员", "演技", "表演", "塑造", "台词",
    # 视听语言
    "导演", "镜头", "画面", "摄影", "配乐", "音乐", "音效", "剪辑", "特效", "美术",
    "色彩", "构图", "长镜头", "蒙太奇", "调度", "服化道", "场景", "视效",
    # 主题与整体
    "主题", "立意", "内涵", "思想", "表达", "风格", "氛围", "气场", "格调",
    "情感", "情绪", "感动", "共鸣", "震撼", "治愈", "压抑", "沉重",
    # 类型
    "喜剧", "悲剧", "爱情片", "动作片", "科幻片", "文艺片", "商业片", "纪录片",
    "动画", "港片", "国产片", "好莱坞",
]

# 明确的价值判断词：表达对影片整体的好恶
JUDGEMENT_WORDS: list[str] = [
    "好看", "难看", "好片", "烂片", "佳作", "神作", "杰作", "经典", "神剧", "烂剧",
    "精彩", "出色", "优秀", "完美", "惊艳", "震撼", "感动", "喜欢", "讨厌",
    "失望", "无聊", "乏味", "拖沓", "冗长", "俗套", "老套", "尴尬", "做作",
    "值得", "不值", "推荐", "不推荐", "吹爆", "拉胯", "上头", "劝退",
    "百看不厌", "刷了", "重温", "回味", "尽兴", "过瘾", "带感",
    "满分", "良心", "用心", "走心", "差劲", "平庸", "有意思", "没意思",
    "感人", "催泪", "温暖", "治愈", "压抑", "难受", "不适",
    "帅", "漂亮", "辣眼睛", "闷",
]


def has_film_aspect(text: str) -> bool:
    """判断文本是否包含至少一个电影评价要素词。"""
    return any(w in text for w in FILM_ASPECT_WORDS)


def has_judgement(text: str) -> bool:
    """判断文本是否包含明确的价值判断词。"""
    return any(w in text for w in JUDGEMENT_WORDS)


def is_ad(text: str) -> bool:
    """判断文本是否命中广告或营销引流特征。"""
    return any(re.search(p, text, re.IGNORECASE) for p in AD_PATTERNS)


def classify_by_rules(text: str, length: int | None = None) -> tuple[str, str]:
    """
    依据规则对单条评论给出内容有效性标签与理由。

    判定按信息密度分档，核心原则是不因文本短而直接删除：

    | 条件                          | 判定 | 理由                       |
    |-------------------------------|------|----------------------------|
    | 空文本                        | X    | 无可分析内容               |
    | 命中广告特征                  | C    | 与影片无关                 |
    | 纯符号/纯数字/纯表情/纯填充    | B    | 无实义，但保留在情感统计中 |
    | 长度 < 4 且无评价词           | E    | 无法判断                   |
    | 4 ≤ 长度 < 10 且含要素词      | A    | 有具体指向                 |
    | 4 ≤ 长度 < 10 且仅含好恶      | B    | 只有简单喜欢/不喜欢        |
    | 4 ≤ 长度 < 10 且无要素无判断  | E    | 语义模糊                   |
    | 长度 ≥ 10                     | A    | 具备可辨识的观影描述       |

    参数:
        text: 清洗后的评论文本。
        length: 文本长度，未提供时现场计算。

    返回:
        (标签, 理由) 二元组，标签取 A/B/C/E/X。
    """
    if not isinstance(text, str) or not text.strip():
        return "X", "空文本或仅含空白"

    n = length if length is not None else len(text)

    if is_ad(text):
        return "C", "命中广告或营销引流特征"

    if is_pure_noise(text):
        return "B", "纯符号、纯数字、纯表情或纯情绪填充"

    aspect = has_film_aspect(text)
    judge = has_judgement(text)

    if n < MIN_MEANINGFUL_LENGTH:
        if judge:
            return "B", "仅两三个字表达好恶，无具体信息"
        return "E", "文本过短，无法判断是否与影片有关"

    if n < 10:
        if aspect:
            return "A", "提及影片构成要素，可作为有效评价"
        if judge:
            return "B", "仅表达好恶，缺乏具体评价信息"
        return "E", "文本较短且语义模糊，无法确认评价对象"

    if aspect:
        return "A", "包含电影评价要素"
    if judge:
        return "A", "包含明确价值判断且有一定篇幅"
    return "A", "具备一定篇幅的观影描述"


def run_classification() -> dict:
    """
    对清洗后的全量评论执行内容有效性分级。

    输入: data/interim/reviews_cleaned.csv
    输出: data/processed/reviews_labeled.csv
          outputs/tables/quality_distribution.csv

    返回:
        含各标签计数与占比的字典。
    """
    path = PROCESSED_DIR.parent / "interim" / "reviews_cleaned.csv"
    if not path.exists():
        raise FileNotFoundError(f"未找到清洗结果: {path}，请先运行 src.cleaning")

    df = pd.read_csv(path, dtype={"movie_id": str, "review_id": str})
    df["clean_text"] = df["clean_text"].fillna("")

    labels: list[str] = []
    reasons: list[str] = []
    for _, row in df.iterrows():
        if not bool(row["struct_ok"]):
            labels.append("X")
            reasons.append("字段结构错位，无法可靠解析")
            continue
        if row["clean_text"] == "":
            labels.append("X")
            reasons.append("空文本或仅含空白字符")
            continue
        if bool(row["is_duplicate"]):
            labels.append("D")
            reasons.append("与同片其他评论完全重复或高度相似")
            continue
        lab, rsn = classify_by_rules(row["clean_text"], int(row["text_length"]))
        labels.append(lab)
        reasons.append(rsn)

    df["quality_label"] = labels
    df["quality_reason"] = reasons
    # A/B 可进入整体情感统计；仅 A 进入内容分析
    df["include_sentiment"] = df["quality_label"].isin(["A", "B"])
    df["include_content"] = df["quality_label"] == "A"

    out = PROCESSED_DIR / "reviews_labeled.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")

    order = ["A", "B", "C", "D", "E", "X"]
    counts = df["quality_label"].value_counts().reindex(order).fillna(0).astype(int)
    total = len(df)

    dist = pd.DataFrame(
        {
            "标签": order,
            "类别": [LABEL_NAMES[k] for k in order],
            "数量": counts.values,
            "占比": [round(v / total, 6) for v in counts.values],
        }
    )
    dist.to_csv(TABLE_DIR / "quality_distribution.csv", index=False, encoding="utf-8-sig")

    stats = {
        "total": total,
        "counts": counts.to_dict(),
        "shares": {k: round(v / total, 4) for k, v in counts.to_dict().items()},
        "valid_rate": round((counts["A"] + counts["B"]) / total, 4),
        "high_quality_rate": round(counts["A"] / total, 4),
    }
    logger.info(
        "内容分级完成：A=%d B=%d C=%d D=%d E=%d X=%d，有效率 %.2f%%",
        counts["A"], counts["B"], counts["C"], counts["D"], counts["E"], counts["X"],
        stats["valid_rate"] * 100,
    )
    return stats


if __name__ == "__main__":
    import json

    _result = run_classification()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
