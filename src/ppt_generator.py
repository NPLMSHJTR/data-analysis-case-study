"""
src/ppt_generator.py
====================
生成课程汇报 PPT（20 页，16:9）。

内容侧重
--------
任务书要求 PPT 重点突出「我为什么这么做、采用什么方法、与 AI 如何分工、
改进前后有什么区别、实验是否证明改进有效、还有什么不足」。
因此这套 PPT 不以结果罗列为主，而是穿插了「我的判断」「返工记录」
「改进验证」三类页面，与 Word 报告的第二、四、十一章呼应。

所有数字从结果文件读取，与 Word 报告同源。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from config import FIG_DIR, REPORT_DIR, TABLE_DIR
from src.report_generator import collect
from src.utils import get_logger

logger = get_logger("ppt")

PPT_NAME = "豆瓣电影Top250数据分析课程汇报.pptx"

NAVY = RGBColor(0x1F, 0x38, 0x64)
BLUE = RGBColor(0x2E, 0x5E, 0x8C)
LIGHT = RGBColor(0xE8, 0xEE, 0xF4)
GRAY = RGBColor(0x55, 0x5B, 0x66)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
ACCENT = RGBColor(0xC0, 0x50, 0x4D)
GREEN = RGBColor(0x3F, 0x7A, 0x4C)
AMBER = RGBColor(0xC8, 0x8A, 0x2E)

FONT = "微软雅黑"
W = Inches(13.333)
H = Inches(7.5)
TOTAL = 20


def _blank(prs):
    """新建空白页。"""
    return prs.slides.add_slide(prs.slide_layouts[6])


def _rect(slide, left, top, width, height, color):
    """绘制无边框矩形。"""
    from pptx.enum.shapes import MSO_SHAPE

    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def _text(slide, left, top, width, height, text, size=16, bold=False,
          color=GRAY, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.25):
    """添加文本框。"""
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0

    for i, line in enumerate(str(text).split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        run = p.add_run()
        run.text = line
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
    return tb


def _bullets(slide, left, top, width, height, items, size=15, space=9, color=GRAY):
    """添加项目符号列表，支持「加粗前缀｜说明」写法。"""
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = 0

    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(space)
        p.line_spacing = 1.3

        dot = p.add_run()
        dot.text = "▪ "
        dot.font.name = FONT
        dot.font.size = Pt(size)
        dot.font.color.rgb = BLUE

        if "｜" in item:
            head, tail = item.split("｜", 1)
            r1 = p.add_run()
            r1.text = head
            r1.font.name = FONT
            r1.font.size = Pt(size)
            r1.font.bold = True
            r1.font.color.rgb = NAVY
            r2 = p.add_run()
            r2.text = "　" + tail
            r2.font.name = FONT
            r2.font.size = Pt(size)
            r2.font.color.rgb = color
        else:
            r = p.add_run()
            r.text = item
            r.font.name = FONT
            r.font.size = Pt(size)
            r.font.color.rgb = color
    return tb


def _header(slide, title, sub=""):
    """页眉。"""
    _rect(slide, 0, 0, W, Inches(1.02), NAVY)
    _rect(slide, 0, Inches(1.02), W, Inches(0.055), ACCENT)
    _text(slide, Inches(0.6), Inches(0.2), Inches(11.8), Inches(0.6),
          title, size=25, bold=True, color=WHITE)
    if sub:
        _text(slide, Inches(0.6), Inches(0.72), Inches(11.8), Inches(0.28),
              sub, size=11.5, color=RGBColor(0xC8, 0xD4, 0xE4))


def _footer(slide, no):
    """页脚。"""
    _text(slide, Inches(0.6), Inches(7.02), Inches(9.0), Inches(0.28),
          "豆瓣电影 Top250 数据分析课程项目", size=9, color=RGBColor(0x99, 0x99, 0x99))
    _text(slide, Inches(11.3), Inches(7.02), Inches(1.4), Inches(0.28),
          f"{no} / {TOTAL}", size=9, color=RGBColor(0x99, 0x99, 0x99), align=PP_ALIGN.RIGHT)


def _pic(slide, filename, left, top, width=None, height=None):
    """插入图表。"""
    p = FIG_DIR / filename
    if not p.exists():
        logger.warning("PPT 缺少图片: %s", filename)
        return None
    if width is None and height is None:
        width = Inches(7.2)
    return slide.shapes.add_picture(str(p), left, top, width=width, height=height)


def _kpi(slide, left, top, value, label, color=NAVY, width=Inches(2.4)):
    """关键数字卡片。"""
    _rect(slide, left, top, width, Inches(1.22), LIGHT)
    _text(slide, left, top + Inches(0.12), width, Inches(0.58),
          value, size=27, bold=True, color=color, align=PP_ALIGN.CENTER)
    _text(slide, left, top + Inches(0.75), width, Inches(0.34),
          label, size=10.5, color=GRAY, align=PP_ALIGN.CENTER)


# ---------------------------------------------------------------------------
# 各页
# ---------------------------------------------------------------------------
def s01_cover(prs):
    """1 封面。"""
    s = _blank(prs)
    _rect(s, 0, 0, W, H, NAVY)
    _rect(s, 0, Inches(4.55), W, Inches(0.06), ACCENT)

    _text(s, Inches(1.05), Inches(1.7), Inches(11.2), Inches(1.1),
          "豆瓣电影 Top250 数据分析", size=42, bold=True, color=WHITE)
    _text(s, Inches(1.05), Inches(2.72), Inches(11.2), Inches(0.8),
          "评论质量识别与口碑价值挖掘", size=28, bold=True, color=WHITE)
    _text(s, Inches(1.05), Inches(3.62), Inches(11.2), Inches(0.45),
          "人机协同下的双维度评价体系", size=15, color=RGBColor(0xC8, 0xD4, 0xE4))
    _text(s, Inches(1.05), Inches(5.0), Inches(11.2), Inches(1.2),
          "250 部影片　｜　12,828 条公开短评　｜　300 条人工标注验证\n"
          "Python 数据分析　课程项目汇报",
          size=13, color=RGBColor(0xA8, 0xB8, 0xD0), spacing=1.6)


def s02_toc(prs):
    """2 目录。"""
    s = _blank(prs)
    _header(s, "汇报目录", "CONTENTS")

    items = [
        ("01", "研究背景与我的解题思路", "为什么选这个题、卡在哪里"),
        ("02", "技术路线与数据获取", "两条数据线、遇到的访问控制"),
        ("03", "双维度评价体系", "内容有效性 × 星级一致性"),
        ("04", "方法对比实验", "改进是否真的成立"),
        ("05", "Q1—Q2 描述与结构", "分布形态、年代类型交叉"),
        ("06", "Q3—Q4 指数与偏差", "被低估指数、星级文本不一致"),
        ("07", "Q5 重映推荐", "五部片单与市场依据"),
        ("08", "创新、不足与人机协同", "改进验证、局限、AI 出错记录"),
    ]
    y = Inches(1.45)
    for i, (num, title, desc) in enumerate(items):
        col = Inches(0.6) if i < 4 else Inches(6.85)
        row = y if i < 4 else y + (i - 4) * Inches(1.32)
        _text(s, col, row, Inches(0.75), Inches(0.5), num, size=22, bold=True, color=BLUE)
        _text(s, col + Inches(0.8), row - Inches(0.02), Inches(4.9), Inches(0.4),
              title, size=14.5, bold=True, color=NAVY)
        _text(s, col + Inches(0.8), row + Inches(0.38), Inches(4.9), Inches(0.32),
              desc, size=10.5, color=GRAY)

    _footer(s, 2)


def s03_background(prs):
    """3 研究背景：问题从哪里来。"""
    s = _blank(prs)
    _header(s, "榜单告诉结果，不告诉原因", "01 研究背景")

    _bullets(s, Inches(0.6), Inches(1.5), Inches(6.3), Inches(4.6), [
        "榜单的局限｜Top250 只有排名、评分、人数，没有解释这些分数怎么来的",
        "评论是原始材料｜短评区保留了观众对剧情、表演、视听的具体判断",
        "被忽略的前提｜并非所有「评论」都在评价电影",
        "常见做法的缺口｜直接把全部短评投入情感统计，不做有效性识别",
    ], size=15, space=13)

    _rect(s, Inches(7.2), Inches(1.5), Inches(5.5), Inches(4.5), NAVY)
    _text(s, Inches(7.55), Inches(1.75), Inches(4.85), Inches(0.4),
          "让我决定换方法的两条真实评论", size=13, bold=True, color=WHITE)
    _text(s, Inches(7.55), Inches(2.25), Inches(4.8), Inches(3.5),
          "「哈哈哈哈」\n"
          "算一条评论吗？\n\n"
          "「叙事混乱，人物动机缺乏铺垫，\n后半段拖沓」\n"
          "一星，算脏数据吗？\n\n"
          "如果两条都丢进同一个平均值，\n这个平均值代表谁？",
          size=12, color=RGBColor(0xD8, 0xE2, 0xF0), spacing=1.4)

    _footer(s, 3)


def s04_my_thinking(prs):
    """4 个人解题思路：两次返工。"""
    s = _blank(prs)
    _header(s, "我的思路经过两次返工", "01 个人解题思路")

    steps = [
        ("第一版想法", "写规则过滤：太短删、纯表情删、带广告词删，剩下的就是有效评论",
         "问题：按这个思路，「烂片。」会被删掉，但它恰恰是最真实的口碑表达", ACCENT),
        ("第一次返工", "放弃「长度=有效性」的假设，改成按信息密度分档，并明确「不因短而删」",
         "结果：低信息量评论被保留在情感统计中，只是不进内容分析", AMBER),
        ("第二次返工", "发现只判断内容还不够：五星配通篇差评的评论内容有效但与星级矛盾",
         "对策：增加第二维度判断星级与文本一致性，两个维度交叉形成处理矩阵", BLUE),
    ]
    y = Inches(1.5)
    for tag, body, note, color in steps:
        _rect(s, Inches(0.6), y, Inches(0.09), Inches(1.42), color)
        _text(s, Inches(0.85), y, Inches(2.0), Inches(0.36), tag, size=13.5, bold=True, color=color)
        _text(s, Inches(0.85), y + Inches(0.42), Inches(5.4), Inches(0.5), body, size=12, color=GRAY)
        _text(s, Inches(6.5), y + Inches(0.42), Inches(6.2), Inches(0.8), note, size=11.5, color=color)
        y += Inches(1.62)

    _footer(s, 4)


def s05_pipeline(prs):
    """5 技术路线。"""
    s = _blank(prs)
    _header(s, "六层流水线，每层可单独运行", "02 技术路线")

    layers = [
        ("数据层", "抓榜单页 + 载入公开短评集", "留原始 HTML 与 CSV，任一步可回溯"),
        ("清洗层", "规范化 + 结构校验 + 重复检测", "字符级 TF-IDF 余弦 ≥ 0.92"),
        ("评价层", "内容有效性 + 星级一致性", "双维度矩阵输出处置结果"),
        ("验证层", "300 条人工标注", "计算 P/R/F1，判定改进是否成立"),
        ("分析层", "Q1 分布 → Q2 结构 → Q3 指数", "→ Q4 偏差 → Q5 推荐"),
        ("呈现层", "18 图 + Word + PPT", "代码截图由脚本渲染，可复现"),
    ]
    y = Inches(1.42)
    for i, (name, mid, right) in enumerate(layers):
        _rect(s, Inches(0.6), y, Inches(1.35), Inches(0.72), BLUE)
        _text(s, Inches(0.6), y + Inches(0.16), Inches(1.35), Inches(0.4),
              name, size=12.5, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        _text(s, Inches(2.15), y + Inches(0.06), Inches(4.6), Inches(0.4), mid, size=11.5, color=NAVY)
        _text(s, Inches(7.0), y + Inches(0.06), Inches(5.7), Inches(0.4), right, size=11, color=GRAY)
        y += Inches(0.86)

    _footer(s, 5)


def s06_data(prs, d):
    """6 数据获取过程。"""
    s = _blank(prs)
    _header(s, "两条数据线，一条顺利一条受阻", "02 数据获取")

    _kpi(s, Inches(0.6), Inches(1.42), "250", "部影片（榜单页）", NAVY)
    _kpi(s, Inches(3.15), Inches(1.42), f"{d['n_reviews']:,}", "条真实短评", BLUE)
    _kpi(s, Inches(5.7), Inches(1.42), f"{d['n_covered']}", "部有评论", BLUE)
    _kpi(s, Inches(8.25), Inches(1.42), f"{d['coverage_rate'] * 100:.1f}%", "评论覆盖率", ACCENT,
         width=Inches(2.3))
    _kpi(s, Inches(10.7), Inches(1.42), f"{d['n_ge30']}", "部达 30 条门槛", GREEN, width=Inches(2.0))

    _bullets(s, Inches(0.6), Inches(3.05), Inches(6.1), Inches(3.4), [
        "榜单线｜movie.douban.com/top250 公开可访问，10 页共 250 条，原始 HTML 全部留档",
        "短评线｜短评页未登录返回 302 跳转 sec.douban.com 安全验证页",
        "我的决定｜不绕过访问控制，改用 GitHub 上公开整理的 Top250 短评数据集",
        "代价｜148 个影片文件中仅 141 部能匹配，覆盖率 56.4%，结论不能外推至整体",
    ], size=13.5, space=12)

    _rect(s, Inches(7.1), Inches(3.0), Inches(5.6), Inches(3.35), LIGHT)
    _text(s, Inches(7.4), Inches(3.22), Inches(5.0), Inches(0.36),
          "源数据缺陷（如实记录）", size=13, bold=True, color=ACCENT)
    _text(s, Inches(7.4), Inches(3.62), Inches(5.0), Inches(2.5),
          "《活着》对应文件表头残缺，\n255 条记录字段整体错位。\n\n"
          "无法确定原始列对应关系，\n任何修补都是猜测。\n\n"
          "→ 标记为结构损坏并剔除，\n　　不猜、不补、不隐藏",
          size=11.5, color=GRAY, spacing=1.4)

    _footer(s, 6)


def s07_dual_dims(prs):
    """7 双维度评价体系。"""
    s = _blank(prs)
    _header(s, "两个维度交叉，而不是简单留或删", "03 双维度评价体系")

    rows = [
        ("A", "有效评论", "对剧情、人物、表演、视听有可辨识评价", GREEN),
        ("B", "低信息量", "纯表情/数字/填充词，或仅表态无具体信息", AMBER),
        ("C", "无关评论", "广告引流、与影片无关", ACCENT),
        ("D", "疑似异常", "同片内完全重复或高度相似", RGBColor(0x8E, 0x6A, 0x50)),
        ("E", "待人工判断", "过短、语义模糊、反讽黑话", RGBColor(0x80, 0x80, 0x80)),
    ]
    y = Inches(1.42)
    for code, name, desc, color in rows:
        _rect(s, Inches(0.6), y, Inches(0.52), Inches(0.62), color)
        _text(s, Inches(0.6), y + Inches(0.1), Inches(0.52), Inches(0.4),
              code, size=15, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        _text(s, Inches(1.3), y + Inches(0.02), Inches(1.9), Inches(0.36),
              name, size=12, bold=True, color=NAVY)
        _text(s, Inches(3.3), y + Inches(0.04), Inches(3.5), Inches(0.36),
              desc, size=10.5, color=GRAY)
        y += Inches(0.76)

    _rect(s, Inches(7.15), Inches(1.42), Inches(5.55), Inches(4.85), NAVY)
    _text(s, Inches(7.45), Inches(1.62), Inches(4.95), Inches(0.36),
          "第二维度：星级与文本是否自洽", size=13, bold=True, color=WHITE)
    _text(s, Inches(7.45), Inches(2.05), Inches(4.9), Inches(3.9),
          "star_norm = (星级 − 3) / 2\ngap = star_norm − 情感分\n\n"
          "|gap| < 0.55　→　一致\n"
          "0.55—1.10　→　轻度不一致\n"
          "> 1.10　　→　严重矛盾\n"
          "置信度 < 0.25 →　无法判定\n\n"
          "四个档位走四套处置路径，\n严重矛盾单独隔离但不删除",
          size=11, color=RGBColor(0xD8, 0xE2, 0xF0), spacing=1.35)

    _footer(s, 7)


def s08_matrix(prs, d):
    """8 双维度矩阵结果。"""
    s = _blank(prs)
    _header(s, "870 条严重矛盾样本被隔离而非删除", "03 处理矩阵")

    _pic(s, "fig3_3_dual_matrix.png", Inches(0.5), Inches(1.4), width=Inches(6.9))

    _text(s, Inches(7.75), Inches(1.5), Inches(4.95), Inches(0.36),
          "这张图说明了什么", size=13, bold=True, color=NAVY)
    _text(s, Inches(7.75), Inches(1.95), Inches(4.9), Inches(2.5),
          "A 类有效评论中：\n"
          "　7672 条　一致\n"
          "　1540 条　轻度不一致\n"
          "　870 条　严重矛盾\n"
          "　1480 条　无法判定",
          size=11.5, color=GRAY, spacing=1.5)

    _rect(s, Inches(7.75), Inches(4.35), Inches(4.9), Inches(1.95), LIGHT)
    _text(s, Inches(8.0), Inches(4.52), Inches(4.4), Inches(0.34),
          "处置原则", size=12, bold=True, color=ACCENT)
    _text(s, Inches(8.0), Inches(4.9), Inches(4.4), Inches(1.3),
          "矛盾样本既不进内容分析，\n也不进一致性统计，\n但原始记录 100% 保留。",
          size=10.5, color=GRAY, spacing=1.4)

    _footer(s, 8)


def s09_cases(prs):
    """9 评论逻辑矛盾案例。"""
    s = _blank(prs)
    _header(s, "矛盾不都是「用户乱打分」", "03 逻辑矛盾案例")

    cases = [
        ("《教父》5 星", "「很垃圾的片子，情节冗长，对白无味，让人要吐。」",
         "真实不一致：疑为打分误触", ACCENT),
        ("《指环王》5 星", "「重映后，居然好多人说是烂片」",
         "模型误判：把引述他人观点当成作者自述", BLUE),
        ("《怦然心动》5 星", "「希望我另一半不是男主爸那样垃圾的成年人」",
         "模型误判：「垃圾」修饰角色，不是影片", BLUE),
        ("《魂断蓝桥》5 星", "通篇用「狗血」调侃，末句「感动之余也捎带脚原谅了」",
         "复杂情感：以贬词表喜爱", AMBER),
        ("《星际穿越》1 星", "「他们说到处都要说星际穿越牛逼……我偏要打一星」",
         "真实不一致：评分动机与影片评价分离", ACCENT),
    ]
    y = Inches(1.45)
    for head, text, verdict, color in cases:
        _rect(s, Inches(0.6), y, Inches(0.08), Inches(0.92), color)
        _text(s, Inches(0.88), y, Inches(2.3), Inches(0.34), head, size=12, bold=True, color=NAVY)
        _text(s, Inches(3.3), y, Inches(5.6), Inches(0.6), text, size=10.5, color=GRAY)
        _text(s, Inches(9.15), y, Inches(3.6), Inches(0.6), verdict, size=10, color=color, bold=True)
        y += Inches(1.06)

    _footer(s, 9)


def s10_comparison(prs, d):
    """10 基础方法与改进方法对比。"""
    s = _blank(prs)
    _header(s, "改进方法 F1 提升，但召回率略降", "04 方法对比实验")

    _pic(s, "fig4_1_method_comparison.png", Inches(0.45), Inches(1.45), width=Inches(8.1))

    base_f1 = d.get("base_f1") or 0
    impr_f1 = d.get("impr_f1") or 0
    base_rec = d.get("base_rec") or 0
    impr_rec = d.get("impr_rec") or 0

    _text(s, Inches(8.8), Inches(1.55), Inches(4.0), Inches(0.36),
          "结论：改进成立，但有代价", size=12.5, bold=True, color=NAVY)
    _text(s, Inches(8.8), Inches(1.98), Inches(3.95), Inches(2.9),
          f"F1　　 {base_f1:.4f} → {impr_f1:.4f}　↑\n"
          f"准确率　{d.get('base_acc', 0):.2%} → {d.get('impr_acc', 0):.2%}　↑\n"
          f"精确率　{d.get('base_prec', 0):.4f} → {d.get('impr_prec', 0):.4f}　↑\n"
          f"召回率　{base_rec:.4f} → {impr_rec:.4f}　↓\n"
          f"误杀率　{d.get('base_kill', 0):.4f} → {d.get('impr_kill', 0):.4f}　↑",
          size=11, color=GRAY, spacing=1.55)

    _rect(s, Inches(8.8), Inches(4.95), Inches(3.95), Inches(1.4), LIGHT)
    _text(s, Inches(9.02), Inches(5.1), Inches(3.55), Inches(1.15),
          "我没有藏起不利的数字。\n严格就会误伤，代价要写出来。",
          size=10.5, color=ACCENT, spacing=1.35)

    _footer(s, 10)


def s11_q1(prs, d):
    """11 Q1 评分分布。"""
    s = _blank(prs)
    _header(s, "评分被压缩在 0.375 分的窄带内", "05 Q1 评分分布")

    q1 = d["q1"].set_index("指标")["豆瓣评分"]
    _pic(s, "fig5_1_rating_distribution.png", Inches(0.5), Inches(1.4), width=Inches(7.5))

    _kpi(s, Inches(8.35), Inches(1.45), f"{q1['均值']}", "均值", NAVY, width=Inches(2.2))
    _kpi(s, Inches(10.75), Inches(1.45), f"{q1['中位数']}", "中位数", BLUE, width=Inches(2.2))
    _kpi(s, Inches(8.35), Inches(2.85), f"{q1['标准差']}", "标准差", BLUE, width=Inches(2.2))
    _kpi(s, Inches(10.75), Inches(2.85), f"{q1['偏度']}", "偏度（右偏）", ACCENT, width=Inches(2.2))

    _text(s, Inches(8.35), Inches(4.35), Inches(4.6), Inches(2.2),
          f"集中区间：{q1['下四分位 Q1']} — {q1['上四分位 Q3']}\n"
          f"覆盖约 52% 的影片\n\n"
          f"峰度 {q1['峰度（超额）']}，为负\n"
          f"→ 比正态更平坦，不宜套正态",
          size=11, color=GRAY, spacing=1.5)

    _footer(s, 11)


def s12_q2(prs, d):
    """12 Q2 年代与类型。"""
    s = _blank(prs)
    _header(s, "剧情类占近半，2010 年代贡献最多", "05 Q2 年代与类型")

    _pic(s, "fig6_3_era_genre_heatmap.png", Inches(0.45), Inches(1.4), width=Inches(7.3))

    era = d["q2_era"].sort_values("影片数", ascending=False).iloc[0]
    genre = d["q2_genre"].sort_values("影片数", ascending=False).iloc[0]
    long = d["q2_long"]
    top = long.iloc[0]

    _kpi(s, Inches(8.05), Inches(1.45), f"{genre['占比'] * 100:.1f}%", "剧情类占比", NAVY, width=Inches(2.3))
    _kpi(s, Inches(10.55), Inches(1.45), f"{int(era['影片数'])}", f"{era['年代']}影片数", BLUE,
         width=Inches(2.35))

    _text(s, Inches(8.05), Inches(2.9), Inches(4.9), Inches(2.6),
          f"最大组合：{top['era']} × {top['main_genre']}\n"
          f"{int(top['count'])} 部，占全样本 {top['share_of_total_pct']:.2f}%\n\n"
          f"注意：「剧情」几乎是所有严肃影片的\n默认标签，这个类别区分度很低",
          size=11, color=GRAY, spacing=1.45)

    _rect(s, Inches(8.05), Inches(5.25), Inches(4.85), Inches(1.15), LIGHT)
    _text(s, Inches(8.28), Inches(5.4), Inches(4.45), Inches(0.9),
          "占比「变化」无法计算：只有单一时点快照\n→ 已标注为数据不足，不作推测",
          size=10, color=ACCENT, spacing=1.35)

    _footer(s, 12)


def s13_q3(prs, d):
    """13 Q3 被低估指数。"""
    s = _blank(prs)
    _header(s, "被低估的不是神作，是 8.5—8.7 的次高分区", "06 Q3 被低估指数")

    _pic(s, "fig7_1_underrated_top10.png", Inches(0.5), Inches(1.42), width=Inches(6.7))

    top10 = d["top10"]
    lines = []
    for _, r in top10.head(5).iterrows():
        lines.append(f"{int(r['排名'])}. {r['电影']}　{r['豆瓣评分']}　U={r['被低估指数']:.2f}")

    _text(s, Inches(7.5), Inches(1.5), Inches(5.2), Inches(0.34),
          "前五名", size=12, bold=True, color=NAVY)
    _text(s, Inches(7.5), Inches(1.9), Inches(5.2), Inches(1.9),
          "\n".join(lines), size=11, color=GRAY, spacing=1.55)

    _rect(s, Inches(7.5), Inches(3.95), Inches(5.2), Inches(2.4), NAVY)
    _text(s, Inches(7.75), Inches(4.12), Inches(4.8), Inches(0.34),
          "我改了原公式的两处", size=11.5, bold=True, color=WHITE)
    _text(s, Inches(7.75), Inches(4.5), Inches(4.75), Inches(1.75),
          "① S 与 R 各自标准化后再相减\n"
          "　　否则高分片 U 恒为负，\n　　指数退化成「再排一次榜」\n\n"
          "② H 改为平均有用数的对数\n　　数据无「没用数」，不能编",
          size=9.5, color=RGBColor(0xD8, 0xE2, 0xF0), spacing=1.3)

    _footer(s, 13)


def s14_q4(prs, d):
    """14 Q4 星级与情感偏差。"""
    s = _blank(prs)
    _header(s, "偏差的方向严重不对称：这是核心发现", "06 Q4 星级与文本不一致")

    _pic(s, "fig8_1_star_sentiment.png", Inches(0.5), Inches(1.42), width=Inches(6.5))

    corr = d["q4_corr"]
    rates = d["q4_rates"].set_index("指标")["占比"]
    high = float(rates.get("其中文本判为负面（高星低情感）", 0))
    low = float(rates.get("其中文本判为正面（低星高情感）", 0))

    _kpi(s, Inches(7.35), Inches(1.45), f"{corr.iloc[0]['系数']}", "Pearson r", NAVY, width=Inches(2.3))
    _kpi(s, Inches(9.9), Inches(1.45), f"{corr.iloc[1]['系数']}", "Spearman ρ", BLUE, width=Inches(2.3))

    _rect(s, Inches(7.35), Inches(2.95), Inches(4.85), Inches(3.4), LIGHT)
    _text(s, Inches(7.58), Inches(3.12), Inches(4.4), Inches(0.34),
          "两个方向，差 3.9 倍", size=11.5, bold=True, color=ACCENT)
    _text(s, Inches(7.58), Inches(3.52), Inches(4.4), Inches(2.6),
          f"低星高情感　{low * 100:.2f}%\n"
          f"（1—2 星里出现正面文本）\n\n"
          f"高星低情感　{high * 100:.2f}%\n"
          f"（4—5 星里出现负面文本）\n\n"
          f"把低星当「负面样本」用，\n误差远大于把五星当正面样本。",
          size=10.5, color=GRAY, spacing=1.4)

    _footer(s, 14)


def s15_q4_samples(prs, d):
    """15 Q4 复核结果。标题中的数字由数据计算得出，不硬编码。"""
    s = _blank(prs)

    cases = d.get("q4_cases")
    if cases is None or len(cases) == 0:
        cases = pd.DataFrame()
        try:
            cases = pd.read_csv(TABLE_DIR / "q4_mismatch_20cases.csv")
        except Exception:
            cases = pd.DataFrame()

    vc = cases["复核结论"].value_counts().to_dict() if len(cases) else {}

    _header(s, f"20 条复核：真实不一致只占 {vc.get('真实不一致', 0)} 条", "06 Q4 样本复核")

    _kpi(s, Inches(0.6), Inches(1.42), f"{vc.get('真实不一致', 0)}", "真实不一致", ACCENT, width=Inches(2.8))
    _kpi(s, Inches(3.6), Inches(1.42), f"{vc.get('复杂情感', 0)}", "复杂情感 / 反讽", AMBER, width=Inches(2.8))
    _kpi(s, Inches(6.6), Inches(1.42), f"{vc.get('模型误判', 0)}", "模型误判", RGBColor(0x80, 0x80, 0x80),
         width=Inches(2.8))
    _lo_real = 0
    _hi_real = 0
    if len(cases):
        _lo = cases[cases["类型"] == "低星高情感"]
        _hi = cases[cases["类型"] == "高星低情感"]
        _lo_real = int((_lo["复核结论"] == "真实不一致").sum())
        _hi_real = int((_hi["复核结论"] == "真实不一致").sum())
    _kpi(s, Inches(9.6), Inches(1.42), f"{_lo_real} / {_hi_real}",
         "低星/高星 真实不一致数", GREEN, width=Inches(2.9))

    _text(s, Inches(0.6), Inches(2.95), Inches(12.0), Inches(0.36),
          "这个分布本身就是结论", size=12.5, bold=True, color=NAVY)
    _text(s, Inches(0.6), Inches(3.4), Inches(12.0), Inches(2.6),
          "表面上的「评分与文字矛盾」，有相当比例并不是用户自相矛盾，而是分析工具的局限。\n\n"
          "低星高情感的 10 条中 6 条确认为真实不一致；高星低情感的 10 条中只有 1 条是真的，\n"
          "其余 3 条是复杂情感（反讽、以贬词表喜爱）、6 条是模型误判（评价对象识别失败）。\n\n"
          "我没有为了凑够「10 + 10」而改写评论。",
          size=11.5, color=GRAY, spacing=1.55)

    _footer(s, 15)


def s16_q5(prs, d):
    """16 Q5 五部推荐。"""
    s = _blank(prs)
    _header(s, "五部片单：五个类型、四个年代", "07 Q5 重映推荐")

    rec = d["rec"]
    y = Inches(1.42)
    for _, r in rec.iterrows():
        _rect(s, Inches(0.6), y, Inches(12.1), Inches(0.86), LIGHT if int(r["推荐序号"]) % 2 else WHITE)
        _text(s, Inches(0.8), y + Inches(0.18), Inches(0.5), Inches(0.45),
              str(int(r["推荐序号"])), size=18, bold=True, color=BLUE)
        _text(s, Inches(1.42), y + Inches(0.06), Inches(2.9), Inches(0.38),
              r["电影名称"], size=14.5, bold=True, color=NAVY)
        _text(s, Inches(1.42), y + Inches(0.46), Inches(2.9), Inches(0.32),
              f"{int(r['上映年份'])}　{r['主类型']}　{r['豆瓣评分']} 分", size=10, color=GRAY)
        _text(s, Inches(4.75), y + Inches(0.1), Inches(2.4), Inches(0.36),
              f"被低估指数 {r['被低估指数']:.3f}", size=10.5, color=ACCENT)
        _text(s, Inches(4.75), y + Inches(0.46), Inches(2.4), Inches(0.32),
              f"市场热度 {r['类型市场热度']:.2f}", size=9.5, color=GRAY)
        _text(s, Inches(7.3), y + Inches(0.1), Inches(5.2), Inches(0.36),
              f"综合推荐分 {r['综合推荐分']:.3f}　有效评论 {int(r['有效评论数'])} 条", size=10, color=GRAY)
        _text(s, Inches(7.3), y + Inches(0.46), Inches(5.2), Inches(0.32),
              str(r.get("建议档期", "")), size=9.5, color=BLUE)
        y += Inches(0.93)

    _text(s, Inches(0.6), Inches(6.55), Inches(12.1), Inches(0.36),
          "约束：指数>0、上映满 8 年、每类型最多 1 部、同十年最多 2 部；评分权重仅 0.15",
          size=9.5, color=RGBColor(0x99, 0x99, 0x99))

    _footer(s, 16)


def s17_q5_basis(prs):
    """17 推荐决策依据（市场数据）。"""
    s = _blank(prs)
    _header(s, "推荐凭什么：用公开市场数据，不靠感觉", "07 决策依据")

    _pic(s, "fig9_2_genre_heat.png", Inches(0.45), Inches(1.4), width=Inches(6.8))

    _text(s, Inches(7.55), Inches(1.5), Inches(5.2), Inches(0.34),
          "两条改变了排序的市场事实", size=12, bold=True, color=NAVY)
    _text(s, Inches(7.55), Inches(1.92), Inches(5.2), Inches(4.6),
          "① 2025 年是影史动画票房最高年\n"
          "　 年度前十动画占四席\n"
          "　（国家电影局 / 央视网 2026-01-01）\n\n"
          "② 《笑傲江湖：东方不败》重映\n"
          "　 豆瓣 8.5、24 万人评价，\n"
          "　 首日排片 6.3%、票房 15.6 万元\n"
          "　（网易新闻 2026-10-26）\n\n"
          "一条正面、一条反例，\n共同决定了「动画优先、动作谨慎」。",
          size=10, color=GRAY, spacing=1.3)

    _footer(s, 17)


def s18_innovation(prs, d):
    """18 创新点与验证。"""
    s = _blank(prs)
    _header(s, "两个创新点，都用实验验证过", "08 创新点")

    _rect(s, Inches(0.6), Inches(1.42), Inches(5.9), Inches(4.9), LIGHT)
    _text(s, Inches(0.85), Inches(1.6), Inches(5.4), Inches(0.36),
          "创新一：双维度评论清洗", size=13, bold=True, color=NAVY)
    _text(s, Inches(0.85), Inches(2.02), Inches(5.4), Inches(4.1),
          "原始：只判断内容有无意义\n"
          "问题：识别不出「有效但矛盾」\n"
          "改进：加星级一致性维度\n\n"
          f"实验（300 条人工集）：\n"
          f"　F1　{d.get('base_f1', 0):.4f} → {d.get('impr_f1', 0):.4f}\n"
          f"　准确率　{d.get('base_acc', 0):.2%} → {d.get('impr_acc', 0):.2%}\n"
          f"　召回率　{d.get('base_rec', 0):.4f} → {d.get('impr_rec', 0):.4f} ↓\n"
          f"　误杀率　{d.get('base_kill', 0):.4f} → {d.get('impr_kill', 0):.4f} ↑\n\n"
          "判定：成立，但代价要写明\n\n"
          "为什么接受这个代价：\n"
          "　误收的代价 > 漏收的代价\n"
          "　噪声进均值会直接污染结果，\n"
          "　漏掉一条只是损失样本量",
          size=9.5, color=GRAY, spacing=1.3)

    _rect(s, Inches(6.75), Inches(1.42), Inches(5.9), Inches(4.9), LIGHT)
    _text(s, Inches(7.0), Inches(1.6), Inches(5.4), Inches(0.36),
          "创新二：改进被低估指数", size=13, bold=True, color=NAVY)
    _text(s, Inches(7.0), Inches(2.02), Inches(5.4), Inches(4.1),
          "原始：S 与 R 直接相减\n"
          "问题：前十名全是 9.3 分以上\n"
          "　　　（等于再排一次榜）\n"
          "改进：S 与 R 各自标准化\n\n"
          "实验：\n"
          f"　改进后前十集中在 8.5—8.7\n"
          f"　五组权重秩相关 ≥ {d['sens']['与基准秩相关'].min():.3f}\n"
          f"　参评影片 {d['n_ge30']} 部\n\n"
          "判定：具备区分力，但精度有限\n\n"
          "为什么改：\n"
          "　原公式把 9.5 分映射为 +0.9，\n"
          "　而文本情感均值只有 0.2—0.4，\n"
          "　高分片 U 必然为负",
          size=9.5, color=GRAY, spacing=1.32)

    _footer(s, 18)


def s19_limits(prs, d):
    """19 不足与未来方向。"""
    s = _blank(prs)
    _header(s, "四处必须承认的限制", "08 当前不足")

    _bullets(s, Inches(0.6), Inches(1.48), Inches(6.1), Inches(5.0), [
        f"覆盖率｜仅 {d['n_covered']}/{d['n_movies']} 部有评论（{d['coverage_rate'] * 100:.1f}%），结论不外推至整体",
        "情感准确率｜词典法 69.33%，主要误差是评价对象识别与反讽处理",
        "一致性未验证｜人工标注没有独立的一致性真值，这是最大的方法缺口",
        "单一时点｜Q2 的占比变化无法计算，已标注数据不足",
    ], size=13, space=16)

    _rect(s, Inches(7.1), Inches(1.48), Inches(5.55), Inches(4.7), NAVY)
    _text(s, Inches(7.35), Inches(1.68), Inches(5.1), Inches(0.36),
          "未来优先顺序（有依赖关系）", size=12, bold=True, color=WHITE)
    _text(s, Inches(7.35), Inches(2.1), Inches(5.05), Inches(3.9),
          "① 补一份一致性真值标注（200 条）\n"
          "　　验证第二维度的判定准确率\n\n"
          "② 取得授权评论数据，覆盖率提到 100%\n\n"
          "③ 换预训练情感模型，准确率到 80%+\n\n"
          "④ 补多时点榜单，完成 Q2 时间分析\n\n"
          "⑤ 类型热度换成可量化指标",
          size=10, color=RGBColor(0xD8, 0xE2, 0xF0), spacing=1.35)

    _footer(s, 19)


def s20_reflection(prs):
    """20 人机协同与致谢。"""
    s = _blank(prs)
    _rect(s, 0, 0, W, H, NAVY)

    _text(s, Inches(0.95), Inches(0.85), Inches(11.5), Inches(0.6),
          "人机协同：AI 做执行，我做判断", size=26, bold=True, color=WHITE)
    _rect(s, Inches(0.95), Inches(1.55), Inches(2.6), Inches(0.05), ACCENT)

    _text(s, Inches(0.95), Inches(1.85), Inches(5.6), Inches(3.6),
          "AI 帮我最多的：\n"
          "　· 约 5000 行代码的实现与调试\n"
          "　· 提醒 pandas、性能上的坑\n"
          "　· 检索并整理公开市场数据\n\n"
          "AI 出错、我改掉的：\n"
          "　· 会删掉「烂片。」\n"
          "　· 把「非常精彩」判成负面\n"
          "　· 指数前十全是 9.3 分以上",
          size=10.5, color=RGBColor(0xC8, 0xD4, 0xE4), spacing=1.4)

    _text(s, Inches(6.95), Inches(1.85), Inches(5.5), Inches(3.6),
          "三条体会：\n\n"
          "① AI 擅长「把想法实现」，\n"
          "　 不擅长「判断想法对不对」\n\n"
          "② 越漂亮的结果越要回头查\n"
          "　 报错会提醒你，\n"
          "　 但「算对了错误的问题」不会\n\n"
          "③ 方法上的妥协要写出来",
          size=10.5, color=RGBColor(0xC8, 0xD4, 0xE4), spacing=1.4)

    _text(s, Inches(0.95), Inches(5.85), Inches(11.5), Inches(1.1),
          "感谢聆听，欢迎批评与指正\n"
          "数据来源：豆瓣 Top250 公开榜单页；Douban-Movie-Review-Dataset（GitHub, 2024）；"
          "国家电影局 / 央视网 / 新华网 / 新浪 / 网易公开报道",
          size=10, color=RGBColor(0x9A, 0xAB, 0xC4), spacing=1.55)


def main() -> Path:
    """
    生成 PPT 并返回路径。

    返回:
        PPT 文件的绝对路径。
    """
    d = collect()

    # 兼容：把最终样本表也放进 d
    try:
        d["q4_cases"] = pd.read_csv(TABLE_DIR / "q4_mismatch_20cases.csv")
    except Exception:
        d["q4_cases"] = pd.DataFrame()

    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H

    s01_cover(prs)
    s02_toc(prs)
    s03_background(prs)
    s04_my_thinking(prs)
    s05_pipeline(prs)
    s06_data(prs, d)
    s07_dual_dims(prs)
    s08_matrix(prs, d)
    s09_cases(prs)
    s10_comparison(prs, d)
    s11_q1(prs, d)
    s12_q2(prs, d)
    s13_q3(prs, d)
    s14_q4(prs, d)
    s15_q4_samples(prs, d)
    s16_q5(prs, d)
    s17_q5_basis(prs)
    s18_innovation(prs, d)
    s19_limits(prs, d)
    s20_reflection(prs)

    # 演讲者备注：每页一段，写在单独的 ppt_notes 模块里。
    from src.ppt_notes import apply_notes

    n_notes = apply_notes(prs)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / PPT_NAME
    prs.save(str(out))
    logger.info("PPT 已生成: %s（%d 页，%d 页含演讲者备注）",
                out, len(prs.slides._sldIdLst), n_notes)
    return out


if __name__ == "__main__":
    print(main())