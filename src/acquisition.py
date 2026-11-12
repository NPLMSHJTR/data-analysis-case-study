"""
src/acquisition.py
==================
数据采集模块：获取豆瓣 Top250 电影清单与用户短评。

设计原则
--------
1. 只访问公开可访问的页面，不绕过登录、验证码或任何访问控制。
2. 每次网络请求都保存原始响应（HTML 快照），便于事后审计与复核。
3. 采集失败如实记录原因并抛出可捕获的异常，绝不填充伪造数据。
4. 已存在的原始文件默认复用，避免重复请求与覆盖。

数据来源
--------
- 电影榜单：豆瓣电影 Top250 公开榜单页 https://movie.douban.com/top250
  （10 页 × 25 条 = 250 条，无需登录）
- 用户短评：豆瓣短评页在未登录状态下会 302 跳转至 sec.douban.com 安全验证页，
  本项目不绕过该机制，改用第三方公开整理的 Top250 短评数据集：
  GitHub 仓库 xiaobing0222/Douban-Movie-Review-Dataset（2024 年 4 月发布）。
  该数据集按影片分文件存放，字段为 time/uname/comment/star/title/support/sentiment_score。
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import (
    DOUBAN_TOP250_URL,
    EXTERNAL_DIR,
    FORCE_REFETCH,
    RAW_DIR,
    REQUEST_DELAY,
    REQUEST_HEADERS,
    REQUEST_RETRY,
    REQUEST_TIMEOUT,
    REVIEW_DIRNAME,
    REVIEW_FILE_PREFIX,
    TOP250_PAGE_SIZE,
    TOP250_TOTAL_PAGES,
)
from src.utils import get_logger, timestamp

logger = get_logger("acquisition")

HTML_SNAPSHOT_DIR = RAW_DIR / "html_snapshots"
COLLECTION_META_FILE = RAW_DIR / "collection_meta.json"
REVIEW_DIR = EXTERNAL_DIR / REVIEW_DIRNAME

# 榜单页字段与来源说明，写入 meta 供报告引用
SOURCE_NOTE = {
    "movies": "豆瓣电影 Top250 公开榜单页（未登录，未绕过访问控制）",
    "reviews": (
        "Douban-Movie-Review-Dataset（GitHub: xiaobing0222，2024-04 发布），"
        "内容为抓取时的豆瓣页面原始短评"
    ),
}


# ---------------------------------------------------------------------------
# 一、文本与字段解析工具
# ---------------------------------------------------------------------------
def _clean_text(text: str) -> str:
    """
    清理 HTML 片段转换后的文本：去除多余空白、不间断空格与首尾标点。

    参数:
        text: 原始文本。

    返回:
        归一化后的文本。
    """
    text = text.replace("\xa0", " ").replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" /·\t\r\n")


def parse_info_block(info_html: str) -> dict:
    """
    解析榜单条目中的信息段落，提取导演、主演、年份、国家与类型。

    榜单页该段落形如：
        导演: 弗兰克·德拉邦特 Frank Darabont   主演: 蒂姆·罗宾斯 Tim Robbins /...
        1994 / 美国 / 犯罪 剧情

    注意两种页面固有的数据缺陷：
    1. 部分条目导演有多人时，页面把主演压缩为「主...」，此时主演字段留空；
    2. 国家字段可能是多个地区（如「英国 美国」），保留原始串并另取首个地区。

    参数:
        info_html: 条目 <div class="bd"> 内 <p> 的 HTML 字符串。

    返回:
        含 director / actors / release_year / country / country_all / genres 的字典。
    """
    result = {
        "director": "", "actors": "", "release_year": "",
        "country": "", "country_all": "", "genres": "",
    }
    if not isinstance(info_html, str) or not info_html.strip():
        return result

    text = html_lib.unescape(info_html).replace("\xa0", " ")

    segments = re.split(r"<br\s*/?>", text)
    segments = [re.sub(r"<[^>]+>", "", s) for s in segments]
    segments = [re.sub(r"\s+", " ", s).strip(" /·") for s in segments]
    segments = [s for s in segments if s]
    if not segments:
        return result

    crew = segments[0]
    # 页面把主演省略为「主...」：主演不可得，去掉该残段
    if re.search(r"主\s*\.{2,}\s*$", crew):
        crew = re.sub(r"主\s*\.{2,}\s*$", "", crew).strip()

    if "主演" in crew:
        director_part, actor_part = crew.split("主演", 1)
        result["actors"] = _clean_text(actor_part.lstrip(":："))
    else:
        director_part = crew

    result["director"] = _clean_text(director_part.replace("导演", "", 1).lstrip(":："))

    if len(segments) >= 2:
        parts = [p for p in (_clean_text(x) for x in segments[1].split("/")) if p]
        if parts:
            m = re.search(r"(\d{4})", parts[0])
            result["release_year"] = m.group(1) if m else ""
        if len(parts) >= 2:
            result["country_all"] = parts[1]
            tokens = parts[1].split()
            result["country"] = tokens[0] if tokens else ""
        if len(parts) >= 3:
            result["genres"] = parts[-1]

    return result


def parse_top250_page(html: str, collect_time: str) -> list[dict]:
    """
    解析单页 Top250 榜单 HTML，返回电影记录列表。

    参数:
        html: 页面 HTML 文本。
        collect_time: 采集时间字符串，写入每条记录。

    返回:
        电影记录字典列表。
    """
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict] = []

    for item in soup.select("div.item"):
        try:
            rank_el = item.select_one("div.pic em")
            link_el = item.select_one("div.hd a")
            title_els = item.select("div.hd span.title")
            other_el = item.select_one("span.other")
            rating_el = item.select_one("span.rating_num")
            info_p = item.select_one("div.bd p")

            if not (link_el and title_els and rating_el):
                continue

            href = link_el.get("href", "")
            id_match = re.search(r"/subject/(\d+)", href)

            title_cn = _clean_text(title_els[0].get_text())
            original_title = ""
            if len(title_els) > 1:
                original_title = _clean_text(title_els[1].get_text().replace("/", "", 1))

            other_titles = ""
            if other_el:
                other_titles = _clean_text(other_el.get_text()).lstrip("/").strip()

            bd_text = item.select_one("div.bd").get_text(" ", strip=True)
            cnt_match = re.search(r"(\d[\d,]*)\s*人评价", bd_text)
            rating_count = int(cnt_match.group(1).replace(",", "")) if cnt_match else None

            info = parse_info_block(str(info_p)) if info_p else {}

            records.append(
                {
                    "movie_id": id_match.group(1) if id_match else "",
                    "title": title_cn,
                    "original_title": original_title,
                    "other_titles": other_titles,
                    "rank": int(rank_el.get_text(strip=True)) if rank_el else None,
                    "douban_rating": float(rating_el.get_text(strip=True)),
                    "rating_count": rating_count,
                    "release_year": info["release_year"],
                    "country": info["country"],
                    "country_all": info["country_all"],
                    "director": info["director"],
                    "actors": info["actors"],
                    "genres": info["genres"],
                    "runtime": "",  # 榜单页不提供片长，详情页需登录，未采集
                    "collect_time": collect_time,
                    "source": "douban_top250_webpage",
                }
            )
        except Exception as exc:
            logger.warning("单条解析失败，已跳过: %s", exc)
            continue

    return records


# ---------------------------------------------------------------------------
# 二、榜单抓取
# ---------------------------------------------------------------------------
def rebuild_raw_from_snapshots() -> pd.DataFrame:
    """
    从本地已保存的 HTML 快照重新解析榜单数据（不发起网络请求）。

    用于修正解析逻辑后离线重建，不会对目标站点造成额外访问压力，也不伪造数据。

    返回:
        重建后的电影 DataFrame，并覆盖写入原始 CSV/JSON。
    """
    snaps = sorted(
        HTML_SNAPSHOT_DIR.glob("top250_start*.html"),
        key=lambda p: int(re.search(r"start(\d+)", p.name).group(1)),
    )
    if not snaps:
        raise FileNotFoundError(f"未找到 HTML 快照: {HTML_SNAPSHOT_DIR}")

    collect_time = "unknown"
    if COLLECTION_META_FILE.exists():
        meta = json.loads(COLLECTION_META_FILE.read_text(encoding="utf-8"))
        collect_time = meta.get("collect_time", "unknown")

    all_records: list[dict] = []
    for snap in snaps:
        all_records.extend(
            parse_top250_page(snap.read_text(encoding="utf-8"), collect_time)
        )
        logger.info("快照重解析: %s → 累计 %d 条", snap.name, len(all_records))

    df = pd.DataFrame(all_records).sort_values("rank").reset_index(drop=True)
    df.to_csv(RAW_DIR / "top250_raw.csv", index=False, encoding="utf-8-sig")
    (RAW_DIR / "top250_raw.json").write_text(
        json.dumps(df.to_dict(orient="records"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("快照重建完成：%d 条", len(df))
    return df


def fetch_top250(force: bool = FORCE_REFETCH) -> pd.DataFrame:
    """
    抓取豆瓣 Top250 完整榜单（10 页，共 250 条）。

    参数:
        force: 为 True 时忽略已有原始文件，重新抓取。

    返回:
        电影 DataFrame。

    异常:
        RuntimeError: 首屏即被重定向到安全验证页，或全部页面均抓取失败。
    """
    csv_path = RAW_DIR / "top250_raw.csv"
    json_path = RAW_DIR / "top250_raw.json"

    if csv_path.exists() and not force:
        df = pd.read_csv(csv_path, dtype={"movie_id": str})
        logger.info("复用已有原始榜单文件: %s（%d 条）", csv_path.name, len(df))
        return df

    HTML_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)

    all_records: list[dict] = []
    page_stats: list[dict] = []
    collect_time = timestamp()

    for page in range(TOP250_TOTAL_PAGES):
        start = page * TOP250_PAGE_SIZE
        url = f"{DOUBAN_TOP250_URL}?start={start}&filter="

        html = None
        for attempt in range(1, REQUEST_RETRY + 1):
            try:
                resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                if "sec.douban.com" in resp.url or "检测到有异常请求" in resp.text:
                    raise RuntimeError(
                        "请求被重定向至豆瓣安全验证页，属于访问控制机制，本项目不绕过"
                    )
                resp.encoding = resp.apparent_encoding or "utf-8"
                if resp.status_code == 200:
                    html = resp.text
                    break
                logger.warning("第 %d 页状态码 %s（第 %d 次）", page + 1, resp.status_code, attempt)
            except RuntimeError:
                raise
            except requests.RequestException as exc:
                logger.warning("第 %d 页请求异常（第 %d 次）: %s", page + 1, attempt, exc)
            time.sleep(REQUEST_DELAY * attempt)

        if html is None:
            logger.error("第 %d 页抓取失败，已跳过", page + 1)
            page_stats.append({"page": page + 1, "start": start, "records": 0, "status": "failed"})
            continue

        (HTML_SNAPSHOT_DIR / f"top250_start{start}.html").write_text(html, encoding="utf-8")
        records = parse_top250_page(html, collect_time)
        all_records.extend(records)
        page_stats.append({"page": page + 1, "start": start, "records": len(records), "status": "ok"})
        logger.info("第 %d 页完成：%d 条（累计 %d）", page + 1, len(records), len(all_records))
        time.sleep(REQUEST_DELAY)

    if not all_records:
        raise RuntimeError(
            "Top250 榜单抓取失败：未获得任何记录，可能触发访问限制。"
            "本项目不绕过访问控制，请改用经授权的数据源。"
        )

    df = pd.DataFrame(all_records).sort_values("rank").reset_index(drop=True)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(
        json.dumps(df.to_dict(orient="records"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    meta = {
        "collect_time": collect_time,
        "source_url": DOUBAN_TOP250_URL,
        "source_note": SOURCE_NOTE,
        "records": int(len(df)),
        "pages": page_stats,
    }
    COLLECTION_META_FILE.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Top250 抓取完成：%d 条 → %s", len(df), csv_path.name)
    return df


# ---------------------------------------------------------------------------
# 三、评论数据载入
# ---------------------------------------------------------------------------
def normalize_title(text: str) -> str:
    """
    规范化片名，用于跨数据源匹配。

    仅去除首尾空白与结尾标点，不做同义词替换，避免把不同影片误判为同一部。

    参数:
        text: 原始片名。

    返回:
        规范化片名。
    """
    s = str(text).strip().replace("\u3000", " ")
    return re.sub(r"[。．\.！!？?、,，\s]+$", "", s).strip()


def load_reviews(force: bool = False) -> pd.DataFrame:
    """
    合并 148 个分片 CSV，标准化字段并匹配豆瓣电影 ID。

    处理内容：
    1. 逐文件读取并按片名与榜单匹配；
    2. 清理评论时间两侧的换行与缩进；
    3. 用户昵称做 MD5 哈希脱敏（先对唯一值建映射，避免逐行计算）；
    4. 生成全局唯一 review_id。

    参数:
        force: 为 True 时忽略缓存重新合并。

    返回:
        标准化评论 DataFrame；原始目录缺失时返回空表并记录原因。
    """
    cache_path = RAW_DIR / "reviews_raw.csv"
    if cache_path.exists() and not force:
        df = pd.read_csv(cache_path, dtype={"movie_id": str, "review_id": str})
        logger.info("复用已有原始评论文件: %s（%d 条）", cache_path.name, len(df))
        return df

    if not REVIEW_DIR.exists():
        logger.error("未找到短评分片目录: %s", REVIEW_DIR)
        return pd.DataFrame()

    files = sorted(REVIEW_DIR.glob("*.csv"))
    if not files:
        logger.error("短评分片目录为空: %s", REVIEW_DIR)
        return pd.DataFrame()

    top = pd.read_csv(RAW_DIR / "top250_raw.csv", dtype={"movie_id": str})
    title_to_id = {
        normalize_title(t): (mid, t) for t, mid in zip(top["title"], top["movie_id"])
    }

    frames: list[pd.DataFrame] = []
    matched: set[str] = set()
    unmatched: set[str] = set()

    for path in files:
        name = re.sub(rf"^{REVIEW_FILE_PREFIX}", "", path.stem)
        key = normalize_title(name)
        try:
            part = pd.read_csv(path, encoding="utf-8-sig")
        except Exception as exc:
            logger.warning("短评文件读取失败 %s: %s", path.name, exc)
            continue
        if part.empty:
            continue

        if key in title_to_id:
            movie_id, official = title_to_id[key]
            matched.add(official)
        else:
            movie_id, official = "", name
            unmatched.add(name)

        frames.append(part.assign(movie_id=movie_id, movie_name=official))

    if not frames:
        logger.error("未能读取任何短评文件")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    logger.info(
        "短评合并完成：%d 个文件，%d 条评论，匹配影片 %d 部，未匹配 %d 部",
        len(frames), len(df), len(matched), len(unmatched),
    )

    df = df.rename(
        columns={
            "time": "review_time", "uname": "author_raw", "comment": "review_text",
            "star": "rating", "support": "useful_count",
        }
    )

    df["review_time"] = (
        df["review_time"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    )
    df["review_text"] = df["review_text"].astype(str).str.strip()
    df["movie_name"] = df["movie_name"].astype(str).str.strip()

    uniq = df["author_raw"].fillna("__unknown__").astype(str).unique()
    hash_map = {u: hashlib.md5(u.encode("utf-8")).hexdigest()[:16] for u in uniq}
    df["author_id_hash"] = df["author_raw"].fillna("__unknown__").astype(str).map(hash_map)
    df = df.drop(columns=["author_raw"])

    df = df.reset_index(drop=True)
    df["review_id"] = [
        f"{mid or 'NA'}_{i:06d}" for i, mid in zip(df.index, df["movie_id"])
    ]
    df["source"] = "DoubanMovieReviewDataset_public"

    # 数据集自带的第三方情感分仅作参考保留，本项目另行独立计算
    if "sentiment_score" in df.columns:
        df = df.rename(columns={"sentiment_score": "dataset_sentiment_score"})

    keep = [
        "review_id", "movie_id", "movie_name", "rating", "review_text",
        "review_time", "useful_count", "author_id_hash",
        "dataset_sentiment_score", "source",
    ]
    df = df[[c for c in keep if c in df.columns]]

    df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    logger.info("评论原始数据已保存: %s（%d 条）", cache_path.name, len(df))
    return df


def build_coverage(movies: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    """
    统计每部 Top250 影片的评论覆盖数量，用于判断分析可用样本。

    参数:
        movies: Top250 榜单 DataFrame。
        reviews: 标准化评论 DataFrame。

    返回:
        含 movie_id / title / rank / n_reviews / has_reviews 的覆盖率表。
    """
    from config import TABLE_DIR

    if reviews is None or reviews.empty:
        return pd.DataFrame(columns=["movie_id", "title", "n_reviews", "has_reviews"])

    counts = reviews.groupby("movie_id").size().rename("n_reviews")
    cov = movies[["movie_id", "title", "rank"]].copy()
    cov = cov.merge(counts, left_on="movie_id", right_index=True, how="left")
    cov["n_reviews"] = cov["n_reviews"].fillna(0).astype(int)
    cov["has_reviews"] = cov["n_reviews"] > 0
    cov = cov.sort_values("rank").reset_index(drop=True)
    cov.to_csv(TABLE_DIR / "data_review_coverage.csv", index=False, encoding="utf-8-sig")
    return cov


# ---------------------------------------------------------------------------
# 四、总入口
# ---------------------------------------------------------------------------
def run_acquisition(force_reviews: bool = False) -> dict:
    """
    执行全部采集步骤，返回各步骤结果摘要。

    参数:
        force_reviews: 是否强制重新合并短评分片。

    返回:
        含 movies / reviews / coverage 统计的字典。
    """
    summary: dict = {"source_note": SOURCE_NOTE}

    try:
        movies = fetch_top250()
        summary["movies"] = {"status": "ok", "count": int(len(movies))}
    except Exception as exc:
        logger.error("电影榜单采集失败: %s", exc)
        summary["movies"] = {"status": "failed", "count": 0, "reason": str(exc)}
        return summary

    try:
        reviews = load_reviews(force=force_reviews)
        summary["reviews"] = {
            "status": "ok" if len(reviews) else "empty",
            "count": int(len(reviews)),
            "movies_covered": int(
                reviews.loc[reviews["movie_id"] != "", "movie_id"].nunique()
            ) if len(reviews) else 0,
        }
        if len(reviews):
            cov = build_coverage(movies, reviews)
            summary["coverage"] = {
                "movies_total": int(len(cov)),
                "movies_with_reviews": int(cov["has_reviews"].sum()),
                "movies_ge_30": int((cov["n_reviews"] >= 30).sum()),
                "coverage_rate": round(float(cov["has_reviews"].mean()), 4),
            }
    except Exception as exc:
        logger.error("评论数据载入失败: %s", exc)
        summary["reviews"] = {"status": "failed", "count": 0, "reason": str(exc)}

    return summary


if __name__ == "__main__":
    import json

    _result = run_acquisition()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
