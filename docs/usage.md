# 使用手册

本文讲怎么把这个项目跑起来、怎么改、出错了怎么办。
方法为什么这么设计，见 `docs/methodology.md`；字段口径见 `docs/data_dictionary.md`。本文只管操作。

---

## 目录

1. [五分钟跑起来](#一五分钟跑起来)
2. [环境准备（详细）](#二环境准备详细)
3. [两种运行方式](#三两种运行方式)
4. [分阶段说明：每一步在做什么](#四分阶段说明每一步在做什么)
5. [改配置：最常改的六个地方](#五改配置最常改的六个地方)
6. [看结果：文件都在哪](#六看结果文件都在哪)
7. [换数据：想用自己抓的数据怎么办](#七换数据想用自己抓的数据怎么办)
8. [常见问题与报错对照](#八常见问题与报错对照)
9. [交作业前的检查清单](#九交作业前的检查清单)

---

## 一、五分钟跑起来

已经装好 Python 的情况下，最短路径是三条命令：

```bash
cd E:/PycharmProjects/pythonProject/douban_top250
pip install -r requirements.txt
python main.py
```

跑完在 `outputs/reports/` 下会多出两个文件：

- `豆瓣电影Top250数据分析课程项目报告.docx`
- `豆瓣电影Top250数据分析课程汇报.pptx`

**总耗时约 40 秒到 1 分钟**（不含装依赖）。其中情感分析最慢（约 25 秒），因为它要逐条处理 12,828 条评论。

**不需要联网也能跑通**。原始数据已经随包提供（`data/raw/` 与 `data/external/`），程序默认复用。只有在你显式要求重新抓取时才会访问豆瓣。

---

## 二、环境准备（详细）

### 2.1 Python 版本

要求 **3.10 及以上**，本项目在 **3.13.15** 上实测通过。

检查版本：

```bash
python --version
```

### 2.2 建虚拟环境

不建议装在系统 Python 里。在项目目录下建一个独立环境：

**Windows（PowerShell）**

```powershell
cd E:/PycharmProjects/pythonProject/douban_top250
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows（CMD）**

```bat
cd /d E:\PycharmProjects\pythonProject\douban_top250
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux**

```bash
cd ~/path/to/douban_top250
python3 -m venv .venv
source .venv/bin/activate
```

激活后命令提示符前面会出现 `(.venv)`。之后所有 `python` 命令都指向这个环境。

> 如果你用 PyCharm 打开这个项目，可以在 `Settings → Project → Python Interpreter` 里直接选已有的 `.venv`，之后在 PyCharm 的 Terminal 里就自动激活了。

### 2.3 装依赖

```bash
pip install -r requirements.txt
```

国内网络建议加镜像，否则 scipy、scikit-learn 这些包会比较慢：

```bash
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

如果阿里云源出现「找不到包」，换成官方源试一次：

```bash
pip install -r requirements.txt -i https://pypi.org/simple
```

### 2.4 验证装好了

```bash
python -c "import pandas,numpy,scipy,matplotlib,seaborn,sklearn,jieba,snownlp,docx,pptx,PIL;print('依赖齐全')"
```

能打印「依赖齐全」就说明没问题。若报 `ModuleNotFoundError: xxx`，单独补装那一个：

```bash
pip install xxx -i https://mirrors.aliyun.com/pypi/simple/
```

### 2.5 一个容易被忽略的坑：中文字体

图表里的中文如果显示成方框（豆腐块），说明 matplotlib 没找到中文字体。

项目里 `config.py` 定义了一组候选字体：

```python
FONT_CANDIDATES = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
    "Source Han Sans CN", "WenQuanYi Zen Hei", "Arial Unicode MS",
]
```

Windows 一般自带「Microsoft YaHei」和「SimHei」，不会出问题。
Linux 服务器上通常一个都没有，需要装：

```bash
# Ubuntu / Debian
sudo apt install fonts-noto-cjk
# CentOS / RHEL
sudo yum install google-noto-sans-cjk-fonts
```

装完删掉 matplotlib 的字体缓存再跑：

```bash
python -c "import matplotlib;print(matplotlib.get_cachedir())"
# 删掉打印出来的目录，然后重新运行
```

---

## 三、两种运行方式

### 3.1 一次性跑完全流程（推荐）

```bash
python main.py
```

会依次执行 14 个阶段，终端最后打印一张摘要表：

```
====================================================================
运行摘要
====================================================================
  [成功] 01_数据采集                    0.0s
  [成功] 02_文本清洗                    3.8s
  [成功] 03_内容分级                    0.8s
  [成功] 04_情感分析                   24.6s
  [成功] 05_一致性判定                   0.4s
  ...
  [成功] 14_PPT报告                   0.4s
====================================================================
```

同时写入 `outputs/run_summary.json`，里面有每个阶段的耗时、返回值，失败时还有报错堆栈。

**退出码**：全部成功返回 `0`，有失败阶段返回 `1`。写批处理脚本时可以据此判断。

### 3.2 只跑某一个模块（调试用）

每个模块都有独立入口，可以直接执行：

```bash
python -m src.cleaning              # 只跑文本清洗
python -m src.sentiment             # 只跑情感分析
python -m src.underrated_index      # 只跑被低估指数
python -m src.visualization         # 只重画全部图表
python -m src.report_generator      # 只重新生成 Word
python -m src.ppt_generator         # 只重新生成 PPT
```

运行后会以 JSON 形式打印这一步的返回值，方便快速看数字对不对。

**改了一处想看效果时用这个**。比如调整了被低估指数的权重，只需要：

```bash
python -m src.underrated_index
python -m src.recommendation
python -m src.visualization
python -m src.report_generator
python -m src.ppt_generator
```

比整条重跑快得多。

> 注意：模块之间有依赖顺序。跳过前一步直接跑后一步可能读到旧文件。
> 完整的依赖关系见下一节。

---

## 四、分阶段说明：每一步在做什么

`main.py` 的 14 个阶段，以及每步的输入输出。

| 阶段 | 模块 | 读取 | 写出 | 失败会怎样 |
|---|---|---|---|---|
| 01 数据采集 | `acquisition` | 榜单页 / `data/external/` | `data/raw/top250_raw.csv`、`reviews_raw.csv` | **流程终止**（没有影片数据无法继续） |
| 02 文本清洗 | `cleaning` | `reviews_raw.csv` | `data/interim/`、`data/processed/reviews_clean.csv` | 后续全废 |
| 03 内容分级 | `quality_classification` | 清洗结果 | `reviews_labeled.csv` | 后续全废 |
| 04 情感分析 | `sentiment` | 分级结果 | `reviews_scored.csv` | 后续全废 |
| 05 一致性判定 | `consistency_check` | 分级 + 情感 | `reviews_dual.csv` | Q4 与指数受影响 |
| 06 方法对比 | `method_comparison` | 双维度结果 + 人工标注 | `method_comparison.csv` | 报告第四章缺数据 |
| 07 Q1/Q2 | `statistics` | `top250_raw.csv` | `q1_*.csv`、`q2_*.csv` | 第五、六章缺数据 |
| 08 Q3 | `underrated_index` | `reviews_dual.csv` | `q3_*.csv` | 第七章、第九章受影响 |
| 09 Q4 | `mismatch_analysis` + `mismatch_cases` | `reviews_scored.csv` | `q4_*.csv` | 第八章缺数据 |
| 10 Q5 | `recommendation` | Q3 结果 + 市场数据 | `q5_*.csv` | 第九章缺数据 |
| 11 图表 | `visualization` | 全部上表 | `outputs/figures/*.png` | 报告缺图 |
| 12 代码截图 | `code_screenshot` | `src/*.py` 源码 | `outputs/screenshots/*.png` | 附录缺图 |
| 13 Word | `report_generator` | 全部结果 | `outputs/reports/*.docx` | PPT 仍可生成 |
| 14 PPT | `ppt_generator` | 全部结果 + 备注 | `outputs/reports/*.pptx` | — |

**关键依赖链**：

```
01 → 02 → 03 → 04 → 05 → 06
                  ↓
                  08 → 10 → 11 → 13 → 14
                  ↓
                  09 ────────┘
07 ────────────────────────┘
```

也就是说：**改了 04 情感分析，05 之后全都要重跑**；只改 13 Word 的排版，重跑 13 就行。

---

## 五、改配置：最常改的六个地方

所有可调参数都在 `config.py`，改完直接重跑对应模块，不用动代码逻辑。

### 5.1 填封面信息（交作业必改）

`config.py` 第 156 行起：

```python
COVER_INFO: dict[str, str] = {
    "课程名称": "Python 数据分析",
    "项目名称": "豆瓣电影 Top250 数据分析：评论质量识别与口碑价值挖掘",
    "姓名": "",        # ← 填这里
    "班级": "",        # ← 填这里
    "学号": "",        # ← 填这里
    "指导教师": "",    # ← 填这里
}
```

留空会显示成下划线。填完重跑：

```bash
python -m src.report_generator
```

### 5.2 换评论数据的路径

如果你自己抓了一份评论，`config.py`：

```python
REVIEW_DIRNAME: str = "douban_top250_reviews"      # data/external/ 下的目录名
REVIEW_FILE_PREFIX: str = "douban_movie_xsk_1-5"   # 文件名要剥掉的前缀
```

这两个值决定了程序怎么从文件名还原片名。详细说明见 [第七节](#七换数据想用自己抓的数据怎么办)。

### 5.3 调一致性判定的松紧

```python
CONSISTENCY_TOLERANT_GAP: float = 0.55    # 小于此值算「一致」
CONSISTENCY_SEVERE_GAP: float = 1.10      # 大于此值算「严重矛盾」
MIN_CONFIDENCE_FOR_CONSISTENCY: float = 0.25  # 置信度低于此值判「无法判定」
```

**调小 `TOLERANT_GAP`**：判定更严，一致性比例下降、矛盾数上升。
**调大**：更宽松，更多评论被当一致。

改完重跑：

```bash
python -m src.consistency_check
python -m src.method_comparison
python -m src.mismatch_analysis
```

> 这两个阈值是在 300 条人工验证集上试出来的，改动会直接影响第四章的 F1。改之前先记下原来的数字。

### 5.4 调被低估指数的权重

```python
WEIGHT_SENTIMENT_GAP: float = 0.50   # 文本情感与评分的落差
WEIGHT_USEFUL: float = 0.30          # 评论有用性
WEIGHT_ATTENTION: float = 0.20       # 关注度（取负号）
```

三个数最好加起来等于 1。

下面还有一组敏感性分析用的权重组合：

```python
WEIGHT_SENSITIVITY_GRID: list[tuple[float, float, float]] = [
    (0.50, 0.30, 0.20),  # 基准
    (0.70, 0.20, 0.10),  # 强化文本口碑差值
    (0.40, 0.40, 0.20),  # 强化评论有用性
    (0.34, 0.33, 0.33),  # 等权
    (0.60, 0.15, 0.25),  # 强化关注度惩罚
]
```

想加一组就往后追加一个三元组，`q3_weight_sensitivity.csv` 会多一行。
**至少要保留 3 组**，这是任务书的硬性要求。

### 5.5 调推荐权重

```python
REC_WEIGHTS: dict[str, float] = {
    "rating": 0.15,     # 口碑基础
    "index": 0.25,      # 被低估指数
    "sentiment": 0.15,  # 文本情感强度
    "attention": 0.08,  # 评分人数
    "reviews": 0.07,    # 有效评论数
    "era": 0.10,        # 年代稀缺性
    "market": 0.20,     # 类型市场热度
}
```

⚠️ **`rating` 不要调到 0.40 以上**。评分权重一高，结果必然退化成「Top250 前五名」，失去策划价值。这是我在项目里踩过的坑。

约束条件也在附近：

```python
REC_MIN_YEARS_SINCE_RELEASE: int = 8   # 重映需已上映满 8 年
REC_MAX_PER_GENRE_ROUND1: int = 1      # 每类型最多 1 部
REC_MAX_PER_DECADE: int = 2            # 同十年最多 2 部
```

### 5.6 改随机种子

```python
RANDOM_SEED: int = 20261109
```

这个种子控制所有随机过程的可复现性（分层抽样、重复样本抽检等）。**不要随便改**——改了之后数字会变，报告里的结论也要跟着重算。

⚠️ **关于 `manual_validation.csv` 的重要说明**

这个文件是 **300 条人工标注**，是方法对比实验的唯一基准。

**它没有自动生成脚本**。项目里所有代码只「读取」这个文件，不「生成」它 —— 因为人工标注必须由人逐条读原文完成，不能由程序代劳。文件丢失就意味着：

- `method_comparison` 阶段会失败（读不到基准）
- 报告第四章、PPT 第 10 页的数字全部缺失

**所以这个文件千万别删、别覆盖**。项目里已经随包放了一份备份：

```
data/processed/manual_validation.csv           ← 正在用的
data/processed/manual_validation.backup.csv    ← 备份，内容相同
```

如果误删了正在用的那份，从备份恢复即可：

```bash
cp data/processed/manual_validation.backup.csv data/processed/manual_validation.csv
```

如果真丢了，只能重新人工标注，没有捷径。原文件结构（12 列，300 行）：

| 列名 | 含义 |
|---|---|
| `sample_no` | 样本序号 1—300 |
| `review_id` | 关联 `reviews_dual.csv` |
| `movie_name` | 片名 |
| `rating` | 星级 |
| `quality_label` | 规则判定的 A/B/C/D/E |
| `quality_reason` | 规则给出的判定理由 |
| `text_length` | 文本长度 |
| `clean_text` | 清洗后文本 |
| `human_label` | **人工判定的内容质量**（需人填） |
| `human_sentiment` | **人工判定的情感倾向**（需人填） |
| `human_note` | 人工备注（为什么不一致等） |
| `annotation_source` | 标注来源，本项目全部为人工阅读 |

重新做的话，从 `reviews_dual.csv` 分层抽 300 条（按质量类别、星级、文本长度分层，覆盖尽量多的影片），再逐条读原文填后四列。

> 抽样本身用 `RANDOM_SEED` 固定即可复现，但**标注内容无法复现**——这是这个项目里唯一不能靠代码重跑得到的东西。

---

## 六、看结果：文件都在哪

### 6.1 交付物（要交的就这三个）

```
outputs/reports/
├── 豆瓣电影Top250数据分析课程项目报告.docx   ← 55 页，11 章
└── 豆瓣电影Top250数据分析课程汇报.pptx        ← 20 页，含演讲者备注
```

ZIP 包在上层目录：`E:/PycharmProjects/pythonProject/douban_top250_课程项目交付.zip`

### 6.2 中间产物（写报告时查数字用）

| 目录 | 内容 | 数量 |
|---|---|---|
| `outputs/figures/` | 图表 PNG | 18 张 |
| `outputs/tables/` | 统计表 CSV | 35 个 |
| `outputs/screenshots/` | 核心代码截图 | 10 张 |
| `outputs/logs/pipeline.log` | 运行日志 | 追加写 |
| `outputs/run_summary.json` | 各阶段状态与耗时 | 每次覆盖 |

### 6.3 常查的几个表

**报告里所有数字都能在这些文件里找到出处**，写报告或答辩被问「这个数从哪来的」时直接查：

| 想知道什么 | 查哪个文件 |
|---|---|
| 评论质量各类有多少条 | `quality_distribution.csv` |
| 一致性矩阵（A/B 类 × 四个档位） | `consistency_matrix.csv` |
| 基础法 vs 改进法的 P/R/F1 | `method_comparison.csv` |
| Q1 的描述统计与相关系数 | `q1_descriptive.csv`、`q1_correlation.csv` |
| Q2 年代×类型交叉表 | `q2_era_genre_crosstab.csv` |
| Q3 被低估指数全表 | `q3_underrated_full.csv` |
| Q3 前十名 | `q3_underrated_top10.csv` |
| Q3 五种权重下的排名变化 | `q3_weight_sensitivity.csv` |
| Q4 20 条样本与复核结论 | `q4_mismatch_20cases.csv` |
| Q5 五部推荐及得分 | `q5_remake_recommendations.csv` |
| Q5 引用的市场事实（带来源日期） | `q5_market_facts.csv` |

用 Excel 直接打开就能看，或者用 pandas：

```bash
python -c "import pandas as pd; print(pd.read_csv('outputs/tables/q3_underrated_top10.csv').to_string())"
```

### 6.4 看日志

运行过程中的每一步都写在 `outputs/logs/pipeline.log`，出了奇怪的问题先看它：

```bash
tail -50 outputs/logs/pipeline.log          # 最后 50 行
grep ERROR outputs/logs/pipeline.log        # 只看报错
```

日志级别可以调：

```bash
# Windows CMD
set DOUBAN_LOG_LEVEL=DEBUG && python main.py
# PowerShell
$env:DOUBAN_LOG_LEVEL="DEBUG"; python main.py
# macOS / Linux
DOUBAN_LOG_LEVEL=DEBUG python main.py
```

---

## 七、换数据：想用自己抓的数据怎么办

这部分需要你了解项目对文件名的约定。

### 7.1 换榜单数据

程序会优先读 `data/raw/top250_raw.csv`。想强制重新抓：

```bash
# Windows CMD
set DOUBAN_FORCE_REFETCH=1 && python main.py
# PowerShell
$env:DOUBAN_FORCE_REFETCH="1"; python main.py
# macOS / Linux
DOUBAN_FORCE_REFETCH=1 python main.py
```

抓取参数在 `config.py`：

```python
REQUEST_DELAY: float = 2.0     # 页间延时，别调太小，对站点不礼貌也容易被限
REQUEST_TIMEOUT: int = 25
REQUEST_RETRY: int = 3
```

原始 HTML 会存到 `data/raw/html_snapshots/`。**即使后面解析逻辑改了也不需要重抓**——可以直接从快照离线重建：

```bash
python -c "from src.acquisition import rebuild_raw_from_snapshots; df=rebuild_raw_from_snapshots(); print(df.shape)"
```

这条命令不访问网络，只读本地快照，改完 `parse_top250_page()` 的解析逻辑后用它验证效果，几秒钟就能看到结果。

### 7.2 换评论数据

评论数据放在 `data/external/douban_top250_reviews/` 下，**一个影片一个 CSV**。

程序靠文件名还原片名，规则是：

```
文件名 = REVIEW_FILE_PREFIX + 片名 + ".csv"
```

比如 `douban_movie_xsk_1-5活着.csv` → 剥掉前缀 → `活着` → 去跟榜单里的片名做匹配。

⚠️ **如果你自己抓评论，需要注意三点**：

1. **文件名必须能还原成片名**。如果你的前缀不同，改 `config.py` 的 `REVIEW_FILE_PREFIX`。
2. **CSV 的列名必须是这七个**（顺序不能变，程序按列名取值）：
   `time, uname, comment, star, title, support, sentiment_score`
   对应含义是：评论时间、用户名、评论文本、星级、评论标题、有用数、数据集自带的情感分。
   列错位会导致整体读错——本项目就遇到过一个文件表头残缺、255 条记录全错位的情况。
3. **片名匹配是宽松匹配**（去掉尾部标点、空格），但「肖申克的救赎」和「肖申克的救赎 The Shawshank Redemption」算不同片名。对不上就会被判为未匹配。

匹配结果会写在 `outputs/tables/data_review_coverage.csv`，字段是 `movie_id, title, rank, n_reviews, has_reviews`。**跑完先看这个**：

```bash
python -c "import pandas as pd; d=pd.read_csv('outputs/tables/data_review_coverage.csv'); print(d[~d['has_reviews']].head(20).to_string())"
```

如果大量影片的 `n_reviews` 是 0，说明文件名规则对不上，检查前缀。

### 7.3 更新市场数据（影响 Q5）

Q5 的类型热度来自公开报道，存在 `src/market_context.py` 里，每条都带来源和日期。

**这块最好不要凭空改**。如果找到了更新的公开数据，改的时候顺手把来源和发布日期一起写进去，格式照现有条目：

```python
{
    "事实": "2025 年为中国影史动画电影票房最高年",
    "来源": "国家电影局 / 央视网",
    "日期": "2026-01-01",
    ...
}
```

改完重跑：

```bash
python -m src.recommendation
python -m src.visualization
```

---

## 八、常见问题与报错对照

### 8.1 装依赖阶段

**`ERROR: Could not find a version that satisfies the requirement scipy==1.18.1`**

镜像是旧的，换官方源，或者把 `requirements.txt` 里的固定版本改成 `>=`：

```bash
pip install -r requirements.txt -i https://pypi.org/simple
```

**`Microsoft Visual C++ 14.0 is required`**（Windows 装 scipy 时）

装 Microsoft C++ Build Tools，或者直接用预编译 wheel：

```bash
pip install --only-binary :all: scipy
```

### 8.2 运行阶段

**`ModuleNotFoundError: No module named 'src'`**

没在项目根目录下运行。必须：

```bash
cd E:/PycharmProjects/pythonProject/douban_top250
python main.py
```

不能在 `src/` 目录里运行 `python main.py`。

**`KeyError: 'movie_id'` 或类似字段缺失**

上游文件没生成或格式不对。按依赖顺序检查：

```bash
ls data/raw/top250_raw.csv data/processed/reviews_dual.csv outputs/tables/q3_underrated_full.csv
```

缺哪个就从对应的阶段重跑。

**图表中文变成方框**

见 [2.5 中文字体](#25-一个容易被忽略的坑中文字体)。

**Word 目录页码是空的，显示「（在 Word 中按 F9 更新）」**

这是设计如此。目录用 Word 域实现，python-docx 无法计算页码。打开文档后：

1. `Ctrl + A` 全选
2. 按 `F9`
3. 选「只更新页码」或「更新整个目录」

**生成的 PPT 打开提示「文件已损坏」**

一般是上次运行中途被打断，文件写了一半。删掉重新生成：

```bash
rm outputs/reports/*.pptx
python -m src.ppt_generator
```

**`PermissionError: [Errno 13] Permission denied`**

Word 或 PowerPoint 正开着这个文件，程序写不进去。关掉再跑。

### 8.3 数据阶段

**封面姓名是空的**

`config.py` 的 `COVER_INFO` 没填，见 [5.1](#51-填封面信息交作业必改)。

**评论覆盖率特别低（远低于 56.4%）**

文件名规则对不上，见 [7.2](#72-换评论数据)。

**被低估指数前十名全是 9.5 分以上**

说明 R 的尺度出了问题。第一版确实会这样（9.5 分映射到 +0.9，而文本情感均值只有 0.3 左右，导致高分片 U 恒为负）。当前版本已改为 S 与 R 各自 Z 标准化。如果你改动了 `underrated_index.py` 的标准化部分，检查这里。

**Q4 的 20 条样本不足 20 条**

`mismatch_cases.py` 里按「片名 + 星级 + 文本前缀」定位具体评论。如果评论数据换了，这些定位会失效。运行后看输出里的 `missing` 字段，会列出哪几条没找到。

---

## 九、交作业前的检查清单

按顺序过一遍，全打勾就可以交了。

### 9.1 内容

- [ ] `config.py` 的姓名、班级、学号、指导教师已填写
- [ ] 重新生成了 Word 和 PPT（`python main.py`）
- [ ] 报告目录已更新（打开 Word 按 `Ctrl+A` → `F9`）
- [ ] 第二章「我原本以为…后来发现…」的叙述与实际经历一致
- [ ] 第十一章人机协同反思是自己的话，不是模板

### 9.2 数字

- [ ] 报告里的数字与 `outputs/tables/` 下的 CSV 一致
- [ ] 手动抽查 3 个数字（比如 A 类评论数、F1、被低估指数第一名）
- [ ] 如果改过权重或阈值，报告里的文字描述也跟着改了

### 9.3 文件

- [ ] `python main.py` 14 个阶段全部「成功」
- [ ] `python -m pytest tests/ -q` 全部通过
- [ ] `outputs/reports/` 下两个文件都能正常打开
- [ ] Word 页数、表格数、图片数看着正常（当前是 55 页 / 39 表 / 28 图）
- [ ] PPT 20 页，且**每页都有演讲者备注**（在 PowerPoint 里点「视图 → 备注页」看）

### 9.4 打包

```bash
cd E:/PycharmProjects/pythonProject
# 用系统的压缩工具把 douban_top250 整个目录压成 zip
```

打包时**可以排除**这些（体积大且不影响运行）：

- `__pycache__/`
- `.pytest_cache/`
- `outputs/reports/preview/`（预览图，临时产物）

**不要排除** `data/` 目录。原始数据是交付要求的一部分，而且没有它别人跑不起来。

---

## 附录：一页速查

```bash
# 装环境
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 全流程
python main.py

# 单步调试（按依赖顺序）
python -m src.acquisition             # 数据采集（有缓存时不联网）
python -m src.cleaning                # 文本清洗
python -m src.quality_classification  # 内容有效性分级
python -m src.sentiment               # 情感分析（最慢，约 25 秒）
python -m src.consistency_check       # 星级一致性判定
python -m src.method_comparison       # 方法对比实验
python -m src.statistics              # Q1 / Q2
python -m src.underrated_index        # Q3 被低估指数
python -m src.mismatch_analysis       # Q4 不一致统计
python -m src.mismatch_cases          # Q4 最终 20 条样本
python -m src.recommendation          # Q5 重映推荐
python -m src.visualization           # 重画 18 张图
python -m src.code_screenshot         # 重渲染 10 张代码截图
python -m src.report_generator        # 重新生成 Word
python -m src.ppt_generator           # 重新生成 PPT（含演讲者备注）

# 测试
python -m pytest tests/ -q

# 强制重抓
set DOUBAN_FORCE_REFETCH=1 && python main.py

# 看日志
tail -50 outputs/logs/pipeline.log
```

**改配置只需动一个文件**：`config.py`。
**所有结果都能复算**：没有手工填的数字，全部从 `outputs/tables/` 读取。
**跑不通先看**：`outputs/logs/pipeline.log`。