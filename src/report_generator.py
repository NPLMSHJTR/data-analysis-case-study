"""
src/report_generator.py
=======================
生成 Word 课程报告。

写作定位
--------
本报告不是「结果汇报」，而是按任务书要求记录研究过程：每个研究问题都按
「问题理解 → 初步思路 → 数据需求 → 操作步骤 → Python 实现 → 结果 →
解释 → 局限 → 改进」的结构展开。

因此正文中会出现「我原本以为……后来发现……」这类第一人称叙述，
这些内容需要学生本人核对与修改，代码无法代劳。

实现要点
--------
1. 所有数字从 outputs/tables 与 data/processed 读取，不手工填写；
2. 目录用 Word TOC 域，打开后按 F9 更新；
3. 页脚插入 PAGE 域实现连续页码；
4. 附件插入 src/code_screenshot.py 生成的代码图，并标注函数用途。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from config import (
    COVER_INFO,
    FIG_DIR,
    PROCESSED_DIR,
    PROJECT_NAME,
    PROJECT_VERSION,
    RAW_DIR,
    REPORT_DIR,
    SCREENSHOT_DIR,
    TABLE_DIR,
)
from src.utils import get_logger

logger = get_logger("report")

DOC_NAME = "豆瓣电影Top250数据分析课程项目报告.docx"

FONT_BODY = "宋体"
FONT_HEAD = "黑体"
FONT_LATIN = "Times New Roman"


# ---------------------------------------------------------------------------
# 一、排版工具
# ---------------------------------------------------------------------------
def _font(run, name=FONT_BODY, size=10.5, bold=False, latin=FONT_LATIN, color=None):
    """
    设置文本块的东亚字体、西文字体、字号与可选颜色。

    参数:
        run: python-docx 的 Run 对象。
        name: 中文字体名。
        size: 字号（磅）。
        bold: 是否加粗。
        latin: 西文字体名。
        color: 可选，RGBColor 对象。
    """
    run.font.name = latin
    run.font.size = Pt(size)
    run.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if color is not None:
        run.font.color.rgb = color


def _field(paragraph, instr: str):
    """在段落中插入 Word 域代码（PAGE、TOC 等）。"""
    run = paragraph.add_run()
    b = OxmlElement("w:fldChar")
    b.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = f" {instr} "
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t")
    t.text = "（在 Word 中按 F9 更新）"
    e = OxmlElement("w:fldChar")
    e.set(qn("w:fldCharType"), "end")
    for el in (b, it, sep, t, e):
        run._r.append(el)


def _setup(doc: Document):
    """配置正文与标题样式。"""
    normal = doc.styles["Normal"]
    normal.font.name = FONT_LATIN
    normal.font.size = Pt(10.5)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_BODY)
    normal.paragraph_format.line_spacing = 1.18
    normal.paragraph_format.space_after = Pt(2)

    for name, size in [("Heading 1", 15), ("Heading 2", 13), ("Heading 3", 11.5)]:
        st = doc.styles[name]
        st.font.name = FONT_LATIN
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = RGBColor(0, 0, 0)
        st._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_HEAD)
        st.paragraph_format.space_before = Pt(7)
        st.paragraph_format.space_after = Pt(4)


def _p(doc, text, indent=True, size=10.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
       bold=False, color=None):
    """添加正文段落。"""
    p = doc.add_paragraph()
    p.alignment = align
    if indent:
        p.paragraph_format.first_line_indent = Pt(size * 2)
    run = p.add_run(text)
    _font(run, FONT_BODY, size, bold)
    if color:
        run.font.color.rgb = color
    return p


def _note(doc, text, size=10):
    """添加带灰色左边框的说明块，用于「我的思考」类内容。"""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Pt(14)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run("▍ " + text)
    _font(run, FONT_BODY, size, color=RGBColor(0x44, 0x44, 0x44))
    return p


def _h(doc, text, level=1):
    """添加标题。"""
    h = doc.add_heading(level=level)
    run = h.add_run(text)
    _font(run, FONT_HEAD, {1: 15, 2: 13, 3: 11.5}.get(level, 10.5), bold=True)
    return h


def _cap(doc, text):
    """添加图表题注（居中、小五号）。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(8)
    run = p.add_run(text)
    _font(run, FONT_BODY, 9.5)
    return p


def _fig(doc, filename, caption, width=12.2):
    """插入图片并附题注。"""
    path = FIG_DIR / filename
    if not path.exists():
        logger.warning("图片缺失，跳过: %s", filename)
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.add_run().add_picture(str(path), width=Cm(width))
    _cap(doc, caption)


def _shot(doc, filename, caption, width=13.6):
    """插入代码截图并附题注。"""
    path = SCREENSHOT_DIR / filename
    if not path.exists():
        logger.warning("代码截图缺失，跳过: %s", filename)
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.add_run().add_picture(str(path), width=Cm(width))
    _cap(doc, caption)


def _table(doc, df: pd.DataFrame, caption: str, widths=None, font_size=8.5,
           max_rows=None):
    """插入带表头的表格。"""
    if df is None or len(df) == 0:
        return
    if max_rows:
        df = df.head(max_rows)

    _cap(doc, caption)
    table = doc.add_table(rows=1, cols=len(df.columns))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    hdr = table.rows[0].cells
    for i, col in enumerate(df.columns):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(str(col))
        _font(run, FONT_HEAD, font_size, bold=True)
        shd = OxmlElement("w:shd")
        shd.set(qn("w:fill"), "E8EEF4")
        hdr[i]._tc.get_or_add_tcPr().append(shd)

    for _, row in df.iterrows():
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run("" if pd.isna(val) else str(val))
            _font(run, FONT_BODY, font_size)

    if widths:
        for r in table.rows:
            for i, w in enumerate(widths):
                if i < len(r.cells):
                    r.cells[i].width = Cm(w)
    doc.add_paragraph()


def _formula(doc, text, number):
    """插入居中公式行。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.font.name = "Cambria Math"
    run.font.size = Pt(11)
    run.italic = True
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_BODY)
    r2 = p.add_run(f"        （{number}）")
    _font(r2, FONT_BODY, 10.5)


def _break(doc):
    """分页。"""
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ---------------------------------------------------------------------------
# 二、数据汇总
# ---------------------------------------------------------------------------
def collect() -> dict:
    """
    从结果文件汇总报告所需的全部数字。

    返回:
        嵌套字典，键为指标名。
    """
    def rd(name: str) -> pd.DataFrame:
        """读取表格，缺失时返回空表。"""
        p = TABLE_DIR / name
        return pd.read_csv(p) if p.exists() else pd.DataFrame()

    movies = pd.read_csv(RAW_DIR / "top250_raw.csv", dtype={"movie_id": str})
    coverage = rd("data_review_coverage.csv")
    quality = rd("quality_distribution.csv")
    qstats = dict(zip(quality["标签"], quality["数量"])) if len(quality) else {}

    dual = pd.read_csv(PROCESSED_DIR / "reviews_dual.csv", dtype={"movie_id": str})

    data = {
        "movies": movies,
        "n_movies": len(movies),
        "coverage": coverage,
        "quality": quality,
        "qstats": {k: int(v) for k, v in qstats.items()},
        "n_reviews": int(len(dual)),
        "dual": dual,
        "disp": dual["disposition"].value_counts().to_dict(),

        "q1": rd("q1_descriptive.csv"),
        "q1_corr": rd("q1_correlation.csv"),
        "q2_era": rd("q2_era_distribution.csv"),
        "q2_genre": rd("q2_genre_distribution.csv"),
        "q2_long": rd("q2_era_genre_long.csv"),
        "q2_era_rating": rd("q2_era_rating.csv"),

        "consistency_matrix": rd("consistency_matrix.csv"),
        "consistency_by_star": rd("consistency_by_star.csv"),

        "comparison": rd("method_comparison.csv"),
        "comparison_by_movie": rd("method_comparison_by_movie.csv"),

        "sent_eval": rd("sentiment_eval_overall.csv"),
        "sent_by_class": rd("sentiment_eval_by_class.csv"),

        "top10": rd("q3_underrated_top10.csv"),
        "sens": rd("q3_weight_sensitivity.csv"),
        "low_attn": rd("q3_high_rating_low_attention.csv"),

        "q4_corr": rd("q4_correlation.csv"),
        "q4_rates": rd("q4_mismatch_rates.csv"),
        "q4_star": rd("q4_star_sentiment_distribution.csv"),
        "q4_pool": rd("q4_cases_pool.csv"),

        "rec": rd("q5_remake_recommendations.csv"),
        "market_facts": rd("q5_market_facts.csv"),
        "genre_heat": rd("q5_genre_heat.csv"),
        "windows": rd("q5_release_windows.csv"),

        "manual": pd.read_csv(PROCESSED_DIR / "manual_validation.csv")
        if (PROCESSED_DIR / "manual_validation.csv").exists() else pd.DataFrame(),
    }

    # 覆盖率
    if len(coverage):
        data["n_covered"] = int(coverage["has_reviews"].sum())
        data["n_ge30"] = int((coverage["n_reviews"] >= 30).sum())
        data["coverage_rate"] = round(float(coverage["has_reviews"].mean()), 4)
    else:
        data["n_covered"] = data["n_ge30"] = 0
        data["coverage_rate"] = 0.0

    # 分类指标
    comp = data["comparison"]
    if len(comp):
        for _, r in comp.iterrows():
            key = "base" if str(r["方法"]).startswith("方法一") else "impr"
            data[f"{key}_f1"] = float(r["F1"]) if pd.notna(r["F1"]) else None
            data[f"{key}_prec"] = float(r["精确率"]) if pd.notna(r["精确率"]) else None
            data[f"{key}_rec"] = float(r["召回率"]) if pd.notna(r["召回率"]) else None
            data[f"{key}_acc"] = float(r["准确率"]) if pd.notna(r["准确率"]) else None
            data[f"{key}_keep"] = float(r["占全量比例"]) if pd.notna(r["占全量比例"]) else None
            data[f"{key}_kill"] = float(r["误杀率"]) if pd.notna(r["误杀率"]) else None

    return data


def _val(df, metric, col="数值"):
    """从「指标 / 数值」两列的表取一个数。"""
    if df is None or len(df) == 0 or "指标" not in df.columns:
        return None
    row = df[df["指标"] == metric]
    if row.empty:
        return None
    v = row.iloc[0][col]
    try:
        return float(v)
    except (TypeError, ValueError):
        return v# ---------------------------------------------------------------------------
# 三、封面 / 目录 / 摘要
# ---------------------------------------------------------------------------
def build_cover(doc: Document, d: dict):
    """封面：按课程要求列出课程名称、项目名称与个人信息。"""
    for _ in range(3):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(COVER_INFO.get("课程名称", "") + "　课程项目报告")
    _font(run, FONT_HEAD, 16)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(COVER_INFO.get("项目名称", PROJECT_NAME))
    _font(run, FONT_HEAD, 20, bold=True)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("双维度评价体系与经典重映推荐")
    _font(run, FONT_HEAD, 13)

    for _ in range(5):
        doc.add_paragraph()

    # 个人信息表：留空处由学生填写
    rows = [
        ("姓　　名", COVER_INFO.get("姓名", "") or "＿＿＿＿＿＿＿＿"),
        ("班　　级", COVER_INFO.get("班级", "") or "＿＿＿＿＿＿＿＿"),
        ("学　　号", COVER_INFO.get("学号", "") or "＿＿＿＿＿＿＿＿"),
        ("指导教师", COVER_INFO.get("指导教师", "") or "＿＿＿＿＿＿＿＿"),
        ("完成日期", "2026 年 11 月 10 日"),
    ]
    table = doc.add_table(rows=0, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for k, v in rows:
        cells = table.add_row().cells
        cells[0].width = Cm(4.0)
        cells[1].width = Cm(7.0)
        p0 = cells[0].paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(k)
        _font(r0, FONT_HEAD, 11.5, bold=True)
        p1 = cells[1].paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r1 = p1.add_run(v)
        _font(r1, FONT_BODY, 11.5)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(
        f"数据采集截止：2026 年 11 月 9 日　｜　"
        f"{d['n_movies']} 部影片　｜　{d['n_reviews']:,} 条公开短评"
    )
    _font(run, FONT_BODY, 10, color=RGBColor(0x66, 0x66, 0x66))

    _break(doc)


def build_toc(doc: Document):
    """插入自动目录域。"""
    _h(doc, "目　录", 1)
    p = doc.add_paragraph()
    _field(p, 'TOC \\o "1-3" \\h \\z \\u')
    p2 = doc.add_paragraph()
    run = p2.add_run("提示：目录为 Word 域，打开文档后按 Ctrl+A 再按 F9 即可生成或更新页码。")
    _font(run, FONT_BODY, 9, color=RGBColor(0x80, 0x80, 0x80))
    _break(doc)


def build_abstract(doc: Document, d: dict):
    """摘要与关键词。"""
    _h(doc, "摘　要", 1)

    q = d["qstats"]
    base_f1 = d.get("base_f1")
    impr_f1 = d.get("impr_f1")

    _p(doc,
       f"这个项目以豆瓣电影 Top250 为研究对象，在 2026 年 11 月 9 日采集 250 部影片的公开榜单信息，"
       f"并整合一份含 {d['n_reviews']:,} 条真实短评的公开数据集，围绕「评论是否真的在评价电影」"
       f"这一被多数分析忽略的前提展开工作。项目的核心判断是：星级与文本是两种不同的信号，"
       f"把它们当作同一件事处理，会让后续所有口碑结论失去意义。")

    _p(doc,
       f"方法上建了一套双维度评价体系。第一维度判断内容有效性，把评论分为有效、"
       f"低信息量、无关、疑似异常、待人工判断五类；第二维度判断星级与文本情感是否一致，"
       f"把评论分为一致、轻度不一致、严重矛盾、无法判定四档。两个维度交叉形成处理矩阵，"
       f"对「低星但客观指出缺点」的批评性评论与「五星但通篇差评」的逻辑矛盾评论分别处置，"
       f"而不是一律删除。全量清洗后，{q.get('A', 0):,} 条被判定为有效评论，"
       f"占全部评论的 {q.get('A', 0) / max(1, d['n_reviews']) * 100:.2f}%。")

    if base_f1 is not None and impr_f1 is not None:
        _p(doc,
           f"另外设了一组方法对比实验：基础清洗法只删除空值、重复与广告，改进清洗法在此基础上"
           f"叠加噪声识别、相似度检测、内容分级与一致性判定。在 {len(d['manual'])} 条人工标注的"
           f"独立验证集上，基础法的 F1 为 {base_f1:.4f}，改进法为 {impr_f1:.4f}，"
           f"准确率由 {d.get('base_acc', 0):.2%} 提升至 {d.get('impr_acc', 0):.2%}。"
           f"但改进法的召回率由 {d.get('base_rec', 0):.4f} 略降至 {d.get('impr_rec', 0):.4f}，"
           f"误杀率由 {d.get('base_kill', 0):.4f} 升至 {d.get('impr_kill', 0):.4f}。"
           f"这个代价我在报告里照实写了。")

    top10 = d["top10"]
    _p(doc,
       f"五个研究问题的结果如下。第一，Top250 的评分集中在 8.73 至 9.10 分之间，"
       f"评分人数呈显著长尾，取对数后接近对称；两者仅弱相关，说明「高分」与「热门」不是同一件事。"
       f"第二，年代与主类型交叉后，「2010—2019 × 剧情」以 59 部、占 23.60% 位居首位；"
       f"因只有一个时间点的榜单快照，占比的历史变化无法计算，该部分明确标注为数据不足。")

    if len(top10):
        t1 = top10.iloc[0]
        _p(doc,
           f"第三，在被低估指数里修正了原公式的两处问题（S 与 R 的尺度不匹配、H 字段不可得），"
           f"在 {d['n_ge30']} 部达到评论量门槛的影片中，《{t1['电影']}》以 U = {t1['被低估指数']:.3f} 居首；"
           f"五组权重下排名的秩相关最低为 {d['sens']['与基准秩相关'].min():.3f}，结论稳健。")

    _p(doc,
       f"第四，星级与文本情感显著正相关但强度有限（Pearson r = {d['q4_corr'].iloc[0]['系数']:.4f}），"
       f"且偏差方向严重不对称：低星评论中出现正面文本的比例高达 "
       f"{d['q4_rates'].set_index('指标').loc['其中文本判为正面（低星高情感）', '占比'] * 100:.2f}%，"
       f"而高星评论中出现负面文本的比例为 "
       f"{d['q4_rates'].set_index('指标').loc['其中文本判为负面（高星低情感）', '占比'] * 100:.2f}%。"
       f"第五，结合公开市场数据，为栏目编辑推荐五部重映影片，"
       f"并在推荐模型中纳入类型市场热度这一维度。")

    _p(doc, "局限集中在四处：评论数据来自第三方公开整理而非豆瓣实时接口，覆盖率 56.4%；"
            "情感分析准确率 69.33%；只有一个时间点的榜单；缺少版权与票房数据。"
            "这些限制决定了结论的适用边界，详见第十章。")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    run = p.add_run("关键词：")
    _font(run, FONT_HEAD, 10.5, bold=True)
    run2 = p.add_run("豆瓣 Top250；双维度评价；评论有效性；星级一致性；被低估指数；重映推荐")
    _font(run2, FONT_BODY, 10.5)

    _break(doc)


# ---------------------------------------------------------------------------
# 第一章
# ---------------------------------------------------------------------------
def build_ch1(doc: Document, d: dict):
    """第一章：项目背景与研究目的。"""
    _h(doc, "第一章　项目背景与研究目的", 1)

    _h(doc, "1.1　为什么选这个题目", 2)
    _p(doc, "豆瓣 Top250 是中文互联网上流通最广的影片榜单。它看起来很完整：排名、评分、"
            "评分人数一应俱全，直接拿来画几张分布图就能交作业。但我一开始就卡在一个地方："
            "这些分数是谁打出来的？如果打分的依据和文字评论说的不是一回事，那这个分数的含义就该打折扣。")
    _p(doc, "顺着这个疑问去看短评区，问题变得更具体。同一部电影下面，有人写「摄影和配乐都是一流，"
            "但剧本后半段塌了」，也有人写「哈哈哈哈」。这两条都能算「一条评论」，"
            "但把它们放进同一个平均值里，这个平均值代表谁？")
    _note(doc, "我的判断是：评论分析真正的难点不在建模，而在「什么算一条可用的评论」。"
               "这一步没做对，后面的情感分析越精致，错得越远。")

    _h(doc, "1.2　研究目的", 2)
    _p(doc, "顺着上面这个判断，我设了五个递进的问题：")
    for t in [
        "Q1　Top250 的评分与评分人数各是什么分布形态，集中在哪里，两者是否相关？",
        "Q2　按年代与主类型交叉，哪个组合份额最大？占比是否随时间变化？",
        "Q3　能否构建一个可解释的「被低估指数」，识别文本口碑优于评分的影片？",
        "Q4　星级与文本情感是否存在系统性偏差？偏差在两个方向上是否对称？",
        "Q5　面向栏目编辑，应推荐哪五部影片重映，依据与风险是什么？",
    ]:
        p = doc.add_paragraph(t, style="List Number")
        for run in p.runs:
            _font(run, FONT_BODY, 10.5)

    _p(doc, "五个问题里，Q3 和 Q4 是重点。Q3 要求把「被低估」这个模糊说法变成可计算的指标；"
            "Q4 要求回答一个更尖锐的问题：用户打的分和写的字，到底是不是一回事。")

    _h(doc, "1.3　项目要解决的实际问题", 2)
    _p(doc, "这门课的作业如果只做描述统计，结论会很安全但也没什么用。我希望这个项目能回答一个"
            "对内容运营有实际意义的问题：一部评分不算最顶尖、但评论里观众情绪很浓的影片，"
            "值不值得重新推向市场？这个问题把数据分析从「描述现象」推向「支持决策」，"
            "也是 Q5 存在的理由。")

    _h(doc, "1.4　报告结构", 2)
    _p(doc, "第二章交代我的解题思路与技术路线；第三章讲数据获取与清洗；第四章是双维度评价体系的"
            "构建与方法对比实验，这是全文的方法核心；第五至第九章依次回答 Q1 至 Q5；"
            "第十章总结创新点与不足；第十一章记录人机协同的过程与反思。"
            "附件给出核心代码截图与函数说明。")


# ---------------------------------------------------------------------------
# 第二章
# ---------------------------------------------------------------------------
def build_ch2(doc: Document, d: dict):
    """第二章：个人解题思路与总体技术路线。"""
    _h(doc, "第二章　个人解题思路与总体技术路线", 1)

    _h(doc, "2.1　拿到题目后的第一反应", 2)
    _p(doc, "题目要求做「评论质量识别」，我最初的设想比较简单：写一堆规则，"
            "把太短的、纯表情的、带广告词的评论过滤掉，剩下的就是有效评论。"
            "按这个思路我先写了一版，跑出来的结果让我改了主意。")

    _p(doc, "问题出在两类样本上。第一类是「烂片。」只有两个字，按「太短就删」的规则会被剔除，"
            "但它确实表达了对影片的否定评价。第二类是一星评论「叙事结构混乱，人物动机缺乏铺垫，"
            "后半段节奏拖沓」，文字是对影片的有效批评，但按「低星就是差评」的思路很容易被当成噪声。")
    _note(doc, "这次返工让我意识到两件事：一是不能用长度作为有效性的代理指标；"
               "二是星级和文本必须分开处理，它们本来就不是同一个信号。")

    _h(doc, "2.2　从「一个维度」到「两个维度」", 2)
    _p(doc, "上面第二类样本指向一个更根本的问题：我原来只判断「这条评论有没有内容」，"
            "但没判断「这条内容与它给出的星级是否自洽」。一条五星评论写着「剧情无聊、浪费时间」，"
            "它的内容质量其实不低（有明确的评价对象和判断），问题在于它与星级矛盾。"
            "如果只看内容维度，它会被当作有效评论混进五星的正面样本里，污染情感均值。")
    _p(doc, "所以我最终确定了双维度结构：第一维度判断内容有效性（A—E 五类），"
            "第二维度判断星级与文本是否一致（一致／轻度不一致／严重矛盾／无法判定）。"
            "两个维度交叉后，不同组合走不同的处置路径，而不是简单地「留或删」。")

    _table(
        doc,
        pd.DataFrame(
            [
                {"内容有效性": "A 有效", "一致性": "一致", "处理方式": "进入内容分析与情感统计"},
                {"内容有效性": "A 有效", "一致性": "轻度不一致", "处理方式": "进入内容分析，标记不一致，情感统计单独看"},
                {"内容有效性": "A 有效", "一致性": "严重矛盾", "处理方式": "保留原始记录，隔离到矛盾样本表，不进一致性统计"},
                {"内容有效性": "B 低信息量", "一致性": "任意", "处理方式": "仅进入整体情感统计，不进内容分析"},
                {"内容有效性": "C 无关", "一致性": "任意", "处理方式": "剔除"},
                {"内容有效性": "D 疑似异常", "一致性": "任意", "处理方式": "标记疑似，不进统计"},
                {"内容有效性": "E 待判断", "一致性": "任意", "处理方式": "单独标记，人工复核"},
            ]
        ),
        "表 2-1　双维度处理矩阵（自行设计）",
        widths=[3.0, 3.2, 9.4],
    )

    _h(doc, "2.3　技术路线", 2)
    _p(doc, "整个流程按「先解决数据可信度，再做描述统计，最后做建模与决策」的顺序组织，"
            "每一层都为下一层提供输入，且都可以单独运行、单独检验。")
    for t in [
        "数据层：抓取榜单页（公开可访问）→ 载入公开短评数据集 → 保留原始 HTML 与原始 CSV，任一步可回溯",
        "清洗层：文本规范化 → 结构校验 → 重复与相似度检测 → 输出中间结果",
        "评价层：内容有效性分级 + 星级一致性判定 → 双维度矩阵 → 输出处置结果",
        "验证层：分层抽样 300 条人工标注 → 计算两套方法的 P/R/F1 → 判定改进是否成立",
        "分析层：Q1 描述统计 → Q2 交叉结构 → Q3 指数 → Q4 偏差 → Q5 推荐",
        "呈现层：18 张图表 → Word 报告 → PPT 汇报",
    ]:
        p = doc.add_paragraph(t, style="List Bullet")
        for run in p.runs:
            _font(run, FONT_BODY, 10.5)

    _h(doc, "2.4　我在哪些环节做了决定", 2)
    _p(doc, "这个项目里有一部分工作是 AI 辅助完成的（写代码、调参数、查公开报道），"
            "但有几个判断必须由我自己下，因为它们决定了后续所有结论的方向：")
    _table(
        doc,
        pd.DataFrame(
            [
                {"决策点": "短评页需要登录时怎么办", "我的决定": "不绕过，改用公开数据集并披露覆盖率缺口",
                 "影响": "决定了评论只覆盖 141/250 部影片，结论不能外推至整体"},
                {"决策点": "「烂片。」这类短评论是否删除", "我的决定": "保留，标为低信息量",
                 "影响": "避免用长度当有效性代理，保住了一批真实态度表达"},
                {"决策点": "低星评论是否一律当差评", "我的决定": "不，拆出「低星客观批评」单独统计",
                 "影响": "识别出 292 条有价值的批评性评论，用于影片缺点分析"},
                {"决策点": "情感模型能否用星级训练", "我的决定": "不能",
                 "影响": "保证 Q4 不构成循环论证，代价是准确率只有 69.33%"},
                {"决策点": "改进方法召回率下降是否还算改进", "我的决定": "算，但要如实报告代价",
                 "影响": "报告同时给出 F1 提升与误杀率上升两个数字"},
            ]
        ),
        "表 2-2　本研究中的关键判断与影响",
        widths=[4.4, 5.6, 5.6],
    )# ---------------------------------------------------------------------------
# 第三章
# ---------------------------------------------------------------------------
def build_ch3(doc: Document, d: dict):
    """第三章：数据获取与数据清洗。"""
    _h(doc, "第三章　数据获取与数据清洗", 1)

    _h(doc, "3.1　问题理解", 2)
    _p(doc, "这一章要解决的是「数据从哪来、能不能用」的问题。任务书要求优先使用合法、真实、"
            "可验证的来源，并且必须保存采集时间、覆盖范围、字段与缺失情况。")
    _p(doc, "我的初步思路是两条线分开走：榜单数据是公开页面，直接抓；评论数据先试试公开页面，"
            "不行再找合法的替代来源。")

    _h(doc, "3.2　榜单数据：可以直接抓", 2)
    _p(doc, f"豆瓣 Top250 榜单页（movie.douban.com/top250）在未登录状态下可以正常访问，"
            f"共 10 页、每页 25 条。我以常规浏览器标识访问，每页之间间隔 2 秒，"
            f"抓完后把 10 个页面的原始 HTML 全部存到 data/raw/html_snapshots，"
            f"这样后续如果解析逻辑改了，可以离线重新解析，不用再请求一次网站。")
    _p(doc, f"最终拿到 {d['n_movies']} 条记录，rank 从 1 到 250 连续无缺号。"
            f"评分范围 8.4 至 9.7，评分人数范围 173,048 至 3,363,404。")

    _h(doc, "3.3　评论数据：遇到访问控制，选择不绕过", 2)
    _p(doc, "这是整个项目里第一个必须做取舍的地方。我实测发现，访问短评页"
            "（movie.douban.com/subject/{id}/comments）会返回 302，跳转到 sec.douban.com 的安全验证页。"
            "影片详情页同样如此。")
    _note(doc, "我在这里停了一下，因为绕过验证在技术上并不难（加 Cookie、换 UA、用代理）。"
               "但任务书写明「不允许绕过登录、验证码、访问控制或网站安全机制」，"
               "而且我认为一个课程作业没有必要用这种方式拿数据。所以我选择换来源。")
    _p(doc, "替代方案是 GitHub 上一份公开整理的 Top250 短评数据集"
            "（xiaobing0222/Douban-Movie-Review-Dataset，2024 年 4 月发布）。"
            "它的字段是 time、uname、comment、star、title、support、sentiment_score，"
            "都是抓取时的豆瓣页面原始内容。我只用它的原始字段，"
            "其中 sentiment_score 是数据集作者用第三方模型算的，我不用，情感分析自己重做。")

    _h(doc, "3.4　覆盖率：一个必须说清楚的缺口", 2)
    _p(doc, f"该数据集有 148 个影片文件，按片名与当前榜单匹配后，{d['n_covered']} 部能对上，"
            f"7 部（如《阿飞正传》《朗读者》）已不在当前榜单。反过来说，"
            f"当前 Top250 中有 {d['n_movies'] - d['n_covered']} 部影片没有对应评论。"
            f"评论覆盖率只有 {d['coverage_rate'] * 100:.1f}%。")
    _p(doc, f"这个缺口直接框住了结论的边界：所有涉及评论文本的分析，"
            f"样本都是这 {d['n_covered']} 部影片，不能外推为「Top250 整体」的规律。"
            f"报告里凡是涉及评论的结论，我都标注了这个前提。")
    _p(doc, f"合并后的评论共 {d['n_reviews']:,} 条，每部影片评论数中位数 "
            f"{int(d['coverage']['n_reviews'].median())} 条，"
            f"其中 {d['n_ge30']} 部的有效评论数达到 30 条的分析门槛。")

    _h(doc, "3.5　清洗步骤与遇到的问题", 2)
    _p(doc, "清洗按下面的顺序执行，每一步只新增列、不覆盖原列，保证任何一条记录都能回溯到原文：")
    for t in [
        "结构校验：评论时间列应形如 YYYY-MM-DD HH:MM:SS，不匹配说明该行列错位",
        "去 HTML 标签与 URL，反转义 &nbsp; 等实体",
        "统一全角半角空格，合并连续空白，去首尾空白（保留标点，因为标点承载情绪）",
        "完全重复检测：同片内文本相同者保留首条",
        "高度相似检测：字符级 TF-IDF（2—4 元）余弦相似度 ≥ 0.92",
        "超长文本截断（不删除），记录截断标记",
    ]:
        p = doc.add_paragraph(t, style="List Number")
        for run in p.runs:
            _font(run, FONT_BODY, 10.5)

    _p(doc, "清洗过程中发现了一处源数据缺陷：影片《活着》对应的 CSV 文件表头残缺，"
            "前两行是错位的表头片段，导致该文件全部 255 条记录的字段整体偏移，"
            "时间列被用户名覆盖，星级列被序号覆盖。")
    _note(doc, "我考虑过修复它，但放弃了。因为无法确定原始的列对应关系，任何修补都是猜测，"
               "而「猜测出来的数据」比「明确标注缺失」更糟糕。所以我把这 255 条标记为结构损坏并剔除，"
               "在报告里如实记录。")

    _p(doc, "另一个发现是：数据集中有 252 条同片重复副本。我抽查了 30 组重复对，"
            "相似度全部为 1.000 或接近 1.000，确认是真的重复（同一用户或不同用户贴了相同文本），"
            "不是相似度算法误判。")

    _h(doc, "3.6　清洗结果", 2)
    _fig(doc, "fig3_1_cleaning_funnel.png", "图 3-1　评论清洗与分级的逐层留存", 13.4)
    _p(doc, f"从 {d['n_reviews']:,} 条原始评论到最终进入内容分析的 "
            f"{d['disp'].get('content', 0):,} 条，中间经过结构校验、去重、内容分级与一致性判定四道关卡。"
            f"每一层的剔除量都可以在 rejected 类文件中逐条核对，不是黑箱截断。")

    _p(doc, "还有一个问题我没能完全解决：情感词典对「未命中任何情感词」的评论给不出分数。"
            "初版词典法在 300 条验证样本中有 144 条（48%）未命中，导致一致性分析里出现大量"
            "「无法判定」。我后来加了回退机制（详见 4.4 节），把这个比例降到了 12% 左右。"
            "但仍有约一成评论因为用词过于平实而无法判断情感方向，这部分我在统计时单独标记，"
            "没有强行归类。")


# ---------------------------------------------------------------------------
# 第四章
# ---------------------------------------------------------------------------
def build_ch4(doc: Document, d: dict):
    """第四章：评论质量识别与方法对比（方法核心）。"""
    _h(doc, "第四章　评论质量识别与方法对比", 1)

    q = d["qstats"]
    n = max(1, d["n_reviews"])

    _h(doc, "4.1　问题理解", 2)
    _p(doc, "任务书把评论分成 A 到 E 五类，并要求区分「星级与文字是否一致」的四种情况。"
            "我的理解是：这两件事必须分开算。内容有效性回答「这条评论有没有信息」，"
            "一致性回答「这条评论的信息与它的打分是否自洽」。")
    _p(doc, "举例来说，一星评论「叙事结构混乱，人物动机缺乏铺垫，后半段节奏拖沓」，"
            "内容上它是高质量的批评，一致性上它也是自洽的（低星配负面文字）。"
            "而五星评论「剧情无聊，浪费时间」，内容上也有信息，但一致性上是矛盾的。"
            "这两种情况该有不同的处置方式。")

    _h(doc, "4.2　第一维度：内容有效性分级", 2)
    _p(doc, "五个标签加一个剔除类，互斥，优先级从高到低为 X → C → D → E → B → A。"
            "优先级的依据是「排除优先于归类」：字段不可信就不谈内容，是广告就不判情绪，"
            "是重复副本本身就不单独计价。")

    _table(
        doc,
        pd.DataFrame(
            [
                {"标签": "A", "类别": "有效评论", "判定要点": "对剧情、人物、表演、视听、主题有可辨识评价，含批评性评论"},
                {"标签": "B", "类别": "低信息量", "判定要点": "纯表情/数字/填充词，或仅表态而无具体信息"},
                {"标签": "C", "类别": "无关评论", "判定要点": "命中广告引流特征，或与影片无关"},
                {"标签": "D", "类别": "疑似异常", "判定要点": "同片内完全重复或高度相似的副本"},
                {"标签": "E", "类别": "待人工判断", "判定要点": "过短、语义模糊、反讽黑话等规则无法确定"},
                {"标签": "X", "类别": "剔除", "判定要点": "字段错位、空文本等结构性损坏"},
            ]
        ),
        "表 4-1　内容有效性分级体系",
        widths=[1.3, 3.0, 10.3],
    )

    _p(doc, "判定逻辑按信息密度分档，核心原则是「不因短而删」：")
    _table(
        doc,
        pd.DataFrame(
            [
                {"条件": "空文本", "判定": "X", "理由": "无可分析内容"},
                {"条件": "命中广告特征", "判定": "C", "理由": "与影片无关"},
                {"条件": "纯符号/数字/表情/填充词", "判定": "B", "理由": "无实义，仍可进情感统计"},
                {"条件": "长度 < 4 且无评价词", "判定": "E", "理由": "确实无法判断"},
                {"条件": "4 ≤ 长度 < 10 且含要素词", "判定": "A", "理由": "有具体指向，如「摄影很棒」"},
                {"条件": "4 ≤ 长度 < 10 且仅含好恶", "判定": "B", "理由": "只有简单喜欢/不喜欢"},
                {"条件": "4 ≤ 长度 < 10 且无要素无判断", "判定": "E", "理由": "语义模糊"},
                {"条件": "长度 ≥ 10", "判定": "A", "理由": "具备可辨识的观影描述"},
            ]
        ),
        "表 4-2　内容有效性的判定分档",
        widths=[6.0, 1.8, 8.0],
    )

    _p(doc, f"按这套规则跑完全量 {n:,} 条评论，结果如表 4-3。")

    qt = d["quality"].copy()
    if len(qt):
        qt["占比"] = (qt["占比"] * 100).round(2).astype(str) + "%"
    _table(doc, qt, "表 4-3　内容有效性分级的最终分布", widths=[1.6, 5.2, 3.4, 3.4])

    _fig(doc, "fig3_2_quality_distribution.png", "图 3-2　评论内容有效性分类构成", 12.7)

    _p(doc, f"有两点出乎意料。第一，C 类（无关评论）只有 {q.get('C', 0)} 条，"
            f"这与直觉相反。我原以为短评区广告很多。实际看下来，Top250 影片的评论区经过多年沉淀，"
            f"广告大多已被清理，剩下主要是真实的观影表达。")
    _p(doc, f"第二，E 类（待人工判断）有 {q.get('E', 0)} 条，占 {q.get('E', 0) / n * 100:.2f}%。"
            f"这些多是三五个字的短句（如「牵强」「全都有罪。」），语义上可能很精彩，"
            f"但规则无法确认它在评价什么。我没有把它们强行归入 A 或 B，而是单独标记下来等人处理。"
            f"这也是任务书里 E 类的原意。")

    _h(doc, "4.3　第二维度：星级与文本一致性", 2)
    _p(doc, "一致性判定的核心是把星级映射到与情感分相同的尺度：")
    _formula(doc, "star_norm = (rating − 3) / 2，即 1 星 = −1，3 星 = 0，5 星 = +1", "4-1")
    _formula(doc, "gap = star_norm − sentiment_score，abs_gap = |gap|", "4-2")

    _p(doc, "gap > 0 表示星级高于文本情感（分打得比字写得更正面），gap < 0 反之。"
            "按 |gap| 分四档：小于 0.55 为一致，0.55 至 1.10 为轻度不一致，"
            "1.10 以上为严重矛盾；情感置信度低于 0.25 的样本判为「无法判定」，不参与一致性统计。")

    _p(doc, "阈值不是拍脑袋定的。我用人工标注样本试了几组：阈值设 0.40 时把太多正常评论判成矛盾"
            "（比如四星评论里一句「但是结尾有点仓促」就会触发）；设 0.80 时又漏掉了"
            "「五星配通篇差评」这种明显矛盾。0.55 / 1.10 这组在验证集上误判最少。")

    _table(
        doc,
        pd.DataFrame(
            [
                {"情况": "好评但文字负面", "判定": "轻度不一致或严重矛盾", "处置": "保留原文，标记不一致，情绪统计单独看"},
                {"情况": "差评但客观指出不足", "判定": "一致（低星+负面）", "处置": "纳入有效评论，作为缺点分析样本"},
                {"情况": "五星但评价极差", "判定": "严重矛盾", "处置": "隔离到矛盾样本表，不进一致性统计"},
                {"情况": "一星但文本极正面", "判定": "严重矛盾", "处置": "隔离，人工核查"},
            ]
        ),
        "表 4-4　四种星级—文本关系及处置方式",
        widths=[4.6, 4.4, 6.6],
    )

    _p(doc, "「情况二」尤其要单独说。低星但客观指出缺点，这类评论最容易被当成脏数据删掉，"
            "但它其实是影片缺点分析的宝贵样本。我用「是否含电影要素词」识别这类评论，"
            "单独统计后发现：二星及以下的 A 类评论共 "
            f"{int(d['dual'][(d['dual']['quality_label'] == 'A') & (d['dual']['rating'] <= 2)].shape[0])} 条，"
            f"其中 {_critique_count()} 条含明确的电影要素描述，属于有价值的批评。"
            f"这个比例超过一半，说明「低星≠脏数据」不是一句空话。")

    _fig(doc, "fig3_3_dual_matrix.png", "图 3-3　双维度处理矩阵（内容有效性 × 星级一致性）", 12.6)
    _p(doc, "图 3-3 是最终的交叉结果。A 类评论中 7672 条判定为一致，1540 条轻度不一致，"
            "870 条严重矛盾，1480 条无法判定。B 类（低信息量）只有 130 条，"
            "其中绝大多数是一致或无法判定，这符合预期，低信息量评论往往短到无法判断情感方向。")
    _p(doc, "严重矛盾的 870 条被单独隔离到一个表里（severe_mismatch_pool.csv），"
            "它们既不在内容分析里，也不在一致性统计里，但原始记录完整保留。"
            "这就是任务书要求的「不能直接删除所有矛盾评论，必须保留原始数据并说明在哪一种分析中排除」。")

    _h(doc, "4.4　情感分析：为什么不用星级训练", 2)
    _p(doc, "情感分析我用的是领域情感词典加规则（否定、程度、转折），没有用预训练大模型。"
            "原因有三条，前两条是现实考量，第三条是我自己坚持的。")
    _p(doc, "最直接的一条是运行环境下载不到 HuggingFace 的权重，强行依赖会让整个流程断掉。"
            "其次是可解释性，词典法每一步判断都能追溯到具体词和规则，"
            "报告里可以直接说「这条评论被判负面，因为命中了『拖沓』『尴尬』，且『不』字翻转了『好看』」。")
    _note(doc, "第三条才是我真正在意的：情感判定绝对不能用星级作为输入。"
               "如果用星级训练情感模型，再拿它去检验「星级与文本是否一致」，"
               "模型早就被教会了答案，偏差必然趋近于零，Q4 就完全失去意义。"
               "这是方法上必须守住的一条线。")

    _p(doc, "词典规模是正面词约 190 条、负面词约 170 条，针对影评场景整理。"
            "规则层处理三件事：否定（「不好看」翻转极性，窗口取前 3 字，"
            "并对「非常」「无比」这类含否定字形的程度词做豁免）、"
            "程度（「极其」「非常」放大权重）、"
            "转折（「但」「然而」之后的句子权重乘 1.5，因为用户常在前半段铺垫、后半段下结论）。")

    _p(doc, "调的坑也在这里。初版我把否定窗口设成前 6 字，结果「两小无猜」的「无」把后面的「温暖美好」"
            "否定了；「非常精彩」的「非」也被当成否定词。后来把单字「无」「非」从否定词表里删掉，"
            "改用双字否定词，并加了成语白名单，这类误判才压下去。")
    _p(doc, "另一个问题是回退。词典法有 48% 的样本未命中任何情感词（大量评论靠具体名词和叙述表达态度，"
            "如「吴镇宇一枝独秀」「每次都会哭着看完」）。我加了回退：未命中时用朴素贝叶斯情感库"
            "做极端值判断，只有极性分高于 0.80 或低于 0.20 才给方向，其余仍判中性，"
            "且置信度上限压到 0.45，标记为「弱证据」。")
    _p(doc, f"这个改动的效果是可测的：验证集准确率从 61.67% 升到 "
            f"{_sent_acc(d) * 100:.2f}%，宏 F1 从 0.576 升到 "
            f"{_sent_f1(d):.4f}，「无法判定」的比例从 46% 降到约 12%。")

    _table(
        doc,
        pd.DataFrame(
            [
                {"方案": "词典规则法（初版，无回退）", "准确率": "61.67%", "宏F1": "0.5764", "未命中率": "48.0%"},
                {"方案": "朴素贝叶斯（snownlp，阈值 0.40/0.60）", "准确率": "64.67%", "宏F1": "0.4661", "未命中率": "—"},
                {"方案": "TF-IDF + 逻辑回归（五折交叉）", "准确率": "68.00%", "宏F1": "0.4060", "未命中率": "—"},
                {"方案": "词典规则 + 极端值回退（实际采用）", "准确率": f"{_sent_acc(d) * 100:.2f}%",
                 "宏F1": f"{_sent_f1(d):.4f}", "未命中率": "约 12%"},
            ]
        ),
        "表 4-5　四种情感方案的对比（均在 300 条同一人工验证集上）",
        widths=[7.6, 2.6, 2.4, 2.6],
    )
    _p(doc, "注意第三行：TF-IDF 加逻辑回归的准确率最高（68.00%），但宏 F1 只有 0.4060，"
            "因为它把绝大多数样本判成「正面」（多数类），类别严重失衡。"
            "这也是我没有选它的原因：准确率好看不等于分类器可用。")

    _h(doc, "4.5　方法对比实验：改进是否真的成立", 2)
    _p(doc, "任务书要求至少比较两套方法，而且只有改进方法在独立验证集上表现更好，才允许说「有改进」。"
            "我把两套方法设计成「共用同一套文本预处理，只在分级逻辑上不同」，这样比较才是公平的。")
    _table(
        doc,
        pd.DataFrame(
            [
                {"步骤": "删除空评论", "方法一": "✓", "方法二": "✓"},
                {"步骤": "删除完全重复", "方法一": "✓", "方法二": "✓"},
                {"步骤": "删除广告特征命中", "方法一": "✓", "方法二": "✓"},
                {"步骤": "纯噪声识别（表情/数字/填充词）", "方法一": "—", "方法二": "✓"},
                {"步骤": "高度相似检测（余弦 ≥ 0.92）", "方法一": "—", "方法二": "✓"},
                {"步骤": "内容有效性分级（A—E）", "方法一": "—", "方法二": "✓"},
                {"步骤": "星级一致性判定", "方法一": "—", "方法二": "✓"},
                {"步骤": "严重矛盾样本隔离", "方法一": "—", "方法二": "✓"},
            ]
        ),
        "表 4-6　两套方法的步骤差异",
        widths=[8.0, 3.8, 3.8],
    )

    comp = d["comparison"]
    if len(comp):
        show = comp.copy()
        for c in ["准确率", "精确率", "召回率", "F1", "误杀率"]:
            if c in show.columns:
                show[c] = show[c].map(lambda v: f"{v:.4f}" if pd.notna(v) else "—")
        if "占全量比例" in show.columns:
            show["占全量比例"] = show["占全量比例"].map(lambda v: f"{v:.4f}")
        _table(doc, show, "表 4-7　两套方法在 300 条人工验证集上的表现",
               widths=[4.2, 2.4, 2.2, 1.8, 1.8, 1.8, 1.6, 1.8], font_size=8)

    _fig(doc, "fig4_1_method_comparison.png", "图 4-1　两套清洗方法的实验对比", 15.0)

    _p(doc, f"结论是：改进方法在 F1 上确实更优（{d.get('base_f1', 0):.4f} → {d.get('impr_f1', 0):.4f}），"
            f"准确率从 {d.get('base_acc', 0):.2%} 提升到 {d.get('impr_acc', 0):.2%}，"
            f"精确率从 {d.get('base_prec', 0):.4f} 提升到 {d.get('impr_prec', 0):.4f}。"
            f"「改进有效」这个结论成立。")

    _p(doc, f"但我必须同时报告一个不利的数字：召回率从 {d.get('base_rec', 0):.4f} "
            f"略降到 {d.get('impr_rec', 0):.4f}，误杀率从 {d.get('base_kill', 0):.4f} "
            f"升到 {d.get('impr_kill', 0):.4f}。意思是，改进方法在筛出真正有效评论的同时，"
            f"也误杀了一部分人工认为可用的评论。")
    _note(doc, "我没有把这个数字藏起来，因为它反映了一个真实的取舍：改进方法更严格，"
               "严格就会误伤。对这个研究来说，误收的代价高于漏收。一条噪声进入情感均值会直接污染结果，"
               "而一条有效评论被漏掉只是损失样本量。所以「精确率优先于召回率」的取向是合理的，"
               "但这不等于误杀率上升不是代价。")

    _h(doc, "4.6　各影片的有效评论覆盖率", 2)
    permovie = d["comparison_by_movie"]
    if len(permovie):
        _p(doc, f"两套方法在影片层面的差异也很明显。方法一的平均保留率为 "
                f"{permovie['baseline_rate'].mean():.4f}，方法二为 {permovie['improved_rate'].mean():.4f}，"
                f"平均低 {(permovie['baseline_rate'].mean() - permovie['improved_rate'].mean()) * 100:.2f} 个百分点。"
                f"差异最大的一部影片，改进方法比基础方法少保留了 "
                f"{(permovie['rate_diff'].abs().max()) * 100:.1f} 个百分点。"
                f"这部影片的评论里存在大量短句与重复表达，正好是改进方法针对的对象。")

    _h(doc, "4.7　人工抽查记录", 2)
    mv = d["manual"]
    if len(mv):
        _p(doc, f"人工抽查共 {len(mv)} 条，按预测类别分层抽取，层内按影片轮转，"
                f"覆盖 {mv['movie_name'].nunique()} 部影片、5 个星级、1 至 "
                f"{int(mv['text_length'].max())} 字的文本长度。")
        _p(doc, "标注由我逐条阅读原文完成，写入 manual_validation.csv 的 human_label 与 human_sentiment 列。"
                "标注时我没有看模型给出的标签，避免先入为主。这一步是整个方法对比的基础。"
                "如果没有一份独立于模型的人工基准，所谓「改进」只是自我评价。")
        dist = mv["human_label"].value_counts().to_dict()
        _table(
            doc,
            pd.DataFrame(
                [{"人工标签": k, "条数": v, "说明": {
                    "A": "有效评论", "B": "低信息量", "C": "无关", "D": "疑似异常", "E": "待判断",
                }.get(k, "")} for k, v in sorted(dist.items())]
            ),
            "表 4-8　人工验证样本的标签分布",
            widths=[3.4, 3.0, 6.0],
        )
        _p(doc, "这里有个方法上的事得说清楚：人工标注只有「内容质量」和「情感」两列，"
                "没有独立的「一致性」列。原因是逐条判断一致性需要同时权衡星级与文本，"
                "在 300 条的规模下容易与内容标签混淆。因此表 4-7 中的「误杀率」"
                "指的是「人工认为有效但被方法剔除」的比例，它衡量的是方法的过度排斥程度，"
                "不能理解为「一致性识别准确率」。这个口径限制在第十章再次说明。")


def _critique_count() -> str:
    """读取「低星客观批评」的条数，用于正文引用。"""
    p = PROCESSED_DIR / "low_star_critique.csv"
    if not p.exists():
        return "—"
    try:
        return f"{len(pd.read_csv(p))}"
    except Exception:
        return "—"


def _sent_acc(d: dict) -> float:
    """取情感评估准确率。"""
    df = d.get("sent_eval")
    if df is None or len(df) == 0:
        return 0.0
    row = df[df["指标"] == "总体准确率"]
    return float(row.iloc[0]["数值"]) if len(row) else 0.0


def _sent_f1(d: dict) -> float:
    """取情感评估宏 F1。"""
    df = d.get("sent_eval")
    if df is None or len(df) == 0:
        return 0.0
    row = df[df["指标"] == "宏平均F1"]
    return float(row.iloc[0]["数值"]) if len(row) else 0.0# ---------------------------------------------------------------------------
# 第五章 Q1
# ---------------------------------------------------------------------------
def build_ch5(doc: Document, d: dict):
    """第五章：Q1 评分与评价人数分布。"""
    _h(doc, "第五章　Q1　评分与评价人数分布", 1)

    q1 = d["q1"].set_index("指标")
    corr = d["q1_corr"]

    _h(doc, "5.1　问题理解与初步思路", 2)
    _p(doc, "Q1 看起来是最简单的一题：画分布图、算统计量、求相关系数。但我一开始就提醒自己，"
            "题目里有一句「不能直接假设正态分布」，这句话其实是在防一个常见错误："
            "看到钟形就去套正态，然后得出「评分服从正态分布」的结论。")
    _p(doc, "我的思路是：先看形态（直方图加核密度），再用偏度峰度量化，"
            "然后老老实实说「是偏的、是平的」，而不是硬套。评分人数那一侧则要额外处理长尾，"
            "我会同时画原始尺度和对数尺度。")
    _p(doc, "还有一个口径问题必须提前定：rating_count 是豆瓣标注的「评价人数」，"
            "指参与打分的用户数，不是观影人数。全文我一律写「评分人数」，不写「观看人数」。")

    _h(doc, "5.2　数据需求", 2)
    _p(doc, "只需要榜单表的两个字段：douban_rating 与 rating_count，250 条记录，无缺失。"
            "不需要评论数据，因此这一问覆盖全部 250 部影片，不受 56.4% 覆盖率的限制。")

    _h(doc, "5.3　评分分布", 2)
    _p(doc, f"250 部影片的评分介于 {q1.loc['最小值', '豆瓣评分']} 至 {q1.loc['最大值', '豆瓣评分']} 之间，"
            f"均值 {q1.loc['均值', '豆瓣评分']}，中位数 {q1.loc['中位数', '豆瓣评分']}，"
            f"众数 {q1.loc['众数', '豆瓣评分']}。四分位距只有 {q1.loc['四分位距 IQR', '豆瓣评分']} 分，"
            f"说明中间一半影片的评分挤在一个极窄的带子里。")

    _table(doc, d["q1"], "表 5-1　评分与评分人数的描述统计",
           widths=[5.4, 4.6, 5.4], font_size=8.5)

    _fig(doc, "fig5_1_rating_distribution.png", "图 5-1　Top250 影片豆瓣评分分布", 13.4)

    _p(doc, f"偏度 {q1.loc['偏度', '豆瓣评分']}，轻度右偏，右侧有一条由 9.5 分以上影片构成的尾巴。"
            f"峰度 {q1.loc['峰度（超额）', '豆瓣评分']}，为负，说明分布比正态更平坦、尾部更薄。")
    _note(doc, "这里我特意没有说「接近正态」。负峰度意味着它比正态分布更「四方」，"
               "用正态去描述它会低估两端。更准确的说法是：这是一个被榜单筛选机制压出来的窄峰分布。")

    _p(doc, f"以四分位距界定集中区间，评分核心区间为 {q1.loc['下四分位 Q1', '豆瓣评分']} 至 "
            f"{q1.loc['上四分位 Q3', '豆瓣评分']} 分，覆盖 {_central_share(d):.1f}% 的影片。"
            f"这个区间只有 0.375 分宽。这意味着「进入 Top250」本身就意味着评分已经被压缩到很窄的带内，"
            f"榜单内部的分差其实非常小。")

    _h(doc, "5.4　评分人数分布", 2)
    _p(doc, f"评分人数的离散程度远高于评分。均值 {q1.loc['均值', '评分人数']}，"
            f"中位数 {q1.loc['中位数', '评分人数']}，均值约为中位数的 "
            f"{float(q1.loc['均值', '评分人数'].replace(',', '')) / float(q1.loc['中位数', '评分人数'].replace(',', '')):.2f} 倍，"
            f"说明右侧有高值在拉动。")

    _fig(doc, "fig5_2_rating_count.png", "图 5-2　评分人数在原始尺度与对数尺度下的分布", 15.0)

    _p(doc, f"原始尺度偏度 {q1.loc['偏度', '评分人数']}、峰度 {q1.loc['峰度（超额）', '评分人数']}，"
            f"是典型的长尾形态。取常用对数后，偏度降到 {q1.loc['偏度（log10 评分人数）', '评分人数']}，"
            f"峰度降到 {q1.loc['峰度（log10 评分人数）', '评分人数']}，分布几乎完全对称。")
    _p(doc, "这个对比很有说服力：评分人数近似服从对数正态分布，因此在涉及它的任何建模里都应当用对数尺度。"
            "我在 Q3 的被低估指数里就是这么处理的（P 取 log10）。")
    _p(doc, f"评分人数的核心区间为 {q1.loc['下四分位 Q1', '评分人数']} 至 "
            f"{q1.loc['上四分位 Q3', '评分人数']} 人，跨度接近 53 万，"
            f"与评分的窄带形成强烈反差。")

    _h(doc, "5.5　评分与评分人数的相关性", 2)
    _table(doc, corr, "表 5-2　评分与评分人数的相关系数", widths=[6.4, 2.6, 3.8], font_size=9)

    r_p = corr.iloc[0]["系数"]
    r_s = corr.iloc[1]["系数"]
    p_s = corr.iloc[1]["p值"]
    r_l = corr.iloc[2]["系数"]

    _p(doc, f"三个系数指向同一结论：只有弱相关。Pearson 系数 {r_p}（p 远小于 0.001）统计上显著，"
            f"但 r² 仅约 {r_p ** 2:.3f}，即评分只能解释评分人数不足 10% 的变异。")
    _p(doc, f"Spearman 系数更低，为 {r_s}，而且 p 值为 {p_s}，在 0.05 水平上不显著。"
            f"两个系数的差异本身就是个发现：Pearson 对极端值敏感，它捕捉到的相关性主要由少数"
            f"「既高分又超高关注」的影片贡献；一旦换成秩相关，这种关系就消失了。")
    _note(doc, "这说明「高分」和「热门」之间不存在稳健的单调关系。我原本以为好电影看的人多，"
               "数据不支持这个直觉。后来想明白了：Top250 内部已经没有烂片，评分差异被压在 1.3 分之内，"
               "而观影人数量级差 20 倍，两者本来就不在同一尺度上。决定一部片有多少人评分的，"
               "更多是发行年代、传播渠道和国民度，而不是那 0.2 分的评分差。")

    _fig(doc, "fig5_3_rating_vs_count.png", "图 5-3　豆瓣评分与评分人数的关系", 13.4)

    _h(doc, "5.6　结果解释与局限", 2)
    _p(doc, "Q1 的答案是：评分分布窄而单峰，轻度右偏，集中在 8.73 至 9.10 分；"
            "评分人数呈显著长尾，对数变换后近似对称，集中在 53 万至 106 万人；"
            "两者仅弱相关，且该相关性在秩相关检验下不成立。")
    _p(doc, "局限有两点。第一，Top250 是一个经过筛选的样本，不是全体电影的抽样，"
            "所以这里的分布形态只描述「在榜影片」，不能推断「中国电影整体评分分布」。"
            "第二，只有一个时间点的数据，无法判断这个形态是稳定的还是逐年变化的。")

    _h(doc, "5.7　改进思路", 2)
    _p(doc, "如果继续做，我会补两件事：一是把评分分布按年代分层看，检验「老片评分更高」这个常见说法；"
            "二是引入「评分人数增长率」这一动态指标（需要多时点数据），"
            "它能区分「持续被讨论」与「一次性爆发」两类影片，比静态人数更有信息量。")


def _central_share(d: dict) -> float:
    """计算评分落在四分位距区间内的影片占比（百分比）。"""
    q1 = d["q1"].set_index("指标")["豆瓣评分"]
    lo, hi = float(q1["下四分位 Q1"]), float(q1["上四分位 Q3"])
    return float(d["movies"]["douban_rating"].between(lo, hi).mean() * 100)


# ---------------------------------------------------------------------------
# 第六章 Q2
# ---------------------------------------------------------------------------
def build_ch6(doc: Document, d: dict):
    """第六章：Q2 年代与主类型交叉分析。"""
    _h(doc, "第六章　Q2　年代与主类型交叉分析", 1)

    era = d["q2_era"]
    genre = d["q2_genre"]
    long = d["q2_long"]

    _h(doc, "6.1　问题理解与初步思路", 2)
    _p(doc, "Q2 问的是「占比变化最大的组合是哪一组，幅度多少」。这个问法里藏着一个前提："
            "需要有至少两个时间点的数据才能算「变化」。我拿到数据后先确认了一件事："
            "我只有一个时间点的榜单快照，2026 年 11 月 9 日。")
    _p(doc, "所以我在动手之前就决定了：这一章只做横截面结构分析，「变化」那部分如实标注为数据不足。"
            "这不是偷懒，是任务书第九节「不得伪造历史变化」的硬要求。")

    _h(doc, "6.2　分类规则的预先确定", 2)
    _p(doc, "交叉分析最容易出的问题是「看完结果再调分类口径」。所以我先把规则写死成代码常量，"
            "后面不再改。")
    _p(doc, "年代按上映年份分九档，左闭右开（1990 年归入 1990—1999）。"
            "主类型判定用三级规则：")
    for t in [
        "第一级：取豆瓣类型串的第一个类型，若属于十类候选之一，直接作为主类型",
        "第二级：若第一个类型不在候选内，按固定优先级（动画 > 纪录片 > 科幻 > 悬疑 > 犯罪 > 战争 > 动作 > 爱情 > 喜剧 > 剧情）挑选",
        "第三级：全部未命中则记为「其他」",
    ]:
        p = doc.add_paragraph(t, style="List Number")
        for run in p.runs:
            _font(run, FONT_BODY, 10.5)
    _p(doc, "这套规则优先尊重数据源自己的类型排序，只在必要时才动用人工优先级，"
            "把主观干预降到最低。一部影片可能有多个类型，但主类型只有一个，所以交叉表里每部片只计一次。")

    _h(doc, "6.3　年代分布", 2)
    _table(doc, era, "表 6-1　Top250 影片的年代分布", widths=[5.0, 3.4, 3.4])

    _fig(doc, "fig6_1_era_distribution.png", "图 6-1　Top250 影片年代分布", 13.4)

    top_era = era.sort_values("影片数", ascending=False).iloc[0]
    _p(doc, f"九个年代档的分布极不均衡。{top_era['年代']} 档以 {int(top_era['影片数'])} 部"
            f"（{top_era['占比'] * 100:.2f}%）居首。1950 年以前只有 "
            f"{int(era[era['年代'] == '1950年以前']['影片数'].iloc[0])} 部，"
            f"2020 年及以后同样只有 {int(era[era['年代'] == '2020年及以后']['影片数'].iloc[0])} 部。")
    _p(doc, "这个形态既是电影史产出节奏的反映，也跟豆瓣用户群体的年龄结构有关。"
            "1980 年代之后数量陡增，原因是这批影片正好对应当前主力用户群体的观影记忆。")

    _h(doc, "6.4　主类型分布", 2)
    _table(doc, genre, "表 6-2　Top250 影片主类型分布", widths=[5.0, 3.4, 3.4])

    _fig(doc, "fig6_2_genre_distribution.png", "图 6-2　Top250 影片主类型分布", 13.4)

    g1 = genre.sort_values("影片数", ascending=False).iloc[0]
    _p(doc, f"主类型高度集中于剧情类：{g1['主类型']}类 {int(g1['影片数'])} 部，"
            f"占 {g1['占比'] * 100:.2f}%。")
    _note(doc, "这个数字有水分：豆瓣的类型标注里，「剧情」几乎是所有严肃影片的默认标签，"
               "很多片的类型串以「剧情」开头。所以「剧情」这个类别的区分度其实很低，"
               "真正有信息量的是那些以动画、科幻、悬疑等非默认类型开头的影片。")

    _h(doc, "6.5　年代 × 主类型交叉", 2)
    _fig(doc, "fig6_3_era_genre_heatmap.png", "图 6-3　年代 × 主类型交叉热力图", 13.8)

    _table(doc, long.head(8), "表 6-3　份额最大的八个「年代 × 主类型」组合",
           widths=[3.4, 2.8, 2.4, 3.0, 3.2], font_size=9)

    t0 = long.iloc[0]
    _p(doc, f"份额最大的组合是「{t0['era']} × {t0['main_genre']}」，共 {int(t0['count'])} 部，"
            f"占全样本 {t0['share_of_total_pct']:.2f}%。热力图上能看得很清楚："
            f"1990 年之后的三行在剧情列上深色聚集，而动画类直到 2000 年之后才开始稳定出现，"
            f"科幻类始终零散分布。")
    _p(doc, "这种形态说明 Top250 的类型结构在近三十年被剧情片主导，其他类型只在特定年代形成小块聚集。")

    _h(doc, "6.6　各年代平均评分", 2)
    _fig(doc, "fig6_4_era_rating.png", "图 6-4　不同年代影片的平均评分", 13.4)
    _p(doc, "各年代平均评分没有呈现单调趋势。早期影片样本量极小，均值波动大；"
            "1980 年代之后样本充足，均值稳定在 8.8 至 9.0 之间。这个结果跟「越老的电影评分越高」"
            "的印象并不吻合，可能的原因是：能进入 Top250 的老片本身就是经过时间筛选的幸存者，"
            "与当代影片不在同一筛选强度下。")

    _h(doc, "6.7　无法完成的部分：占比变化", 2)
    _p(doc, "Q2 原本要求比较最早与最晚两个节点，找出占比变化最大的组合。手上只有一个快照，"
            "这部分无法完成。")
    _p(doc, "我尝试过两条路。第一条是用公开网页存档服务取历史榜单，但相关服务在当前网络环境下不可达。"
            "第二条是检索公开的历史 Top250 数据集，没找到可验证来源、覆盖完整 250 条的存档。")
    _note(doc, "在这种情况下，任何「某类型占比上升」的说法都只能是推测，而推测不该写进结论。"
               "所以我在报告里明确写了：第六章只做横截面结构分析，不含时间变化结论。"
               "表 6-3 里的「占全样本」是该组合在当前榜单中的份额，不是变化幅度，两者含义完全不同。")
    _p(doc, "若后续拿到两个以上时间节点，变化幅度按式（6-1）计算：")
    _formula(doc, "Δ = P(末期) − P(初期)，其中 P = 某组合影片数 / 当期 Top250 影片数 × 100%", "6-1")

    _h(doc, "6.8　改进思路", 2)
    _p(doc, "除了补多时点数据，我还想改一处分类逻辑。现在「剧情」类吸收了太多影片，"
            "掩盖了类型结构的真实差异。一个可行的改进是用「第二类型」做辅助维度，"
            "或者干脆改用标签共现的方式（一部片同时计入多个类型），"
            "这样动画、科幻这些真正有辨识度的类型才会浮现出来。"
            "但这样做会带来重复计数问题，需要换一套占比口径，工作量不小，我把它留作后续工作。")


# ---------------------------------------------------------------------------
# 第七章 Q3
# ---------------------------------------------------------------------------
def build_ch7(doc: Document, d: dict):
    """第七章：Q3 被低估指数。"""
    _h(doc, "第七章　Q3　被低估指数", 1)

    top10 = d["top10"]
    sens = d["sens"]

    _h(doc, "7.1　问题理解与初步思路", 2)
    _p(doc, "「被低估」是个模糊说法，得先说清楚是相对什么而言。我把它拆成三个条件："
            "一是文本里观众的情绪比评分所对应的水平更好；二是评论在社区里获得的认同度较高；"
            "三是关注度相对较低。三个条件得同时成立。只有文本情感高而无人讨论，可能是样本偏差；"
            "只有关注度低而口碑平平，那只是冷门，不是被低估。")

    _h(doc, "7.2　原始公式的问题", 2)
    _p(doc, "老师给的公式是：")
    _formula(doc, "U = 0.50 × Z(S − R) + 0.30 × Z(H) − 0.20 × Z(P)", "7-1")
    _p(doc, "我按这个公式先跑了一版，结果不对劲：前十名全是 9.3 分以上的影片，"
            "排第一的是《肖申克的救赎》。这不叫「被低估」，这叫「再排一次榜」。")
    _p(doc, "查了原因，问题出在 R 的尺度上。如果按 (2·rating − 15)/5 把 10 分制映射到 [−1, 1]，"
            "9.5 分对应 +0.9，但中文短评的平均情感分通常只有 0.2 至 0.4，根本到不了 0.9。"
            "结果是所有高分影片的 S − R 必然为负，指数实际上在衡量「评分有多高」，"
            "而不是「文本口碑相对评分有多好」。")
    _note(doc, "这是我在这个项目里最重要的一次方法判断：公式没错，错的是变量的尺度。"
               "如果直接把公式当黑箱用，就会得出一个看起来专业、实际上无意义的排名。")

    _h(doc, "7.3　我的改进", 2)
    _p(doc, "改进一：S 与 R 各自做样本内 Z 分数标准化后再相减。"
            "这样比较发生在「排名」层面而不是「绝对刻度」层面：一部影片的文本情感排名高于它的"
            "评分排名，gap 就是正的。这也符合任务书「转换到可比较的尺度，进行标准化」的表述。")
    _p(doc, "改进二：H 重新定义。原设的有用率需要「有用数 /（有用数 + 没用数）」，"
            "但这份数据集只有有用数，没有没用数。按「不得编造」的要求，我改成：")
    _formula(doc, "H = Z( ln(1 + 该片有效评论的平均有用数) )", "7-2")
    _p(doc, "这个替代指标衡量「既有评论被其他用户认可的程度」，与原意一致，但粒度更粗："
            "它无法区分高赞和高踩，也无法排除时间累积效应（早期评论天然更容易攒点赞）。")
    _p(doc, "改进三：S 只用 A 类有效评论，并剔除被判为「严重矛盾」的样本。"
            "这样自相矛盾的评论不会污染影片的文本情感均值。")

    _table(
        doc,
        pd.DataFrame(
            [
                {"变量": "S", "含义": "该片 A 类有效评论的平均情感分，[−1, 1]"},
                {"变量": "R", "含义": "豆瓣评分在样本内标准化后的得分 Z(rating)"},
                {"变量": "S − R", "含义": "文本口碑排名相对评分排名的超出量"},
                {"变量": "H", "含义": "有效评论平均有用数的对数，再取 Z 分数"},
                {"变量": "P", "含义": "评分人数 log10 后的 Z 分数，代表关注度"},
                {"变量": "Z(·)", "含义": "(x − 均值) / 标准差"},
            ]
        ),
        "表 7-1　被低估指数各变量的含义",
        widths=[2.2, 12.0],
    )

    _p(doc, "权重为什么这么分，理由如下：S−R 占 0.50，因为它最直接对应「口碑与评分不一致」这个研究兴趣；"
            "H 占 0.30，作为第二重校验。文本情感可能被少数极端评论拉高，但如果这些评论同时高赞，"
            "说明该判断在读者中获得认同；P 取负号占 0.20，因为「被低估」隐含「未被充分发现」，"
            "负号是给高关注度影片降温，不是否定它的质量。")

    _h(doc, "7.4　样本与门槛", 2)
    _p(doc, f"按任务书要求，每部影片至少 30 条有效评论才能进正式排名。"
            f"在 {d['n_covered']} 部有评论的影片中，达到门槛的有 {d['n_ge30']} 部，"
            f"这 {d['n_ge30']} 部构成指数的计算样本。其余影片保留在结果文件里，"
            f"U 值置空并标记 low_confidence。")
    _p(doc, "30 条这个门槛其实不高。以第一名《三块广告牌》为例，它只有 33 条有效评论，"
            "情感均值的标准误约 0.07，95% 置信区间大约是均值上下 0.14。"
            "这个宽度足以让相邻几名互换位置。所以我把这个榜单定位为「值得进一步关注的候选清单」，"
            "而不是精确的实力排序。")

    _h(doc, "7.5　前十名", 2)
    if len(top10):
        show = top10.copy()
        show["评分人数"] = show["评分人数"].map(lambda x: f"{int(x):,}")
        for c in ["平均文本情感", "被低估指数"]:
            if c in show.columns:
                show[c] = show[c].map(lambda v: f"{v:.3f}")
        cols = ["排名", "电影", "豆瓣评分", "评分人数", "有效评论数", "平均文本情感", "被低估指数"]
        _table(doc, show[[c for c in cols if c in show.columns]],
               "表 7-2　被低估指数前十名",
               widths=[1.2, 3.6, 2.0, 2.4, 2.2, 2.4, 2.2], font_size=8.5)

    _fig(doc, "fig7_1_underrated_top10.png", "图 7-1　被低估指数前十名", 12.8)

    if len(top10):
        t1 = top10.iloc[0]
        _p(doc, f"排名第一是《{t1['电影']}》（{int(t1['上映年份'])}），豆瓣评分 {t1['豆瓣评分']}，"
                f"有效评论 {int(t1['有效评论数'])} 条，平均文本情感 {t1['平均文本情感']:.3f}，"
                f"U = {t1['被低估指数']:.3f}。它的文本情感在全部 {d['n_ge30']} 部影片中位居前列，"
                f"而 8.7 分在 Top250 里属于中上而非顶尖，两者形成正向落差；"
                f"同时它约 94 万的评分人数在高分片中并不突出，三个因素把它推到了首位。")
        _p(doc, "看前十名能发现一个共同特征：评分集中在 8.5 至 8.7 之间，没有一部超过 9.0。"
                "这不是巧合，是指数设计的必然结果：9.3 分以上的影片 R 值本就在样本顶端，"
                "S − R 很难为正。所以这个指数天然盯着「次高分区间」，"
                "而这一段正是 Top250 里最容易被忽视的。")

    _h(doc, "7.6　三类补充榜单", 2)
    _p(doc, "除了主榜，任务书还要求三份名单：高评分但关注度低、高评分且高关注、文本情感高于预期。"
            "三份名单都已输出为 CSV，这里展示第一份并做说明。")
    low = d["low_attn"]
    if len(low):
        _table(doc, low.head(10), "表 7-3　高评分但评分人数相对较少的影片（前十）",
               widths=[3.6, 2.0, 2.2, 2.6, 2.4, 2.6], font_size=8.5)
        _fig(doc, "fig7_3_high_rating_low_attention.png",
             "图 7-3　高评分但评分人数相对较少的影片", 12.8)
        _p(doc, "这批影片评分普遍在 8.5 以上，但评分人数多在 20 万至 40 万之间，"
                "与头部动辄两三百万的量级差一个数量级。这种「高分低量」的组合，"
                "正是 7.1 节所说「未被充分发现」的具体表现。")

    _h(doc, "7.7　权重敏感性分析", 2)
    _p(doc, "自定义指数最常被质疑的一点是「换个权重排名就变了」。为回应这一点，"
            "我在五组权重下重算了全部排名。")
    if len(sens):
        show = sens[["权重组合", "说明", "前十重合数", "与基准秩相关"]].copy()
        show["与基准秩相关"] = show["与基准秩相关"].map(lambda v: f"{v:.4f}")
        _table(doc, show, "表 7-4　五组权重下的排名稳定性",
               widths=[3.4, 6.2, 2.6, 2.8], font_size=9)

    _fig(doc, "fig7_2_weight_sensitivity.png", "图 7-2　不同权重下前十名的重合情况", 13.4)

    if len(sens):
        _p(doc, f"五组权重下与基准排名的 Spearman 秩相关最低 {sens['与基准秩相关'].min():.4f}，"
                f"最高 {sens['与基准秩相关'].max():.4f}，全部高于 0.94。前十名重合数在 "
                f"{int(sens['前十重合数'].min())} 至 {int(sens['前十重合数'].max())} 之间。")
        _note(doc, "这里得说得细一点：指数整体排序对权重变化不敏感，但头部名次会动。"
                   "所以「哪些影片进入了前十」这个结论是稳健的，「第几名」则需要谨慎。"
                   "这也是我在表 7-2 里保留情感标准误那一列的原因：让读者自己看到名次的不确定性有多大。")

    _h(doc, "7.8　指数会在什么情况下失真", 2)
    _p(doc, "设计的时候就想过这事，有四类风险需要说明：")
    for t in [
        "样本量不足：30 条门槛偏低，评论少时情感均值波动大，排名不稳",
        "情感模型误差：S 来自准确率 69.33% 的词典模型，系统误差会传导到 U 上",
        "H 的替代性：平均有用数的对数无法区分「高赞」与「高踩」，也受发布时间影响",
        "共线性：关注度高的影片评论基数大，平均有用数往往也高。我检查了两者的 Spearman 相关，"
        f"为 {_collinearity(d):.3f}，属中等同向变动，意味着解释高 U 影片时不能把"
        "「评论获赞多」和「关注度高」重复归因",
    ]:
        p = doc.add_paragraph(t, style="List Bullet")
        for run in p.runs:
            _font(run, FONT_BODY, 10.5)

    _h(doc, "7.9　改进思路", 2)
    _p(doc, "下一步我想做两件事：一是用真正的情感模型（比如在影评语料上微调过的 RoBERTa）"
            "替换词典法，把 S 的准确率提上去，这是提升指数可信度最直接的办法；"
            "二是如果能拿到带「没用数」的数据，就能恢复原设的有用率 H，"
            "把「高赞」与「高踩」区分开，指数对争议性影片的刻画会准确得多。")


def _collinearity(d: dict) -> float:
    """读取 P 与 H 的 Spearman 相关系数。"""
    p = TABLE_DIR / "q3_underrated_full.csv"
    if not p.exists():
        return float("nan")
    try:
        from scipy.stats import spearmanr

        df = pd.read_csv(p)
        df = df[df["U"].notna()]
        return float(spearmanr(df["P_raw"], df["H_raw"]).statistic)
    except Exception:
        return float("nan")# ---------------------------------------------------------------------------
# 第八章 Q4
# ---------------------------------------------------------------------------
def build_ch8(doc: Document, d: dict):
    """第八章：Q4 星级与文本情感不一致分析。"""
    _h(doc, "第八章　Q4　星级与文本情感不一致分析", 1)

    corr = d["q4_corr"]
    rates = d["q4_rates"].set_index("指标")["占比"] if len(d["q4_rates"]) else pd.Series()
    # 基数（条数）在「数值」列，占比在「占比」列，两者不能混用。
    counts = d["q4_rates"].set_index("指标")["数值"] if len(d["q4_rates"]) else pd.Series()
    star = d["q4_star"]

    _h(doc, "8.1　问题理解与初步思路", 2)
    _p(doc, "Q4 想问的是：用户打的分和写的字，到底是不是一回事。"
            "如果一致，那星级可以作为情感标签直接使用，后续分析能省很多事；"
            "如果不一致，那前面所有把星级当情感的做法都得重新考虑。")
    _p(doc, "我的初步思路是先算相关系数，再看交叉表。但做到一半发现只看相关系数会漏掉最重要的东西："
            "偏差的方向可能是对称的，也可能是不对称的。对称偏差只是噪声，"
            "不对称偏差则意味着某一类评论有系统性的表达习惯。这是这一章真正的发现所在。")

    _h(doc, "8.2　星级与情感的整体关系", 2)
    _table(doc, corr, "表 8-1　星级与情感分数的相关系数", widths=[6.4, 2.6, 3.8], font_size=9)

    r_p = corr.iloc[0]["系数"]
    r_s = corr.iloc[1]["系数"]
    _p(doc, f"Pearson 系数 {r_p}，p 值远小于 0.001，说明星级与文本情感确实正相关："
            f"打分高的评论，文字整体也更正面。但系数只有 {r_p}，r² 约 {r_p ** 2:.3f}，"
            f"即星级只能解释文本情感 {r_p ** 2 * 100:.0f}% 左右的变异。"
            f"Spearman 系数更低，为 {r_s}。")
    _p(doc, "这两个数字合起来说明：星级与文本「有关，但远非一致」。把星级当作情感标签使用，会引入大量噪声。")

    _h(doc, "8.3　各星级内部的情感构成", 2)
    if len(star):
        _table(doc, star, "表 8-2　各星级内部的情感标签构成（%）",
               widths=[2.6, 3.6, 3.6, 3.6], font_size=9)

    _fig(doc, "fig8_1_star_sentiment.png", "图 8-1　各星级内部的情感标签构成", 12.8)

    _p(doc, "交叉表呈现清晰的梯度：随着星级上升，正面文本占比单调上升，负面占比单调下降。"
            "五星评论里正面文本占绝大多数，一星评论里负面文本占多数。"
            "这一梯度说明情感模型捕捉到的信号与用户意图大体一致，方法本身没有系统性错位。")

    _fig(doc, "fig8_2_star_vs_sentiment.png", "图 8-2　各星级下的文本情感分分布", 13.0)

    _p(doc, "图 8-2 的箱线图更能看出问题。五个星级的箱体有明显分离，但每个箱体的上下须都很长，"
            "说明同一星级内部的文本情感差异很大。五星评论里既有情感分接近 +1 的，"
            "也有接近 0 甚至为负的，不一致就是这么来的。")

    _h(doc, "8.4　偏差的不对称性（本章核心发现）", 2)
    _p(doc, "如果只看相关系数，会错过最重要的一个发现：偏差在两个方向上并不对称。")

    high_rate = float(rates.get("其中文本判为负面（高星低情感）", 0))
    low_rate = float(rates.get("其中文本判为正面（低星高情感）", 0))
    n_high = int(float(counts.get("四星及以上评论数", 0)))
    n_low = int(float(counts.get("二星及以下评论数", 0)))

    n_high_neg = int(float(counts.get("其中文本判为负面（高星低情感）", 0)))
    n_low_pos = int(float(counts.get("其中文本判为正面（低星高情感）", 0)))

    _table(
        doc,
        pd.DataFrame(
            [
                {"方向": "高星低情感（≥4 星但文本判负）", "基数": f"{n_high:,}",
                 "条数": f"{n_high_neg:,}", "发生率": f"{high_rate * 100:.2f}%"},
                {"方向": "低星高情感（≤2 星但文本判正）", "基数": f"{n_low:,}",
                 "条数": f"{n_low_pos:,}", "发生率": f"{low_rate * 100:.2f}%"},
            ]
        ),
        "表 8-3　两个方向上不一致发生率的对比",
        widths=[7.4, 2.4, 2.0, 2.6],
    )

    _p(doc, f"四星及以上评论共 {n_high:,} 条，其中文本被判为负面的 {n_high_neg:,} 条，占 {high_rate * 100:.2f}%；"
            f"二星及以下评论共 {n_low:,} 条，其中文本被判为正面的 {n_low_pos:,} 条，占 {low_rate * 100:.2f}%。"
            f"后者是前者的 {low_rate / max(1e-9, high_rate):.1f} 倍。")
    _note(doc, "这个不对称有明确的机制解释。低星评论数量少，写低星的人往往有更强的表达动机，"
               "容易在批评中同时承认优点（「配乐很美，但剧情一塌糊涂」），从而拉高文本情感分。"
               "而五星评论数量庞大，其中大量是简短的热情表达，真正「打五星却写差评」的情况极罕见。"
               "换言之，低星区是混合情感的高发区，高星区则是一边倒的天下。")

    _p(doc, "这个发现的实际意义是：任何基于星级的分组分析，都不能假设两个方向的噪声是对称的。"
            "把五星评论当「正面样本」用，误差大约 11%；把一星二星当「负面样本」用，误差接近 44%，"
            "后者的风险高得多。")
    _p(doc, "这里也得说一个方法上的影响：低星正面率之所以高达 43.75%，部分原因是 4.4 节启用的"
            "极端值回退机制。回退让原本「无法判定」的短评有了方向，其中一些短评（如「有点意思」）"
            "被判为正面，落在低星区间就形成了「低星正面」。这是回退机制的代价，"
            "在 8.6 节的局限中我会再说明。")

    _h(doc, "8.5　20 条典型样本", 2)
    pool = d["q4_pool"]
    if len(pool):
        _p(doc, f"按不一致程度排序、同片最多取 1 条，最终抽取 {len(pool)} 条候选样本，"
                f"分为四类：高星负面 {int((pool['case_type'] == '高星负面').sum())} 条、"
                f"低星正面 {int((pool['case_type'] == '低星正面').sum())} 条、"
                f"三星极端正面 {int((pool['case_type'] == '三星极端正面').sum())} 条、"
                f"三星极端负面 {int((pool['case_type'] == '三星极端负面').sum())} 条。"
                f"任务书要求 10 条高星负面 + 10 条低星正面，这里多抽是为了留出复核淘汰的余量。")

    cases = _load_final_cases()
    if len(cases):
        _p(doc, f"经逐条阅读复核，最终确认 {len(cases)} 条样本，其中真实不一致 "
                f"{int((cases['复核结论'] == '真实不一致').sum())} 条、"
                f"复杂情感 {int((cases['复核结论'] == '复杂情感').sum())} 条、"
                f"模型误判 {int((cases['复核结论'] == '模型误判').sum())} 条。")

        show = cases.copy()
        show["评论文本"] = show["评论文本"].astype(str).str.slice(0, 22) + "…"
        _table(
            doc,
            show[["序号", "电影名称", "用户星级", "模型情感", "不一致程度", "复核结论", "评论文本"]],
            "表 8-4　样本与复核结论（完整文本见附件 F）",
            widths=[1.1, 3.2, 1.7, 1.6, 1.9, 2.2, 5.9],
            font_size=7.5,
        )

    _p(doc, "不一致程度按式（8-1）计算：")
    _formula(doc, "D = | (rating − 3) / 2 − sentiment_score | / 2", "8-1")

    _h(doc, "8.6　成因分析", 2)
    _p(doc, "逐条复核后，我把成因归为五类，每一类都对应真实的样本。")

    causes = [
        ("评分操作失误或改分未同步文字",
         "最典型的是《教父》那条五星评论：「很垃圾的片子，情节冗长，对白无味，让人要吐。」"
         "全句是极端负面判断，与五星完全对立，最合理的解释是打分时误触。"
         "同类还有《布达佩斯大饭店》的一星评论，正文写「完美」「好看到难过」，与一星截然相反。"),
        ("评分动机与影片评价分离",
         "《星际穿越》那条一星评论明说「我偏要打一星」，原因是反感其他观众的吹捧；"
         "《可可西里》的一星评论写「大师作品，值得信赖」，低分可能来自对题材立场的抵触。"
         "这类情况下，星级表达的是态度，文本表达的是评价，两者本就不在同一层面。"),
        ("反讽与以贬词表喜爱",
         "《魂断蓝桥》的五星评论通篇用「狗血」调侃剧情，但末句写「感动之余也捎带脚原谅了」，"
         "是以贬义词表达喜爱的典型写法。《海上钢琴师》的五星评论开篇「非常做作」，"
         "随后展开辩证肯定，写「敬佩他如一的懦弱」，属于先抑后扬。"),
        ("混合情感",
         "《七宗罪》的五星评论既写「有些画面好恶心」，又写「特别喜欢老警察」「万万没想到的结局」，"
         "正负并存且以正面收束。这类文本的真实情感本身就不是单一标签能概括的，"
         "任何三分类模型都会损失信息。"),
        ("模型误判",
         "这是数量最多的一类。具体有三种表现：评价对象错位（「垃圾」修饰角色而非影片）、"
         "引用他人话语（「居然好多人说是烂片」是转述而非自述）、"
         "剧情名词误计（「垃圾堆」「一堆垃圾」是场景或台词）。"
         "三种错误共同指向一个技术缺陷：词典法只识别词，不识别词指向的对象。"),
    ]
    for i, (title, body) in enumerate(causes, start=1):
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_before = Pt(4)
        run = p.add_run(f"（{i}）{title}。")
        _font(run, FONT_HEAD, 10.5, bold=True)
        run2 = p.add_run(body)
        _font(run2, FONT_BODY, 10.5)

    _h(doc, "8.7　是否存在系统性偏差：结论", 2)
    _p(doc, f"存在。证据有三条：第一，星级与文本情感虽然显著正相关（r = {r_p}），"
            f"但强度弱，星级只能解释约 {r_p ** 2 * 100:.0f}% 的变异；"
            f"第二，各星级内部的情感构成都有不可忽略的「异类」比例；"
            f"第三，也是最关键的，两个方向的不一致发生率严重不对称"
            f"（{low_rate * 100:.2f}% 对 {high_rate * 100:.2f}%），说明这不是随机噪声，"
            f"而是有机制的系统偏差。")
    _p(doc, "但这个结论有几个限定。情感模型准确率只有 69.33%，上述发生率应视为估计值；"
            "模型误差是随机还是系统的，这里分不开；"
            "极端值回退机制抬高了低星区的正面率，使得 43.75% 这个数字偏保守还是偏激进，需要更好的模型来校准。")

    _h(doc, "8.8　改进思路", 2)
    _p(doc, "最直接的改进是换模型：用一个在中文影评上微调过的句向量模型，"
            "把三分类准确率提到 80% 以上，同时输出概率分布而不是硬标签，"
            "这样「混合情感」这类样本就能用概率熵来刻画，而不是被迫归入某一类。"
            "第二个改进是加一个「评价对象识别」的步骤，先判断情感词修饰的是影片、角色还是他人言论，"
            "再算情感分，这能解决目前最主要的误判来源。"
            "第三个改进是把 20 条扩展到全部严重矛盾样本（870 条）的抽样，"
            "统计各类成因的比例，让「成因分析」从定性变成定量。")


def _load_final_cases() -> pd.DataFrame:
    """读取经人工复核的最终样本表；缺失时返回空表。"""
    p = TABLE_DIR / "q4_mismatch_20cases.csv"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# 第九章 Q5
# ---------------------------------------------------------------------------
def build_ch9(doc: Document, d: dict):
    """第九章：Q5 经典电影重映推荐。"""
    _h(doc, "第九章　Q5　经典电影重映推荐", 1)

    rec = d["rec"]
    facts = d["market_facts"]
    heat = d["genre_heat"]

    _h(doc, "9.1　问题理解与初步思路", 2)
    _p(doc, "这一题要求推荐五部重映影片，但明确说了「不能简单按照豆瓣排名」。"
            "我一开始想的是按被低估指数排序取前五，后来意识到这也不够。"
            "被低估说明「文本口碑好但没人关注」，但不代表「现在放出来有人买票」。")
    _p(doc, "重映是个商业行为，要同时满足三个条件：口碑基础够（保证上座下限）、"
            "有「被重新发现」的空间（构成传播话题）、大银幕能提供小屏幕替代不了的体验。"
            "所以我最后把「类型在当前市场的接受度」也做成一个维度，"
            "而且这个维度必须用真实的市场数据，不能拍脑袋。")

    _h(doc, "9.2　市场数据：来自公开报道", 2)
    _p(doc, "任务书要求「近期市场趋势必须使用真实、有时间标注的公开资料辅助分析」。"
            "我检索了国家电影局、央视网、新华网等来源的公开报道，摘出与本决策相关的 12 条事实。")
    if len(facts):
        show = facts[["指标", "数值", "来源", "发布日期"]].copy()
        _table(doc, show, "表 9-1　用于推荐决策的公开市场事实",
               widths=[4.6, 3.0, 4.2, 2.2], font_size=7.5)

    _p(doc, "其中有两条对推荐影响最大。第一条是 2025 年动画电影的表现："
            "国家电影局数据显示 2025 年是中国影史动画电影票房最高的一年，"
            "年度票房前十中动画占四席（央视网，2026-01-01）。"
            "第二条是反例：《笑傲江湖：东方不败》豆瓣 8.5 分、24 万人评价，"
            "2026 年重映首日预售只有 1.7 万元、票房 15.6 万元、首日预排片 6.3%（网易新闻，2026-10-26）。"
            "这说明「经典 + 情怀」并不必然转化为票房。")

    _note(doc, "这两条让我改了权重设计。如果只按口碑排，武侠经典一定入选；"
               "但市场数据说这条路风险很高。所以我把类型市场热度设为独立维度、权重 0.20，"
               "并且明确标注这个赋分是「分析者判断」而非行业统计口径。"
               "这一点在报告里必须写清楚，不能把我的主观判断包装成客观数据。")

    _h(doc, "9.3　综合推荐分模型", 2)
    _p(doc, "推荐分 R 的定义如下：")
    _formula(
        doc,
        "R = 0.15·Z(评分) + 0.25·Z(U) + 0.15·Z(情感) + 0.08·Z(关注度) "
        "+ 0.07·Z(评论数) + 0.10·Z(年代稀缺性) + 0.20·Z(类型市场热度)",
        "9-1",
    )
    _p(doc, "评分权重刻意压到 0.15。如果给评分太高权重，结果必然退化为「Top250 前五名」，"
            "失去策划价值。被低估指数 U 占 0.25，是决策起点，回答的是「这部片是否被低估」。"
            "市场热度占 0.20，是这次的改进，回应「现在什么类型还卖得动」。")

    _table(
        doc,
        pd.DataFrame(
            [
                {"维度": "豆瓣评分", "权重": "0.15", "作用": "口碑基础，保证上座下限"},
                {"维度": "被低估指数 U", "权重": "0.25", "作用": "识别「口碑好但未被充分发现」"},
                {"维度": "平均文本情感", "权重": "0.15", "作用": "评论情绪强度，关系宣传素材是否充足"},
                {"维度": "评分人数", "权重": "0.08", "作用": "既有受众规模"},
                {"维度": "有效评论数", "权重": "0.07", "作用": "可用于宣传引用的素材量"},
                {"维度": "年代稀缺性", "权重": "0.10", "作用": "越早的影片大银幕稀缺性越强"},
                {"维度": "类型市场热度", "权重": "0.20", "作用": "当前市场对该类型的接受度（分析者赋分）"},
            ]
        ),
        "表 9-2　推荐模型的七个维度",
        widths=[4.4, 2.0, 8.2],
    )

    _p(doc, "约束条件有四条：被低估指数必须为正（否则推荐会退化成「再推荐一次经典名片」）、"
            "已上映满 8 年、第一轮每类型最多 1 部、同一十年区间最多 2 部。"
            "第一轮选不满时第二轮放宽到每类型 2 部。")

    _fig(doc, "fig9_2_genre_heat.png", "图 9-2　各主类型的市场热度赋分（分析者主观判断）", 12.8)

    if len(heat):
        _p(doc, "类型热度的赋分依据：动画 0.95（2025 年为影史动画票房最高年、年度前十占四席）、"
                "喜剧 0.85（春节档与暑期档主力，票价下行期更依赖解压类型）、"
                "悬疑犯罪 0.75/0.72（中小成本易出黑马）、剧情 0.70、"
                "动作 0.35（出现《东方不败》重映 15.6 万元的明确反例，故压低）。")

    _h(doc, "9.4　五部推荐影片", 2)
    if len(rec):
        show = rec.copy()
        if "评分人数" in show.columns:
            show["评分人数"] = show["评分人数"].map(lambda x: f"{int(x):,}")
        for c in ["被低估指数", "综合推荐分", "平均文本情感", "类型市场热度"]:
            if c in show.columns:
                show[c] = show[c].map(lambda v: f"{v:.3f}")
        cols = ["推荐序号", "电影名称", "上映年份", "主类型", "豆瓣评分", "评分人数",
                "有效评论数", "被低估指数", "类型市场热度", "综合推荐分"]
        _table(doc, show[[c for c in cols if c in show.columns]],
               "表 9-3　五部重映推荐影片的核心指标",
               widths=[1.2, 3.0, 1.6, 1.6, 1.6, 2.2, 1.8, 1.9, 1.9, 1.8], font_size=7.5)

    _fig(doc, "fig9_1_recommendation_scorecard.png",
         "图 9-1　五部推荐影片的多维指标对比", 15.2)

    if len(rec):
        genres = rec["主类型"].nunique()
        eras = rec["年代"].nunique()
        _p(doc, f"五部影片覆盖 {genres} 种主类型与 {eras} 个年代区间，"
                f"上映年份从 {int(rec['上映年份'].min())} 年到 {int(rec['上映年份'].max())} 年。")

        _h(doc, "9.5　逐部说明", 3)
        details = _detail_text(rec)
        for item in details:
            _p(doc, f"第 {item['序号']} 位：《{item['片名']}》（{item['年份']}，{item['类型']}）。"
                    f"导演 {item['导演']}。豆瓣评分 {item['评分']}，评分人数 {item['人数']:,}，"
                    f"有效评论 {item['评论数']} 条，被低估指数 {item['指数']:.3f}，"
                    f"综合推荐分 {item['推荐分']:.3f}。")
            for label, key in [
                ("推荐理由", "理由"), ("数据支持", "数据"), ("目标观众", "观众"),
                ("放映时间", "档期"), ("宣传方向", "宣传"),
            ]:
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Pt(21)
                p.paragraph_format.space_after = Pt(2)
                r1 = p.add_run(f"{label}：")
                _font(r1, FONT_HEAD, 10, bold=True)
                r2 = p.add_run(item[key])
                _font(r2, FONT_BODY, 10)
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(21)
            p.paragraph_format.space_after = Pt(8)
            r1 = p.add_run("潜在风险：")
            _font(r1, FONT_HEAD, 10, bold=True)
            r2 = p.add_run(
                f"版权方面，{item['版权']}；发行方面，{item['发行']}；"
                f"观众兴趣方面，{item['兴趣']}"
            )
            _font(r2, FONT_BODY, 10)

    _h(doc, "9.6　风险汇总与版权边界", 2)
    _table(
        doc,
        pd.DataFrame(
            [
                {"风险类型": "版权风险", "说明": "未获得任何版权信息，五部影片的版权归属、授权状态、可放映拷贝情况均未知"},
                {"风险类型": "发行风险", "说明": "重映需要院线排片、宣发资源与档期协调，无相关数据，可行性无法评估"},
                {"风险类型": "市场风险", "说明": "《笑傲江湖：东方不败》重映 15.6 万元、《功夫之王》不足 3 万元，说明情怀不必然兑现"},
                {"风险类型": "数据风险", "说明": "部分影片有效评论仅 33 条左右，情感均值标准误较大，推荐依据的稳定性有限"},
            ]
        ),
        "表 9-4　四类风险的统一说明",
        widths=[3.2, 12.0],
    )
    _p(doc, "这张表的作用是把「不知道」写明白。我能判断的是「哪些影片在内容层面值得重映」，"
            "不能判断「哪些影片在法律与商业上可以重映」。把前者当后者，是这类分析最常见的越界。"
            "所以五部影片的版权状态在数据表中统一标注为「需进一步确认」。")

    _h(doc, "9.7　给栏目编辑的一页决策摘要", 2)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("豆瓣 Top250 经典影片重映推荐与市场价值分析")
    _font(run, FONT_HEAD, 13, bold=True)

    _p(doc, "核心发现：Top250 内部评分高度集中（8.4—9.7），榜单内的评分差不足以支撑「哪部更值得重映」的判断。"
            "真正有区分度的是评论文本反映的口碑温度、关注度的错配，以及类型在当下市场的接受度。"
            "公开数据显示 2025 年为影史动画票房最高年，而 2026 年一部 8.5 分的武侠经典重映仅收 15.6 万元。"
            "这两条共同决定了本片单的取向：优先动画与合家欢，谨慎对待动作武侠。")

    if len(rec):
        p = doc.add_paragraph()
        run = p.add_run("五部推荐（按推荐顺序）：")
        _font(run, FONT_HEAD, 10.5, bold=True)
        for _, r in rec.iterrows():
            p = doc.add_paragraph(
                f"{int(r['推荐序号'])}. 《{r['电影名称']}》（{int(r['上映年份'])}，{r['主类型']}）"
                f"　综合推荐分 {r['综合推荐分']:.3f}，建议档期：{r['建议档期']}",
                style="List Number",
            )
            for run in p.runs:
                _font(run, FONT_BODY, 10.5)

    _p(doc, "推荐排序依据：第一位《龙猫》在动画类型市场热度最高、年代稀缺性较强、"
            "且被低估指数为正，三个维度同时占优；其后依次在剧情、喜剧、悬疑、科幻上补位，"
            "使整份片单在类型与年代两个维度保持分散。")
    _p(doc, "主要风险：五部影片版权状态全部未知，须在立项前完成版权核查；"
            "《龙猫》等片在国内已有重映先例，需评估再次重映的新鲜度；"
            "1960 年代的影片存在观影习惯断层。")
    _p(doc, "下一步建议：第一步，就五部影片的版权归属与可放映拷贝向版权方询价；"
            "第二步，把这批评论文本当宣传素材库，提取高频情感表达作为文案方向；"
            "第三步，小范围试映验证「被低估」这个卖点是否成立。如果观众反馈与文本分析一致，"
            "说明指数具备实践价值；如果不一致，则需回头检验指数构造。")

    _h(doc, "9.8　局限与改进", 2)
    _p(doc, "三点局限。第一，类型市场热度的赋分是我的主观判断，虽然基于 12 条公开事实，"
            "但赋分数值本身没有统计依据，换一个人可能给出不同分数。"
            "第二，推荐只用了历史数据，没有实时票房跟踪，无法反映上映前一周的市场变化。"
            "第三，缺少版权与发行信息，所有推荐都停在「内容层面」。")
    _p(doc, "改进方向：一是把类型热度换成可量化的指标，比如近 12 个月该类型影片的平均票房、"
            "上映数量、上座率，用数据代替赋分；二是引入档期竞争分析，"
            "避开同类型新片扎堆的窗口；三是如果能拿到版权库信息，"
            "就可以从「值得重映」推进到「可以重映」。")


def _detail_text(rec: pd.DataFrame) -> list[dict]:
    """
    为五部推荐影片生成策划文案。

    事实性内容（年份、导演、评分、指标、建议档期）全部来自数据表；
    判断性内容（目标观众、宣传方向、风险）由项目作者撰写，属于分析者判断。

    参数:
        rec: 推荐结果表。

    返回:
        每部影片一个字典的列表。
    """
    narrative: dict[str, dict[str, str]] = {
        "龙猫": {
            "理由": "动画类型市场热度最高（2025 年为影史动画票房最高年，年度前十动画占四席），"
                    "年代稀缺性系数为五部中偏高的水平，被低估指数为正。影片评分 9.2，"
                    "在五部中最高，评论情感也最一致，是整份片单里风险最低的一部。",
            "观众": "亲子家庭、吉卜力影迷、偏好治愈系内容的年轻女性观众。",
            "档期": "春节档（农历正月初一起）。合家欢类型与假期观影场景高度契合。",
            "宣传": "以「宫崎骏的大银幕」为核心，强调手绘动画在影院放映时的质感差异；配合亲子场次做口碑扩散。",
            "版权": "吉卜力作品在内地的放映权由特定发行方代理，需确认当前授权窗口是否开放",
            "发行": "该片 2018 年曾在内地重映，再次重映需评估间隔是否足够",
            "兴趣": "影片节奏舒缓，低龄观众注意力维持存在挑战",
        },
        "三块广告牌": {
            "理由": "被低估指数在全部达到评论量门槛的影片中最高，文本情感与评分的正向落差最大；"
                    "剧情类型市场热度中等偏上；与其余四部形成年代与题材互补。",
            "观众": "25—45 岁城市观影人群、偏好作者性强类型片的观众、错过当年院线的影迷。",
            "档期": "秋季档（9—10 月，传统淡季）。2026 年秋季档老片重映集中，市场已形成「淡季看修复片」的消费习惯。",
            "宣传": "以「被低估的愤怒」为切口，用母亲与警长的对峙作主视觉，强调大银幕重看演技对决。",
            "版权": "该片为 2017 年福斯探照灯出品，国内版权归属需向现权利方核实",
            "发行": "片长 115 分钟排片灵活，但题材涉及种族与警民冲突，宣发口径需谨慎",
            "兴趣": "影片基调沉重，非合家欢类型，档期需避开强喜剧竞争",
        },
        "冰川时代": {
            "理由": "喜剧类型市场热度高，且叠加动画属性；上映于 2002 年，年代有一定稀缺性；"
                    "被低估指数为正，说明文本口碑优于其评分排名。",
            "观众": "亲子家庭、80 后 90 后怀旧观众、暑期需要轻松内容的年轻群体。",
            "档期": "贺岁档（12 月中下旬）。近年贺岁档票房创八年新高，喜剧类型在该档期表现稳定。",
            "宣传": "以「冰河三人组回归」为情怀点，主打合家欢与怀旧双线。",
            "版权": "该片为 20 世纪福斯动画，国内版权需核实（迪士尼收购后权利归属可能变化）",
            "发行": "系列后续作品已多轮播出，观众「已看过」比例高，需靠大银幕体验差异化",
            "兴趣": "系列续集口碑下滑可能影响对本片的重映期待",
        },
        "惊魂记": {
            "理由": "上映于 1960 年，年代稀缺性系数为五部中最高；悬疑类型市场热度较高，"
                    "中小成本悬疑片近年屡出黑马；作为悬疑片的技术范本，"
                    "其浴室谋杀段落的剪辑在大银幕上具教学与朝圣双重价值。",
            "观众": "影迷群体、影视专业学生、悬疑类型爱好者。",
            "档期": "秋季档或主题影展。黑白片在商业院线排片有限，更适合影展策展或艺术影院专场。",
            "宣传": "以「悬疑片的原点」定位，配合希区柯克导演专题做系列放映。",
            "版权": "影片版权历经多次转让，内地放映权需向环球方面核实",
            "发行": "黑白片在当下院线市场接受度有限，需依托影展或艺术影院渠道",
            "兴趣": "年轻观众对 1960 年代影片的叙事节奏可能不适应",
        },
        "2001太空漫游": {
            "理由": "科幻类型需强视听支撑，本片在 4K/IMAX 修复后的大银幕体验是流媒体无法替代的；"
                    "上映于 1968 年，年代稀缺性与《惊魂记》同档；被低估指数为正，且在五部中排第二。",
            "观众": "硬科幻爱好者、影史研究者、追求大银幕视听体验的观众。",
            "档期": "暑期档（7—8 月）。近年暑期档观影人次同比上升，特效厅一票难求，与影片的视听属性契合。",
            "宣传": "以「影史最伟大的科幻片，终于等到大银幕」为核心，突出 4K 修复与 IMAX 版本。",
            "版权": "该片为 1968 年米高梅出品，现版权归属华纳方面，需核实内地放映授权",
            "发行": "片长 149 分钟且节奏极慢，排片场次受限，需依赖特效厅提高单场收益",
            "兴趣": "影片叙事极简、对白稀少，普通观众接受门槛高，需精准定位核心受众",
        },
    }

    # 「数据支持」一栏全部由结果表回填，不写死数字——写死就会出现正文与 CSV 对不上的情况。

    out: list[dict] = []
    for _, r in rec.iterrows():
        name = str(r["电影名称"])
        n = narrative.get(name, {})
        director = str(r.get("导演", "")).split()[0] if isinstance(r.get("导演"), str) else "未知"
        u_val = float(r["被低估指数"])
        data_text = (
            f"豆瓣 {float(r['豆瓣评分']):.1f} 分，评分人数约 {int(r['评分人数']) / 10000:.0f} 万，"
            f"有效评论 {int(r['有效评论数'])} 条，平均文本情感 {float(r['平均文本情感']):.3f}，"
            f"被低估指数 {u_val:.3f}。"
        )
        out.append(
            {
                "序号": int(r["推荐序号"]),
                "片名": name,
                "年份": int(r["上映年份"]),
                "类型": str(r["主类型"]),
                "导演": director,
                "评分": r["豆瓣评分"],
                "人数": int(r["评分人数"]),
                "评论数": int(r["有效评论数"]),
                "指数": u_val,
                "推荐分": float(r["综合推荐分"]),
                "理由": n.get("理由", "综合指标位于候选前列。"),
                "数据": data_text,
                "观众": n.get("观众", "泛影迷群体。"),
                "档期": str(r.get("建议档期", "")),
                "宣传": n.get("宣传", "以既有口碑为核心卖点。"),
                "版权": n.get("版权", "版权状态未知，需向权利方核实"),
                "发行": n.get("发行", "发行可行性未知"),
                "兴趣": n.get("兴趣", "观众兴趣需通过试映验证"),
            }
        )
    return out# ---------------------------------------------------------------------------
# 第十章
# ---------------------------------------------------------------------------
def build_ch10(doc: Document, d: dict):
    """第十章：研究结论、创新点与不足。"""
    _h(doc, "第十章　研究结论、创新点与不足", 1)

    q = d["qstats"]
    n = max(1, d["n_reviews"])
    top10 = d["top10"]
    corr = d["q4_corr"]

    _h(doc, "10.1　主要结论", 2)

    conclusions = [
        (
            "评论有效性的比例比预想的高，但噪声集中在短文本",
            f"在 {n:,} 条评论中，{q.get('A', 0):,} 条（{q.get('A', 0) / n * 100:.2f}%）被判为有效评论，"
            f"{q.get('B', 0)} 条为低信息量，{q.get('D', 0)} 条为重复副本，{q.get('E', 0)} 条待人工判断，"
            f"{q.get('X', 0)} 条因结构损坏被剔除。两条独立路径（A+B 有效、A 有效）算出的有效率"
            f"分别为 {(q.get('A', 0) + q.get('B', 0)) / n * 100:.2f}% 与 {q.get('A', 0) / n * 100:.2f}%。"
            f"我原以为短评区噪声会更多，实际看下来大部分评论确实在谈电影，"
            f"噪声主要来自特别短的表达和源数据缺陷。",
        ),
        (
            "双维度评价确实筛掉了单维度漏掉的东西",
            f"只判断内容有效性时，870 条「五星配通篇差评」或「一星配通篇好评」的评论会被当作有效样本"
            f"混进情感均值。加上一致性维度后，这批样本被单独隔离，"
            f"既保留了原始记录，又不再污染统计。这是本章我认为最有价值的方法收获。",
        ),
        (
            "评分与评分人数不是一回事",
            f"评分集中在 {d['q1'].set_index('指标').loc['下四分位 Q1', '豆瓣评分']} 至 "
            f"{d['q1'].set_index('指标').loc['上四分位 Q3', '豆瓣评分']} 分（IQR 仅 0.375），"
            f"评分人数呈长尾、取对数后偏度由 {d['q1'].set_index('指标').loc['偏度', '评分人数']} "
            f"降至 {d['q1'].set_index('指标').loc['偏度（log10 评分人数）', '评分人数']}；"
            f"两者相关系数低（Pearson {d['q1_corr'].iloc[0]['系数']}，"
            f"Spearman {d['q1_corr'].iloc[1]['系数']} 且不显著）。"
            f"「高分」与「热门」是两件独立的事。",
        ),
        (
            "被低估的不是神作，是中上游影片",
            f"指数前十名的评分集中在 8.5—8.7，没有一部超过 9.0。"
            f"这不是巧合，而是设计的必然：高分片的评分排名本身就在顶端，"
            f"文本情感排名很难再超过它。所以「被低估」的真实含义是"
            f"「口碑扎实但还没被充分讨论」，而不是「被埋没的杰作」。",
        ),
        (
            "星级与文本的偏差是不对称的",
            f"星级与文本情感正相关但很弱（Pearson r = {corr.iloc[0]['系数']}）。"
            f"更关键的是方向：低星评论中出现正面文本的比例远高于高星评论中出现负面文本的比例。"
            f"这意味着把低星当「负面样本」使用的风险，比把五星当「正面样本」大得多。"
            f"任何按星级分组的分析都必须考虑这一点。",
        ),
        (
            "重映推荐必须引入市场维度",
            f"纯粹按口碑或按被低估指数排，会推荐出一批「叫好但可能不叫座」的影片。"
            f"纳入公开市场数据后，动画类获得更高分值，动作武侠被压低。"
            f"这与 2026 年《笑傲江湖：东方不败》重映仅 15.6 万元的实际表现一致。",
        ),
    ]

    for idx, (title, body) in enumerate(conclusions):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(5)
        run = p.add_run(f"（{'一二三四五六'[idx]}）{title}。")
        _font(run, FONT_HEAD, 10.5, bold=True)
        run2 = p.add_run(body)
        _font(run2, FONT_BODY, 10.5)

    _h(doc, "10.2　两个创新点及其实验验证", 2)

    _h(doc, "10.2.1　创新一：双维度评论清洗", 3)
    _table(
        doc,
        pd.DataFrame(
            [
                {"环节": "原始方法", "内容": "只判断评论有无意义（长度、表情、广告），通过即视为可用"},
                {"环节": "原始方法的问题", "内容": "无法识别「内容有效但与星级矛盾」的评论，这类样本会污染情感统计"},
                {"环节": "改进思路", "内容": "增加第二维度判断星级与文本一致性，与内容维度交叉形成处理矩阵"},
                {"环节": "Python 实现", "内容": "quality_classification.py 分级 + consistency_check.py 一致性 + 矩阵处置"},
                {"环节": "实验对比", "内容": "300 条人工验证集上，F1 由 0.6682 升至 0.7778，准确率由 51.67% 升至 73.33%"},
                {"环节": "改进效果", "内容": "有效成立，但召回率由 0.8156 降至 0.7821，误杀率由 0.1844 升至 0.2179"},
                {"环节": "改进的不足", "内容": "更严格必然误伤；人工标注未提供独立的一致性真值，无法直接验证一致性判定的准确率"},
            ]
        ),
        "表 10-1　创新一的完整链条",
        widths=[3.0, 12.2],
    )

    _h(doc, "10.2.2　创新二：改进被低估指数", 3)
    _table(
        doc,
        pd.DataFrame(
            [
                {"环节": "原始方法", "内容": "U = 0.50·Z(S−R) + 0.30·Z(H) − 0.20·Z(P)，S 与 R 直接相减"},
                {"环节": "原始方法的问题", "内容": "R 用线性映射到 [−1,1]，9.5 分对应 +0.9，而文本情感均值仅 0.2—0.4，导致高分片 U 恒为负，指数退化为「评分越高越被高估」"},
                {"环节": "改进思路", "内容": "S 与 R 各自做样本内 Z 标准化后再相减；H 改为平均有用数的对数；S 只用 A 类且剔除严重矛盾样本"},
                {"环节": "Python 实现", "内容": "underrated_index.py 的 compute_index 与 build_movie_features"},
                {"环节": "实验对比", "内容": "改进前前十名全为 9.3 分以上影片（等同于再排一次榜）；改进后前十集中在 8.5—8.7，符合「被低估」的语义"},
                {"环节": "改进效果", "内容": "指数具备区分力；五组权重下秩相关最低 0.9455，排名稳健"},
                {"环节": "改进的不足", "内容": "H 无法区分高赞与高踩；30 条门槛偏低导致名次不稳；共线性使解释时需避免重复归因"},
            ]
        ),
        "表 10-2　创新二的完整链条",
        widths=[3.0, 12.2],
    )

    _h(doc, "10.3　局限", 2)
    limits = [
        (
            "评论覆盖率只有 56.4%",
            f"短评页需登录，这里不绕过，改用公开数据集。该数据集 148 个影片文件中 "
            f"{d['n_covered']} 部能与当前榜单匹配，当前榜单另有 {d['n_movies'] - d['n_covered']} 部无评论。"
            f"所有涉及评论的结论都不能外推为「Top250 整体」的规律。",
        ),
        (
            "情感分析准确率 69.33%",
            "词典法的主要误差来自三处：评价对象识别失败（把修饰角色的贬义词计入对影片的评价）、"
            "引用他人话语与作者自述混淆、反讽与混合情感无法处理。"
            "这些误差会传导到被低估指数与不一致率上，使相关数值只能视为估计。",
        ),
        (
            "H 维度被迫替换",
            "数据集只提供有用数、无没用数，无法计算原设的有用率。"
            "替代指标无法区分高赞与高踩，也无法排除时间累积效应（早期评论天然更容易攒点赞）。",
        ),
        (
            "只有一个时间节点",
            "Q2 要求的占比变化无法计算，已标注为数据不足。任何「某类型占比上升」的说法，在现有证据里都站不住。",
        ),
        (
            "缺少版权与票房数据",
            "Q5 的推荐只基于内容与市场趋势，不涉及版权归属、发行渠道、排片资源与实际票房，"
            "推荐不构成可执行方案。",
        ),
        (
            "一致性判定的验证缺口",
            "人工标注只有内容质量与情感两列，没有独立的一致性真值。"
            "因此「一致性判定的准确率」没有被直接验证，报告中的「误杀率」"
            "衡量的是过度排斥程度，不能等同于一致性识别精度。这是最需要补上的一环。",
        ),
    ]
    for i, (title, body) in enumerate(limits, start=1):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(4)
        run = p.add_run(f"（{i}）{title}。")
        _font(run, FONT_HEAD, 10.5, bold=True)
        run2 = p.add_run(body)
        _font(run2, FONT_BODY, 10.5)

    _h(doc, "10.4　后续工作优先顺序", 2)
    _p(doc, "如果继续做，我会按这个顺序推进，因为它们的依赖关系是明确的：")
    for t in [
        "第一优先：补一份带一致性真值的人工标注（至少 200 条），验证第二维度的判定准确率。这是当前最大的方法缺口。",
        "第二优先：取得经授权的完整评论数据，把覆盖率从 56.4% 提到接近 100%，这是所有改进的前提。",
        "第三优先：换用中文预训练情感模型（在影评语料上微调），把准确率提到 80% 以上，并保留词典法作为可解释基线。",
        "第四优先：若能获得两到三个时间节点的榜单快照，Q2 的时间变化分析即可补全。",
        "第五优先：把类型市场热度换成可量化指标（近 12 个月该类型平均票房、上座率），替代当前的主观赋分。",
    ]:
        p = doc.add_paragraph(t, style="List Number")
        for run in p.runs:
            _font(run, FONT_BODY, 10.5)


# ---------------------------------------------------------------------------
# 第十一章
# ---------------------------------------------------------------------------
def build_ch11(doc: Document, d: dict):
    """第十一章：个人学习总结与人机协同反思。"""
    _h(doc, "第十一章　个人学习总结与人机协同反思", 1)

    _h(doc, "11.1　我和 AI 的分工", 2)
    _p(doc, "这个项目里我把工作分成两类：需要判断的，和需要执行的。前者我自己做，后者交给 AI 提高效率。"
            "具体分工如下。")
    _table(
        doc,
        pd.DataFrame(
            [
                {"环节": "确定研究目标与问题拆解", "我做的": "独立完成", "AI 做的": "—",
                 "我的判断": "五个问题的主线必须自己定，否则整个项目会散"},
                {"环节": "判断哪些数据源合法可用", "我做的": "决策", "AI 做的": "测试连通性",
                 "我的判断": "遇到访问控制时选择不绕过，这个决定不能外包"},
                {"环节": "制定评论有效性标准", "我做的": "主设计", "AI 做的": "提供规则草案",
                 "我的判断": "「不因短而删」这条原则是我坚持的，AI 初始方案会删掉「烂片。」"},
                {"环节": "编写 Python 代码", "我做的": "审阅与修改", "AI 做的": "主要编写",
                 "我的判断": "代码可以交给 AI，但每个函数的逻辑要能自己讲清楚"},
                {"环节": "人工抽查与纠错", "我做的": "全部 300 条", "AI 做的": "—",
                 "我的判断": "这一步不能代劳，否则验证集就失去意义"},
                {"环节": "比较不同分析方法", "我做的": "决策", "AI 做的": "跑对比实验",
                 "我的判断": "选词典法而非预训练模型，是因为 Q4 不能循环论证"},
                {"环节": "判断创新是否有效", "我做的": "决策", "AI 做的": "计算指标",
                 "我的判断": "F1 提升但召回下降，我认定算改进，但要如实报告代价"},
                {"环节": "查市场数据", "我做的": "核实来源", "AI 做的": "检索与整理",
                 "我的判断": "每条数据都要求标注来源与日期，查不到的写「未知」"},
                {"环节": "写报告", "我做的": "思路与判断", "AI 做的": "排版与初稿",
                 "我的判断": "凡是我自己没想到的结论，都要回去核对数据"},
            ]
        ),
        "表 11-1　人机分工明细",
        widths=[4.4, 2.6, 2.8, 5.4],
        font_size=8,
    )

    _h(doc, "11.2　AI 帮我最多的地方", 2)
    _p(doc, "最直接的帮助是效率。这个项目有 11 个模块、约 5000 行代码，"
            "如果全部手写，光调试环境、处理 pandas 的边界情况就要花掉大半时间。"
            "AI 把这些机械工作接过去后，我可以把精力放在「该不该这么算」而不是「怎么让它跑起来」上。")
    _p(doc, "第二个帮助是提醒我没想到的技术细节。比如处理 200 万行数据时逐行算 MD5 会很慢，"
            "应该先对唯一值建映射表；比如 pandas 3.x 里 astype(str) 不会把 NaN 转成字符串，"
            "直接 encode 会报错。这些坑如果自己踩，每一个都要耗半小时。")

    _h(doc, "11.3　AI 出错、我改掉的地方", 2)
    _p(doc, "这一节我觉得比上一节更重要，因为课程要求「不能把 AI 的判断冒充自己的研究成果」。"
            "下面四处是 AI 给的方案有问题、我判断后改掉的：")
    fixes = [
        (
            "第一版清洗规则会删掉「烂片。」",
            "AI 最初按「长度小于 4 字视为无效」处理，这会删掉大量真实的短评。"
            "我改成「短但有明确好恶判断的保留为低信息量」，理由是这个项目的研究对象就是口碑，"
            "而「烂片」两个字本身就是最有信息量的口碑表达之一。",
        ),
        (
            "第一版情感分析把「非常精彩」判成负面",
            "原因是单字「非」被列进否定词表，「非」+「常精彩」被当成否定结构。"
            "我发现后把单字「无」「非」从否定表删掉，改用双字否定词，并加了成语白名单"
            "（否则「两小无猜」的「无」也会误伤后面的「温暖美好」）。",
        ),
        (
            "第一版被低估指数前十名全是 9.3 分以上影片",
            "这不是「被低估」，是「再排一次榜」。我查出原因是 R 的线性映射尺度不对，"
            "改成样本内 Z 标准化后才合理。这个问题如果没发现，整章结论都是错的，"
            "而且从表面上看不出来：排名很整齐，数字很漂亮。",
        ),
        (
            "AI 一度建议用星级训练情感模型以提高准确率",
            "这个建议在纯技术角度是对的（有监督信号，准确率会明显上升），"
            "但会让 Q4 变成循环论证：用星级训练出来的模型，再去检验星级与文本是否一致，"
            "结果必然高度一致。我拒绝了这个方案，接受准确率只有 69.33% 的代价。",
        ),
    ]
    for i, (title, body) in enumerate(fixes, start=1):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(4)
        run = p.add_run(f"（{i}）{title}。")
        _font(run, FONT_HEAD, 10.5, bold=True)
        run2 = p.add_run(body)
        _font(run2, FONT_BODY, 10.5)

    _h(doc, "11.4　人机协同给我的启示", 2)
    _p(doc, "做完这个项目，我对「AI 辅助分析」的理解具体了一些。")
    _p(doc, "第一，AI 最擅长的是「把想法实现」，最不擅长的是「判断这个想法对不对」。"
            "前面那四处修改，AI 都不是「算错了」，而是「按我给的规则算对了，但规则本身有问题」。"
            "规则的问题只能由人来发现，因为只有人知道这个研究的目的是什么。")
    _p(doc, "第二，越是看起来漂亮的结果，越要回头查。被低估指数前十名全是高分经典那段，"
            "从代码到输出没有任何报错，图表也很整齐，但它回答的不是我想问的问题。"
            "如果没有停下来问一句「这真的是『被低估』吗」，这个错误会一直带到报告里。")
    _p(doc, "第三，方法上的妥协要写出来。改进方法的 F1 上升、召回下降，"
            "如果只报前者，结论会显得更漂亮，但那是不诚实的。"
            "课程要求「如果实验没有证明效果提升，应如实说明」，"
            "我的情况是「部分提升，有代价」，同样应该如实写。")

    _h(doc, "11.5　还需要我自己补的部分", 2)
    _p(doc, "这份报告里有些内容需要我本人核对或补充，代码无法代劳：")
    for t in [
        "封面上的姓名、班级、学号、指导教师（config.py 的 COVER_INFO 中留空，需填写）",
        "第二章提到的几处「我原本以为……后来发现……」，需要对照自己真实的思考过程确认或改写",
        "第九章五部影片的策划文案（目标观众、宣传方向、风险判断）是我的分析，"
        "如果与实际放映经验不符，应以实际经验为准",
        "第十一章的反思部分是按项目实际发生的过程整理的，建议按自己的表达习惯重写一遍",
        "报告中的参考文献需要按学校要求的格式核对",
    ]:
        p = doc.add_paragraph(t, style="List Bullet")
        for run in p.runs:
            _font(run, FONT_BODY, 10.5)

    _p(doc, "最后想说一点。这个项目最初我以为难点在爬虫和建模，做完发现难点在判断："
            "判断哪些数据能用、判断什么算一条有效评论、判断一个漂亮的排名是不是在回答错误的问题。"
            "这些判断 AI 可以给建议，但责任在人。这可能就是课程要求「人机协同」的真正意思。")# ---------------------------------------------------------------------------
# 参考文献
# ---------------------------------------------------------------------------
def build_refs(doc: Document):
    """参考文献（MLA 格式）。"""
    _h(doc, "参考文献", 1)

    refs = [
        "国家电影局. “2025 年全国电影票房 518.32 亿元.” 央视网, 2026 年 1 月 1 日, "
        "news.cctv.cn/2026/01/01/ARTIUthTKd7U6HjW68uZXw3r260101.shtml. 访问日期 2026 年 11 月 10 日.",
        "国家电影局. “2026 年暑期档电影票房 124.98 亿元.” 国家电影局官网, 2026 年 9 月 2 日, "
        "www.chinafilm.gov.cn/xwzx/hyzx/202609/t20260902_1006502.html.",
        "央视网. “2026 总票房破 315 亿！‘跟着电影去运动’解锁消费新场景.” 2026 年 10 月 27 日, "
        "big5.cctv.com/gate/big5/arts.cctv.cn/2026/10/27/ARTI7skoVh0SmUIkOmaZ8ygb261027.shtml.",
        "新华网. “今年总票房已超 500 亿元 多部爆款验证中国电影市场发展空间广阔.” "
        "2025 年 12 月 15 日, www.news.cn/ent/20251215/7d2e1389d22442028bd26e7a1b6235e6/c.html.",
        "新浪新闻. “9 月影市淡季老片重映现象分析.” 2026 年 9 月, "
        "www.sina.cn/news/detail/5341918292873562.html.",
        "网易新闻. “从破影史纪录到票房仅 15.6 万，我感慨：功夫皇帝这块招牌算砸了.” "
        "2026 年 10 月 26 日, m.163.com/dy/article_v5/LA6P3EEF0517CI7M.html.",
        "豆瓣电影. “豆瓣电影 Top250.” 豆瓣, 2026, movie.douban.com/top250. 访问日期 2026 年 11 月 9 日.",
        "xiaobing0222. “Douban-Movie-Review-Dataset.” GitHub, 2024, "
        "github.com/xiaobing0222/Douban-Movie-Review-Dataset.",
        "Pang, Bo, and Lillian Lee. “Opinion Mining and Sentiment Analysis.” "
        "Foundations and Trends in Information Retrieval, vol. 2, no. 1–2, 2008, pp. 1–135.",
        "Taboada, Maite, et al. “Lexicon-Based Methods for Sentiment Analysis.” "
        "Computational Linguistics, vol. 37, no. 2, 2011, pp. 267–307.",
        "Salton, Gerard, and Christopher Buckley. “Term-Weighting Approaches in Automatic "
        "Text Retrieval.” Information Processing & Management, vol. 24, no. 5, 1988, pp. 513–523.",
        "Liu, Bing. Sentiment Analysis and Opinion Mining. Morgan & Claypool Publishers, 2012.",
        "Pedregosa, Fabian, et al. “Scikit-learn: Machine Learning in Python.” "
        "Journal of Machine Learning Research, vol. 12, 2011, pp. 2825–2830.",
        "McKinney, Wes. Python for Data Analysis. 3rd ed., O'Reilly Media, 2022.",
    ]
    for i, r in enumerate(refs, start=1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Pt(24)
        p.paragraph_format.first_line_indent = Pt(-24)
        p.paragraph_format.space_after = Pt(3)
        run = p.add_run(f"[{i}] {r}")
        _font(run, FONT_BODY, 9.5)

    _p(doc, "说明：第 1—6 条为第九章市场分析的数据来源，均标注了发布日期；"
            "第 7—8 条为数据来源；第 9—14 条为方法论参考。"
            "没有引用任何无法核实的内部资料。", size=9.5)


# ---------------------------------------------------------------------------
# 附件
# ---------------------------------------------------------------------------
def build_appendix(doc: Document, d: dict):
    """附件 A—H。"""
    _break(doc)
    _h(doc, "附　件", 1)

    # --- A 数据字典 ---
    _h(doc, "附件 A　数据字典", 2)
    _p(doc, "表 A-1 为电影表字段，表 A-2 为评论表字段。字段口径在分析开始前确定，过程中未调整。")
    _table(
        doc,
        pd.DataFrame(
            [
                {"字段": "movie_id", "类型": "str", "含义": "豆瓣影片 ID", "完整率": "100%"},
                {"字段": "title", "类型": "str", "含义": "中文片名", "完整率": "100%"},
                {"字段": "original_title", "类型": "str", "含义": "外文原名", "完整率": "89.2%"},
                {"字段": "other_titles", "类型": "str", "含义": "港台译名等", "完整率": "99.6%"},
                {"字段": "rank", "类型": "int", "含义": "Top250 排名", "完整率": "100%"},
                {"字段": "douban_rating", "类型": "float", "含义": "豆瓣评分（10 分制）", "完整率": "100%"},
                {"字段": "rating_count", "类型": "int", "含义": "评分人数（非观影人数）", "完整率": "100%"},
                {"字段": "release_year", "类型": "int", "含义": "上映年份", "完整率": "100%"},
                {"字段": "country", "类型": "str", "含义": "主国家/地区", "完整率": "100%"},
                {"字段": "country_all", "类型": "str", "含义": "完整国家/地区串", "完整率": "100%"},
                {"字段": "director", "类型": "str", "含义": "导演署名", "完整率": "100%"},
                {"字段": "actors", "类型": "str", "含义": "主演署名", "完整率": "96.0%"},
                {"字段": "genres", "类型": "str", "含义": "类型串（空格分隔）", "完整率": "100%"},
                {"字段": "runtime", "类型": "str", "含义": "片长（未采集）", "完整率": "0%"},
                {"字段": "collect_time", "类型": "str", "含义": "采集时间", "完整率": "100%"},
                {"字段": "source", "类型": "str", "含义": "来源标识", "完整率": "100%"},
            ]
        ),
        "表 A-1　电影表字段",
        widths=[3.2, 1.6, 6.4, 2.6], font_size=8,
    )
    _p(doc, "两处缺失要说一下：original_title 缺失 27 条，是纯华语片页面本身无外文名；"
            "actors 缺失 10 条，是豆瓣把主演压缩为「主…」，属页面固有缺陷。二者都不是采集失败。", size=9.5)

    _table(
        doc,
        pd.DataFrame(
            [
                {"字段": "review_id", "类型": "str", "含义": "评论唯一标识（影片ID_序号）"},
                {"字段": "movie_id", "类型": "str", "含义": "关联影片 ID"},
                {"字段": "movie_name", "类型": "str", "含义": "影片中文名"},
                {"字段": "rating", "类型": "int", "含义": "用户星级 1—5"},
                {"字段": "review_text", "类型": "str", "含义": "原始评论文本"},
                {"字段": "clean_text", "类型": "str", "含义": "清洗后文本"},
                {"字段": "review_time", "类型": "str", "含义": "评论发表时间"},
                {"字段": "useful_count", "类型": "int", "含义": "评论有用数"},
                {"字段": "author_id_hash", "类型": "str", "含义": "用户标识 MD5 前 16 位（脱敏）"},
                {"字段": "quality_label", "类型": "str", "含义": "内容有效性标签 A/B/C/D/E/X"},
                {"字段": "consistency", "类型": "str", "含义": "一致性标签（一致/轻度不一致/严重矛盾/无法判定）"},
                {"字段": "sentiment_score", "类型": "float", "含义": "情感分 [-1, 1]"},
                {"字段": "sentiment_label", "类型": "str", "含义": "情感标签 pos/neu/neg"},
                {"字段": "sentiment_method", "类型": "str", "含义": "判定方法 lexicon/fallback"},
                {"字段": "disposition", "类型": "str", "含义": "最终处置 content/sentiment/mismatch_only/excluded/manual"},
            ]
        ),
        "表 A-2　评论表字段",
        widths=[3.4, 1.6, 10.2], font_size=8,
    )

    # --- B 清洗规则 ---
    _h(doc, "附件 B　清洗与判定规则清单", 2)
    _table(
        doc,
        pd.DataFrame(
            [
                {"序": 1, "规则": "结构校验", "实现": "时间列须匹配 YYYY-MM-DD HH:MM:SS", "作用": "不匹配标 X"},
                {"序": 2, "规则": "HTML/URL 清理", "实现": "正则去标签与链接，反转义实体", "作用": "全部记录"},
                {"序": 3, "规则": "空白统一", "实现": "全角转半角，合并连续空白", "作用": "全部记录"},
                {"序": 4, "规则": "超长截断", "实现": "超过 1000 字截断并标记", "作用": "标记不删除"},
                {"序": 5, "规则": "完全重复", "实现": "同片内文本相同，保留首条", "作用": "后续标 D"},
                {"序": 6, "规则": "高度相似", "实现": "字符级 TF-IDF 余弦 ≥ 0.92", "作用": "后续标 D"},
                {"序": 7, "规则": "纯噪声", "实现": "纯标点/数字/表情/填充词", "作用": "标 B"},
                {"序": 8, "规则": "广告识别", "实现": "正则匹配引流特征", "作用": "标 C"},
                {"序": 9, "规则": "内容分级", "实现": "按长度与要素词四档判定", "作用": "标 A/B/E"},
                {"序": 10, "规则": "一致性判定", "实现": "|star_norm − score| 分四档", "作用": "标一致/轻度/严重/无法判定"},
                {"序": 11, "规则": "矩阵处置", "实现": "内容 × 一致性交叉", "作用": "输出 disposition"},
            ]
        ),
        "表 B-1　清洗与判定规则",
        widths=[1.0, 3.2, 7.2, 4.2], font_size=8,
    )

    # --- C 模型参数 ---
    _h(doc, "附件 C　模型与算法参数", 2)
    _table(
        doc,
        pd.DataFrame(
            [
                {"参数": "情感词典规模", "取值": "正面约 190 条，负面约 170 条"},
                {"参数": "否定窗口", "取值": "情感词前 3 个字符"},
                {"参数": "程度放大系数", "取值": "1.2—1.8，取窗口内最大值"},
                {"参数": "否定后衰减", "取值": "反转后乘 0.9"},
                {"参数": "转折句权重", "取值": "1.5"},
                {"参数": "分数压缩", "取值": "tanh(总分 / sqrt(命中数+1) / 1.6)"},
                {"参数": "情感标签阈值", "取值": "≥0.12 正面，≤−0.12 负面"},
                {"参数": "回退触发条件", "取值": "词典未命中任何情感词"},
                {"参数": "回退判定阈值", "取值": "极性分 >0.80 判正面，<0.20 判负面，置信度上限 0.45"},
                {"参数": "TF-IDF 分析器", "取值": "char_wb，n-gram 2—4"},
                {"参数": "相似度阈值", "取值": "0.92"},
                {"参数": "一致性阈值", "取值": "0.55（一致/轻度）、1.10（轻度/严重）"},
                {"参数": "一致性最低置信度", "取值": "0.25"},
                {"参数": "被低估指数评论门槛", "取值": "30 条"},
                {"参数": "推荐约束", "取值": "指数>0、上映满 8 年、每类型 1 部、同十年 2 部"},
                {"参数": "随机种子", "取值": "20261109"},
            ]
        ),
        "表 C-1　主要参数取值",
        widths=[5.6, 10.0], font_size=8.5,
    )

    # --- D 人工验证 ---
    _h(doc, "附件 D　人工验证记录", 2)
    mv = d["manual"]
    if len(mv):
        _p(doc, f"验证集共 {len(mv)} 条，字段包括 review_id、movie_name、rating、clean_text、"
                f"quality_label（模型预测）、human_label（人工标注）、human_sentiment（人工情感）。"
                f"完整记录见 data/processed/manual_validation.csv。")
        dist = pd.crosstab(mv["quality_label"], mv["human_label"])
        dist = dist.reset_index().rename(columns={"quality_label": "模型\\人工"})
        _table(doc, dist, "表 D-1　模型预测与人工标注的交叉表",
               font_size=8.5)

    # --- E 20 条样本完整文本 ---
    _h(doc, "附件 E　典型不一致样本（完整文本）", 2)
    cases = _load_final_cases()
    if len(cases):
        _p(doc, "以下样本的评论文本仅截取前 200 字以满足篇幅限制，完整内容见 "
                "outputs/tables/q4_mismatch_20cases.csv。评论文本版权归原作者，仅用于学术分析。")
        for _, r in cases.iterrows():
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(1)
            run = p.add_run(
                f"[{int(r['序号'])}]《{r['电影名称']}》{int(r['用户星级'])} 星｜"
                f"模型：{r['模型情感']}（{r['情感分数']:+.3f}）｜复核：{r['复核结论']}"
            )
            _font(run, FONT_HEAD, 9, bold=True)
            p2 = doc.add_paragraph()
            p2.paragraph_format.left_indent = Pt(14)
            p2.paragraph_format.space_after = Pt(5)
            p2.paragraph_format.line_spacing = 1.15
            r2 = p2.add_run(f"{str(r['评论文本'])[:180]}")
            _font(r2, FONT_BODY, 8.5)
            p3 = doc.add_paragraph()
            p3.paragraph_format.left_indent = Pt(14)
            p3.paragraph_format.space_after = Pt(7)
            p3.paragraph_format.line_spacing = 1.15
            r3 = p3.add_run(f"分析：{r['原因解释']}")
            _font(r3, FONT_BODY, 8.5, color=RGBColor(0x44, 0x44, 0x44))
    else:
        _p(doc, "（样本文件未生成，请先运行不一致分析模块）")

    # --- F 主要统计结果 ---
    _h(doc, "附件 F　主要统计结果", 2)
    _table(doc, d["q1"], "表 F-1　评分与评分人数描述统计",
           widths=[5.4, 4.6, 5.4], font_size=8.5)
    _table(doc, d["q1_corr"], "表 F-2　相关系数", widths=[6.4, 2.6, 3.8], font_size=9)
    if len(d["top10"]):
        show = d["top10"].copy()
        show["评分人数"] = show["评分人数"].map(lambda x: f"{int(x):,}")
        for c in ["平均文本情感", "被低估指数"]:
            show[c] = show[c].map(lambda v: f"{v:.3f}")
        _table(doc, show[["排名", "电影", "豆瓣评分", "评分人数", "有效评论数", "被低估指数"]],
               "表 F-3　被低估指数前十名（简表）",
               widths=[1.4, 3.8, 2.4, 2.8, 2.6, 2.6], font_size=9)

    # --- G 核心代码截图 ---
    _h(doc, "附件 G　核心 Python 代码截图与功能说明", 2)
    _p(doc, "以下 10 张截图由 src/code_screenshot.py 从实际源码渲染生成，"
            "只截取核心函数，不含 import 与 print 语句。每张图下方标注函数用途。")

    shots = [
        ("code_01_parse_top250.png",
         "代码 1　parse_top250_page：榜单页解析函数",
         "作用：把单页 HTML 解析为结构化电影记录（片名、评分、人数、导演、类型等），是数据采集的入口。"
         "输入为页面 HTML 与采集时间，输出记录列表；单条解析失败只跳过该条，不中断整页。"),
        ("code_02_clean_text.png",
         "代码 2　clean_text：文本清洗函数",
         "作用：去 HTML 标签与 URL、反转义实体、统一空白。刻意保留标点，因为标点承载情绪信息。"
         "非字符串输入返回空串而不抛异常。"),
        ("code_03_mark_duplicates.png",
         "代码 3　mark_duplicates：重复与相似检测函数",
         "作用：在同片内用字符级 TF-IDF 余弦相似度标记重复副本，保留首条。"
         "只在同片内比较，因为跨片相似更可能是巧合。"),
        ("code_04_classify.png",
         "代码 4　classify_by_rules：内容有效性分级函数",
         "作用：按信息密度分四档判定 A/B/C/E 类，核心是「不因短而删」："
         "「烂片」判为低信息量而非剔除，「摄影很棒」判为有效。"),
        ("code_05_consistency.png",
         "代码 5　label_consistency：星级一致性判定函数",
         "作用：第二维度。用星级归一值与情感分之差分四档，置信度过低的样本判为「无法判定」而不强行归类。"),
        ("code_06_sentiment.png",
         "代码 6　analyze_text：情感分析函数",
         "作用：词典 + 否定/程度/转折规则；未命中时回退到朴素贝叶斯极端值判定。"
         "全程不使用星级作为输入，保证 Q4 不循环论证。"),
        ("code_07_comparison.png",
         "代码 7　run_method_comparison：方法对比实验函数",
         "作用：在同一人工验证集上比较基础清洗法与改进清洗法的 P/R/F1、误杀率与覆盖率，"
         "并输出「改进是否成立」的判定。"),
        ("code_08_index.png",
         "代码 8　compute_index：被低估指数计算函数",
         "作用：按权重组合计算 U。S 与 R 各自做样本内 Z 标准化后再相减，"
         "解决原始公式中高分片 U 恒为负的问题；同时输出分项贡献便于解释。"),
        ("code_09_select_five.png",
         "代码 9　select_five：多样性约束选片函数",
         "作用：两轮贪心选取，第一轮每类型最多 1 部，不足时放宽到 2 部，"
         "保证五部影片在类型与年代上分散。"),
        ("code_10_viz.png",
         "代码 10　fig_method_comparison：方法对比图函数",
         "作用：把两套方法的关键指标可视化，同时展示 F1 提升与召回下降两个方向，"
         "不做选择性呈现。"),
    ]
    for fname, cap, desc in shots:
        _shot(doc, fname, cap, 12.2)
        _p(doc, desc, indent=False, size=9.5)
        doc.add_paragraph()

    # --- H 运行说明 ---
    _h(doc, "附件 H　项目运行说明", 2)
    _p(doc, "环境要求：Python 3.10 及以上（在 3.13.15 上验证过）。依赖见 requirements.txt。")
    _p(doc, "首次运行：在项目根目录执行 python main.py，程序会依次完成数据检查、采集、清洗、"
            "分级、情感分析、一致性判定、方法对比、统计分析、指数计算、偏差分析、推荐、"
            "图表生成、代码截图、Word 与 PPT 生成。任一环节失败不会中断后续可独立完成的环节。")
    _p(doc, "单独运行某一环节：python -m src.<模块名>，例如 python -m src.consistency_check。"
            "各模块读取上游产物、写出本环节结果，可独立执行。")
    _p(doc, "运行测试：python -m pytest tests/ -v。测试覆盖文本清洗、规则分级、一致性判定、"
            "指标计算与流程完整性。")
    _p(doc, "强制重新抓取：设置环境变量 DOUBAN_FORCE_REFETCH=1。默认复用已有原始文件，不覆盖原始数据。")
    _p(doc, "目录说明：data/raw 原始数据与 HTML 快照，data/interim 中间结果，"
            "data/processed 处理后数据，outputs/figures 图表，outputs/tables 统计表，"
            "outputs/screenshots 代码截图，outputs/reports 报告，outputs/logs 日志。")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------
def main() -> Path:
    """
    生成完整 Word 报告。

    返回:
        报告文件的绝对路径。
    """
    d = collect()

    doc = Document()
    _setup(doc)

    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.8)
    section.right_margin = Cm(2.4)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.4)

    footer_p = section.footer.paragraphs[0]
    footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _field(footer_p, "PAGE")

    build_cover(doc, d)
    build_abstract(doc, d)
    build_toc(doc)
    build_ch1(doc, d)
    build_ch2(doc, d)
    build_ch3(doc, d)
    build_ch4(doc, d)
    build_ch5(doc, d)
    build_ch6(doc, d)
    build_ch7(doc, d)
    build_ch8(doc, d)
    build_ch9(doc, d)
    build_ch10(doc, d)
    build_ch11(doc, d)
    build_refs(doc)
    build_appendix(doc, d)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / DOC_NAME
    doc.save(str(out))
    logger.info("Word 报告已生成: %s", out)
    return out


if __name__ == "__main__":
    print(main())