"""
src/code_screenshot.py
======================
把核心函数源码渲染成「代码截图」图片，用于 Word 报告附件。

为什么要单独生成截图
--------------------
课程报告要求附件给出核心代码截图并标注函数用途。直接截屏既不稳定也无法
复现，本模块用 Pillow 以等宽字体绘制带行号、语法着色的代码图，做到：
1. 每次运行结果一致（可复现）；
2. 只截取指定函数，不含无意义的 print 与 import 噪声；
3. 图片顶部标注函数名与用途，便于正文对照。
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import BASE_DIR, SCREENSHOT_DIR
from src.utils import get_logger

logger = get_logger("screenshot")

# 配色（浅色主题，适合打印）
BG = (252, 252, 252)
GUTTER_BG = (240, 242, 245)
LINE_NO = (150, 155, 165)
TEXT = (33, 37, 41)
KEYWORD = (175, 55, 145)
STRING = (30, 130, 76)
COMMENT = (120, 130, 140)
FUNC = (40, 90, 175)
BUILTIN = (160, 90, 30)

# 需要高亮的 Python 关键字
KEYWORDS = {
    "def", "class", "return", "if", "elif", "else", "for", "while", "in",
    "not", "and", "or", "import", "from", "as", "with", "try", "except",
    "finally", "raise", "pass", "break", "continue", "lambda", "yield",
    "assert", "global", "None", "True", "False", "is", "del",
}

# 常见内置函数与类型
BUILTINS = {
    "len", "range", "float", "int", "str", "list", "dict", "set", "tuple",
    "sum", "min", "max", "round", "abs", "print", "sorted", "enumerate",
    "zip", "any", "all", "isinstance", "getattr", "hasattr", "open",
}


def _find_font(size: int) -> ImageFont.FreeTypeFont:
    """
    查找可用于渲染代码的字体，要求同时支持中文与等宽西文。

    注意：Consolas、Courier 等纯西文等宽字体不含中文字形，
    直接渲染中文注释会得到方块。因此优先选用「等宽中文字体」，
    如 Sarasa Mono、Noto Sans Mono CJK，其次回退到微软雅黑
    （非等宽但中文可读），最后才是纯西文等宽字体。

    参数:
        size: 字号。

    返回:
        PIL 字体对象。
    """
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",          # 微软雅黑：中文清晰，西文非等宽
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",        # 黑体
        r"C:\Windows\Fonts\simsun.ttc",        # 宋体
        r"C:\Windows\Fonts\consola.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    logger.warning("未找到可用字体，代码截图将使用默认字体（中文可能异常）")
    return ImageFont.load_default()


def _measure(font: ImageFont.FreeTypeFont, text: str) -> float:
    """
    测量文本宽度，做中英文混排的近似修正。

    参数:
        font: 字体对象。
        text: 待测文本。

    返回:
        像素宽度。
    """
    return font.getlength(text)


def _find_cjk_font(size: int) -> ImageFont.FreeTypeFont:
    """
    查找可用的中文字体，用于渲染标题。

    参数:
        size: 字号。

    返回:
        PIL 字体对象。
    """
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _tokenize_line(line: str) -> list[tuple[str, tuple[int, int, int]]]:
    """
    对单行代码做简单的语法着色切分。

    只处理字符串、注释、关键字与内置函数四类，够用且不会误伤。

    参数:
        line: 单行代码。

    返回:
        (文本片段, 颜色) 列表。
    """
    segments: list[tuple[str, tuple[int, int, int]]] = []

    # 整行注释
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return [(line, COMMENT)]

    buf = ""
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]

        # 行内注释
        if ch == "#":
            if buf:
                segments.extend(_split_words(buf))
                buf = ""
            segments.append((line[i:], COMMENT))
            return segments

        # 字符串
        if ch in ('"', "'"):
            if buf:
                segments.extend(_split_words(buf))
                buf = ""
            quote = ch
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == quote:
                    j += 1
                    break
                j += 1
            segments.append((line[i:j], STRING))
            i = j
            continue

        buf += ch
        i += 1

    if buf:
        segments.extend(_split_words(buf))
    return segments


def _split_words(chunk: str) -> list[tuple[str, tuple[int, int, int]]]:
    """
    把不含字符串与注释的代码片段按标识符切分并着色。

    参数:
        chunk: 代码片段。

    返回:
        (文本, 颜色) 列表。
    """
    import re

    out: list[tuple[str, tuple[int, int, int]]] = []
    for token in re.findall(r"\w+|\W+", chunk):
        if token in KEYWORDS:
            out.append((token, KEYWORD))
        elif token in BUILTINS:
            out.append((token, BUILTIN))
        elif token and token[0].isupper() and token.replace("_", "").isalnum():
            out.append((token, FUNC))
        else:
            out.append((token, TEXT))
    return out


def render_function(
    module_rel_path: str,
    func_name: str,
    title: str,
    purpose: str,
    output_name: str,
    max_lines: int = 46,
) -> Path:
    """
    把指定函数的源码渲染为代码截图。

    参数:
        module_rel_path: 模块相对项目根目录的路径，如 "src/cleaning.py"。
        func_name: 函数名；传空字符串表示渲染整个模块的前若干行。
        title: 截图标题，如「clean_text —— 文本清洗」。
        purpose: 功能说明，显示在标题下方。
        output_name: 输出文件名（不含路径）。
        max_lines: 最多渲染的行数，超出部分以省略号表示。

    返回:
        生成的图片路径。
    """
    src_path = BASE_DIR / module_rel_path
    if not src_path.exists():
        raise FileNotFoundError(f"未找到模块: {src_path}")

    source = src_path.read_text(encoding="utf-8")

    if func_name:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ValueError(f"模块语法错误，无法解析: {exc}") from exc

        lines = source.splitlines()
        target = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                target = node
                break

        if target is None:
            raise ValueError(f"模块 {module_rel_path} 中未找到函数 {func_name}")

        start = target.lineno - 1
        end = getattr(target, "end_lineno", start + 40)
        code_lines = lines[start:end]
    else:
        code_lines = source.splitlines()[:max_lines]

    truncated = len(code_lines) > max_lines
    if truncated:
        code_lines = code_lines[:max_lines]

    # --- 版面参数 ------------------------------------------------------
    font = _find_font(15)
    title_font = _find_cjk_font(19)
    sub_font = _find_cjk_font(14)

    char_w = _measure(font, "M")
    line_h = 24
    pad = 22
    gutter_w = int(char_w * 5)

    max_w = max((sum(_measure(font, s) for s, _ in _tokenize_line(l)) for l in code_lines),
                default=400)
    body_w = int(max_w) + 24
    width = max(900, gutter_w + body_w + pad * 2)
    header_h = 74
    height = header_h + line_h * len(code_lines) + pad * 2 + (24 if truncated else 0)

    img = Image.new("RGB", (int(width), int(height)), BG)
    draw = ImageDraw.Draw(img)

    # --- 标题区 --------------------------------------------------------
    draw.rectangle([0, 0, width, header_h - 8], fill=(248, 249, 251))
    draw.line([(0, header_h - 8), (width, header_h - 8)], fill=(220, 224, 230), width=1)
    draw.text((pad, 14), title, font=title_font, fill=(25, 35, 60))
    draw.text((pad, 42), purpose, font=sub_font, fill=(110, 118, 130))

    # --- 行号区 --------------------------------------------------------
    draw.rectangle([0, header_h, gutter_w, height], fill=GUTTER_BG)
    draw.line([(gutter_w, header_h), (gutter_w, height)], fill=(220, 224, 230), width=1)

    y = header_h + pad - 6
    for idx, line in enumerate(code_lines, start=1):
        # 行号
        no = str(idx)
        draw.text(
            (gutter_w - 10 - _measure(font, no), y),
            no, font=font, fill=LINE_NO,
        )
        # 代码
        x = gutter_w + 12
        for seg, color in _tokenize_line(line):
            draw.text((x, y), seg, font=font, fill=color)
            x += _measure(font, seg)
        y += line_h

    if truncated:
        draw.text(
            (gutter_w + 12, y + 2),
            f"…… 以下省略（完整实现见 {module_rel_path}）",
            font=sub_font, fill=(150, 155, 165),
        )

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SCREENSHOT_DIR / output_name
    img.save(out)
    logger.info("代码截图已生成: %s（%d 行）", out.name, len(code_lines))
    return out


# 需要截图的函数清单：(模块, 函数名, 标题, 用途, 输出文件名)
SCREENSHOT_SPECS: list[tuple[str, str, str, str, str]] = [
    ("src/acquisition.py", "parse_top250_page", "parse_top250_page —— 榜单页解析",
     "作用：把单页 HTML 解析为结构化电影记录，是数据采集的入口", "code_01_parse_top250.png"),
    ("src/cleaning.py", "clean_text", "clean_text —— 文本清洗",
     "作用：去 HTML 标签与 URL、统一空白，保留标点以维持情绪信息", "code_02_clean_text.png"),
    ("src/cleaning.py", "mark_duplicates", "mark_duplicates —— 重复检测",
     "作用：同片内用字符级 TF-IDF 余弦相似度标记重复与高度相似副本", "code_03_mark_duplicates.png"),
    ("src/quality_classification.py", "classify_by_rules", "classify_by_rules —— 内容有效性分级",
     "作用：按信息密度分档判定 A/B/C/E 四类，是不因短而删的核心逻辑", "code_04_classify.png"),
    ("src/consistency_check.py", "label_consistency", "label_consistency —— 星级一致性判定",
     "作用：第二维度，用星级归一值与情感分之差判定四级一致性", "code_05_consistency.png"),
    ("src/sentiment.py", "analyze_text", "analyze_text —— 情感分析",
     "作用：词典 + 否定/程度/转折规则，未命中时回退朴素贝叶斯极端值判定",
     "code_06_sentiment.png"),
    ("src/method_comparison.py", "run_method_comparison", "run_method_comparison —— 方法对比",
     "作用：在人工验证集上比较基础清洗法与改进清洗法的 P/R/F1", "code_07_comparison.png"),
    ("src/underrated_index.py", "compute_index", "compute_index —— 被低估指数",
     "作用：按权重组合计算 U，含 S/R 标准化与分项贡献分解", "code_08_index.png"),
    ("src/recommendation.py", "select_five", "select_five —— 多样性约束选片",
     "作用：两轮贪心选取，保证类型与年代分散", "code_09_select_five.png"),
    ("src/visualization.py", "fig_method_comparison", "fig_method_comparison —— 方法对比图",
     "作用：把两套方法的关键指标可视化，如实呈现召回率的略降", "code_10_viz.png"),
]


def run_all() -> list[str]:
    """
    批量生成全部代码截图。

    返回:
        已生成文件的路径列表。
    """
    paths: list[str] = []
    for module, func, title, purpose, out in SCREENSHOT_SPECS:
        try:
            paths.append(str(render_function(module, func, title, purpose, out)))
        except Exception as exc:
            logger.error("生成截图失败 %s.%s: %s", module, func, exc)
    logger.info("代码截图完成：%d / %d", len(paths), len(SCREENSHOT_SPECS))
    return paths


if __name__ == "__main__":
    import json

    _result = run_all()
    print(json.dumps(_result, ensure_ascii=False, indent=2))
