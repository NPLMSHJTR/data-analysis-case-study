"""
src/cleaning.py
===============
数据清洗模块：文本规范化、重复检测、噪声识别。

本模块只负责「把文本洗干净」与「找出重复/噪声」，不负责质量分级，
分级在 quality_classification.py 中完成。这样拆分的原因是：
基础清洗法（方法一）与改进清洗法（方法二）需要共用同一套文本预处理，
但只在分级逻辑上不同，拆分后两种方法可以公平对比。

清洗规则（按执行顺序）
--------------------
1. 去除 HTML 标签与实体转义残留
2. 去除 URL
3. 统一全角/半角空格，合并连续空白，去首尾空白
4. 保留原始文本与清洗后文本两列，任何一步都可回溯
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from config import MAX_REVIEW_LENGTH, PROCESSED_DIR, RAW_DIR, SIMILARITY_THRESHOLD
from src.utils import get_logger

logger = get_logger("cleaning")

# 正则常量：集中定义便于复核
HTML_TAG = re.compile(r"<[^>]{1,300}>")
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
MULTI_SPACE = re.compile(r"[ \t\u3000]+")
PUNCT_ONLY = re.compile(r"^[\s\W_]+$", re.UNICODE)
DIGIT_ONLY = re.compile(r"^[\d\s\.\-+/%]+$")
EMOJI_PATTERN = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF"
    "\U0000FE00-\U0000FE0F" "\U00002B00-\U00002BFF" "]+",
    flags=re.UNICODE,
)
# 纯情绪填充词：整条文本只由这些构成时判为无实义
FILLER_PATTERN = re.compile(
    r"^(?:哈+|呵+|嘿+|嘻+|嘎+|6+|顶+|赞+|牛+|强+|好+|妙+|啊+|呀+|哇+|嗯+|哦+|"
    r"喵+|汪+|额+|呃+|em+|233+|awsl|yyds|牛批|牛逼|绝了|支持|路过|打卡|签到|"
    r"第一|沙发|前排|马克|留名|收藏|mark)+$",
    re.IGNORECASE,
)


def clean_text(raw) -> str:
    """
    对单条评论文本做规范化清洗，保留语义内容。

    清洗顺序：去 HTML 标签 → 去 URL → 反转义常见实体 → 统一空白 → 去首尾空白。
    刻意不去停用词、不去标点，因为标点本身承载情绪信息（如「！！！」）。

    参数:
        raw: 原始评论文本，可为 None 或非字符串。

    返回:
        清洗后的文本；非字符串输入返回空串。
    """
    if not isinstance(raw, str):
        return ""

    text = HTML_TAG.sub(" ", raw)
    text = URL_PATTERN.sub(" ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("\u3000", " ")
        .replace("\r", " ")
        .replace("\n", " ")
    )
    return MULTI_SPACE.sub(" ", text).strip()


def is_pure_noise(text: str) -> bool:
    """
    判断文本是否为纯符号、纯数字、纯表情或纯情绪填充。

    参数:
        text: 已清洗的文本。

    返回:
        True 表示不含任何可解释的电影评价信息。
    """
    if not isinstance(text, str) or not text.strip():
        return True

    stripped = EMOJI_PATTERN.sub("", text).strip()
    if not stripped:
        return True
    if PUNCT_ONLY.match(stripped):
        return True
    if DIGIT_ONLY.match(stripped):
        return True

    alnum_only = re.sub(r"[\s\W_]+", "", stripped, flags=re.UNICODE)
    if not alnum_only:
        return True
    return bool(FILLER_PATTERN.match(alnum_only))


def mark_duplicates(df: pd.DataFrame, text_col: str = "clean_text") -> pd.Series:
    """
    在同一影片内部标记完全重复与高度相似的评论副本。

    规则：
    - 文本完全相同者，保留最早一条，其余标记为副本；
    - 字符级 TF-IDF（2—4 元）余弦相似度 ≥ 阈值者，标记后续条目；
    - 只在同片内比较，跨片相似不算重复（更可能是巧合）。

    采用字符级 n-gram 而非分词，原因有二：模板化文本往往只改动个别字词，
    字符特征更敏感；且无需引入额外分词词典，方法保持自足。

    参数:
        df: 含 movie_id 与文本列的评论表。
        text_col: 文本列名。

    返回:
        与 df 同索引的布尔 Series，True 表示疑似重复副本。
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    flag = pd.Series(False, index=df.index)

    for _movie_id, group in df.groupby("movie_id", sort=False):
        texts = group[text_col].fillna("").tolist()
        idx = group.index

        # 完全重复：保留首条
        seen: set[str] = set()
        for pos, t in enumerate(texts):
            if not t:
                continue
            if t in seen:
                flag.at[idx[pos]] = True
            else:
                seen.add(t)

        # 高度相似：仅在未被判为重复的条目上检测
        remain_mask = ~flag.loc[idx].to_numpy()
        if remain_mask.sum() < 2:
            continue

        sub_idx = idx[remain_mask]
        sub_texts = [texts[i] for i in range(len(texts)) if remain_mask[i]]

        try:
            vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
            mat = vec.fit_transform(sub_texts)
        except ValueError:
            continue

        n = len(sub_texts)
        block = 512
        for start in range(0, n, block):
            end = min(start + block, n)
            sim = (mat[start:end] @ mat.T).toarray()
            for i in range(end - start):
                earlier = sim[i][: start + i]
                if earlier.size and earlier.max() >= SIMILARITY_THRESHOLD:
                    flag.at[sub_idx[start + i]] = True

    return flag


def run_cleaning() -> dict:
    """
    执行文本清洗与重复标记，输出中间结果。

    输出:
        data/interim/reviews_cleaned.csv  含 clean_text / text_length / is_duplicate

    返回:
        含各环节计数的字典。
    """
    raw_path = RAW_DIR / "reviews_raw.csv"
    if not raw_path.exists():
        raise FileNotFoundError(f"未找到原始评论数据: {raw_path}")

    df = pd.read_csv(raw_path, dtype={"movie_id": str, "review_id": str})
    n_raw = len(df)
    logger.info("读取原始评论 %d 条", n_raw)

    # --- 步骤 1：字段结构校验 -----------------------------------------
    # 时间列应形如 2024-01-01 12:00:00；无法解析说明该行列错位
    time_pat = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
    struct_ok = df["review_time"].fillna("").astype(str).str.match(time_pat)
    n_struct_bad = int((~struct_ok).sum())
    if n_struct_bad:
        logger.warning("检测到 %d 条记录字段错位（源文件表头残缺所致）", n_struct_bad)

    df["useful_count"] = pd.to_numeric(df["useful_count"], errors="coerce")
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["struct_ok"] = struct_ok

    # --- 步骤 2：文本清洗 ---------------------------------------------
    df["clean_text"] = df["review_text"].map(clean_text)
    df["text_length"] = df["clean_text"].str.len()

    # 超长文本截断（不删除），记录原始长度
    df["is_truncated"] = df["text_length"] > MAX_REVIEW_LENGTH
    df.loc[df["is_truncated"], "clean_text"] = df.loc[
        df["is_truncated"], "clean_text"
    ].str.slice(0, MAX_REVIEW_LENGTH)
    df["text_length"] = df["clean_text"].str.len()

    # 第三方数据集的参考情感分（本项目不采用，仅保留）
    df["dataset_sentiment_score"] = pd.to_numeric(
        df.get("dataset_sentiment_score"), errors="coerce"
    )

    # --- 步骤 3：重复检测（仅在有文本且结构正常的记录上做）-------------
    work = df[struct_ok & (df["clean_text"] != "")].copy()
    dup = mark_duplicates(work)
    df["is_duplicate"] = False
    df.loc[dup.index, "is_duplicate"] = dup
    n_dup = int(df["is_duplicate"].sum())

    # 跨影片完全相同的文本：观察刷屏内容，不剔除
    cross = work.groupby("clean_text")["movie_id"].nunique()
    n_cross = int((cross > 1).sum())

    out = PROCESSED_DIR.parent / "interim" / "reviews_cleaned.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")

    stats = {
        "raw_total": n_raw,
        "struct_broken": n_struct_bad,
        "empty_text": int((df["clean_text"] == "").sum()),
        "duplicates": n_dup,
        "truncated": int(df["is_truncated"].sum()),
        "cross_movie_duplicate_texts": n_cross,
        "median_length": round(float(df["text_length"].median()), 1),
    }
    logger.info(
        "清洗完成：原始 %d 条，结构损坏 %d，空文本 %d，重复副本 %d，中位长度 %.0f 字",
        n_raw, n_struct_bad, stats["empty_text"], n_dup, stats["median_length"],
    )
    return stats


if __name__ == "__main__":
    import json

    _result = run_cleaning()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
