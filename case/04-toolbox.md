# 04 所用工具与命令

> 这一篇是操作手册。所有命令都在 Windows + Python 3.13.15 环境下实际执行过。

## 一、工具清单与选型理由

| 用途 | 工具 | 版本 | 为什么选它 |
|---|---|---|---|
| 语言 | Python | 3.13.15 | 数据分析生态最完整；本项目要求 3.10+ |
| 表格处理 | pandas | 3.1.0 | 12,828 行 × 十几列的变换，手写循环不现实 |
| 数值计算 | numpy | 2.5.4 | Z 标准化、tanh 压缩、相关系数 |
| 统计检验 | scipy | 1.18.1 | Spearman / Pearson 相关系数及显著性 |
| 中文分词 | jieba | 0.42.1 | 情感词典要按词匹配，不分词无法定位情感词 |
| 通用情感 | snownlp | 0.12.3 | 只用作**极端值回退**，不单独使用 |
| 相似度 | scikit-learn | 1.9.1 | 字符级 TF-IDF（`char_wb` 2—4 元）+ 余弦相似度，用于重复检测 |
| 绘图 | matplotlib | 3.11.2 | 18 张图表 |
| 绘图封装 | seaborn | 0.13.2 | 热力图、分布图更省代码 |
| HTTP | requests | 2.32.0 | 榜单抓取 |
| HTML 解析 | beautifulsoup4 + lxml | 4.13.3 / 6.1.3 | lxml 解析器比内置的快 |
| Word 生成 | python-docx | 1.2.0 | 55 页报告，含表格、图片、TOC 域 |
| PPT 生成 | python-pptx | 1.0.2 | 20 页汇报，含演讲者备注 |
| 图像处理 | Pillow | 10.0+ | 代码截图渲染与尺寸处理 |
| 测试 | pytest | 8.0+ | 111 个测试 |

**选型的一条原则：能用标准库就不引第三方，必须引就选最成熟的那个。**

比如相关系数本来可以自己写，但 Spearman 需要处理并列秩（ties），自己实现容易在边界情况出错，
用 scipy 一行解决。反之，像「读取 CSV」这种 pandas 一行的事，没必要为了它引更重的框架。

## 二、环境搭建

### 2.1 检查 Python 版本

```bash
python --version
```

要求 3.10+。低于这个版本，代码里用的 `dict[str, str]` 类型标注和 `X | None` 写法会报错。

### 2.2 建虚拟环境

```bash
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Windows CMD
python -m venv .venv
.venv\Scripts\activate.bat

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

激活后提示符前面会出现 `(.venv)`。

**为什么要建虚拟环境**：项目固定了 15 个依赖的具体版本（如 `pandas==3.1.0`），
装进系统 Python 会和其他项目冲突。虚拟环境让每个项目的依赖互不干扰。

### 2.3 装依赖

```bash
pip install -r requirements.txt
```

国内网络建议加镜像：

```bash
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

镜像报「找不到包」时换官方源：

```bash
pip install -r requirements.txt -i https://pypi.org/simple
```

### 2.4 验证装好了

```bash
python -c "import pandas,numpy,scipy,matplotlib,seaborn,sklearn,jieba,snownlp,docx,pptx,PIL;print('依赖齐全')"
```

能打印「依赖齐全」就说明没问题。

## 三、跑起来：三条命令

```bash
# 1. 全流程（14 个阶段）
python main.py

# 2. 测试（111 个）
python -m pytest tests/ -q

# 3. 看结果
ls outputs/reports/
```

`main.py` 的退出码：全部成功返回 `0`，有失败阶段返回 `1`。写批处理脚本时可以据此判断。

**不需要联网。** 原始数据已随仓库提供，程序默认复用。只有显式设置环境变量才会访问豆瓣。

## 四、单模块调试：最常用的技巧

改了一个参数想看效果，不要重跑整条流程。每个模块都有独立入口：

```bash
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
python -m src.ppt_generator           # 重新生成 PPT
```

运行后以 JSON 形式打印这一步的返回值，方便快速看数字对不对。

### 典型场景：调整被低估指数的权重

```bash
# 改 config.py 里的 WEIGHT_SENTIMENT_GAP 等三个值，然后：
python -m src.underrated_index        # 0.2 秒，立刻看到新排名
python -m src.recommendation
python -m src.visualization
python -m src.report_generator
python -m src.ppt_generator
```

如果不这样分步，每次都要等完整 36 秒，其中 25 秒花在跟本次改动无关的情感分析上。

> 注意：模块之间有依赖顺序。跳过前一步直接跑后一步，可能读到旧文件。
> 完整的依赖关系见 [03 关键步骤与操作顺序](03-workflow.md) 第五节的依赖表。

## 五、强制重新抓数据

默认复用 `data/raw/top250_raw.csv`。想重新抓榜单：

```bash
# Windows CMD
set DOUBAN_FORCE_REFETCH=1 && python main.py

# Windows PowerShell
$env:DOUBAN_FORCE_REFETCH="1"; python main.py

# macOS / Linux
DOUBAN_FORCE_REFETCH=1 python main.py
```

抓取参数在 `config.py`：

```python
REQUEST_DELAY: float = 2.0     # 页间延时（秒）
REQUEST_TIMEOUT: int = 25
REQUEST_RETRY: int = 3
```

`REQUEST_DELAY` 不要调小。2 秒的间隔是基本的礼貌，也降低被限流的概率。
十条页面合计多等 20 秒，比被封 IP 之后处理一堆麻烦更划算。

## 六、离线重建：改解析逻辑不用重抓

这是本项目最省时间的一条命令：

```bash
python -c "from src.acquisition import rebuild_raw_from_snapshots; \
           df = rebuild_raw_from_snapshots(); print(df.shape)"
```

它只读 `data/raw/html_snapshots/` 下的 10 个本地文件，**不访问网络**。

适用场景：改完 `parse_top250_page()` 的解析逻辑后，想验证效果。
用这条命令几秒钟出结果，比重新抓取（10 页 × 2 秒间隔 + 网络时间）快得多。

## 七、温度调节：日志级别

出问题时需要更多信息：

```bash
# Windows CMD
set DOUBAN_LOG_LEVEL=DEBUG && python main.py

# PowerShell
$env:DOUBAN_LOG_LEVEL="DEBUG"; python main.py

# macOS / Linux
DOUBAN_LOG_LEVEL=DEBUG python main.py
```

查日志：

```bash
tail -50 outputs/logs/pipeline.log      # 最后 50 行
grep ERROR outputs/logs/pipeline.log    # 只看报错
```

## 八、改参数：一个文件搞定

所有可调参数集中在 `config.py`，改完直接重跑对应模块，不用动代码逻辑。

### 8.1 封面信息

```python
COVER_INFO: dict[str, str] = {
    "课程名称": "Python 数据分析",
    "项目名称": "豆瓣电影 Top250 数据分析：评论质量识别与口碑价值挖掘",
    "姓名": "",        # ← 填这里
    "班级": "",
    "学号": "",
    "指导教师": "",
}
```

留空会显示成下划线。填完重跑：

```bash
python -m src.report_generator
```

### 8.2 一致性判定阈值

```python
CONSISTENCY_TOLERANT_GAP: float = 0.55        # 小于此值算「一致」
CONSISTENCY_SEVERE_GAP: float = 1.10          # 大于此值算「严重矛盾」
MIN_CONFIDENCE_FOR_CONSISTENCY: float = 0.25  # 置信度低于此值判「无法判定」
```

调小 `TOLERANT_GAP` → 判定更严，一致性比例下降、矛盾数上升。调大则相反。

改完重跑：

```bash
python -m src.consistency_check
python -m src.method_comparison
python -m src.mismatch_analysis
```

> 这两个阈值是在 300 条人工验证集上试出来的，改动会直接影响方法对比的 F1。改之前先记下原值。

### 8.3 被低估指数权重

```python
WEIGHT_SENTIMENT_GAP: float = 0.50   # 文本情感与评分的落差
WEIGHT_USEFUL: float = 0.30          # 评论有用性
WEIGHT_ATTENTION: float = 0.20       # 关注度（取负号）
```

三个数最好加起来等于 1。下面还有一组敏感性分析用的权重组合：

```python
WEIGHT_SENSITIVITY_GRID: list[tuple[float, float, float]] = [
    (0.50, 0.30, 0.20),  # 基准
    (0.70, 0.20, 0.10),  # 强化文本口碑差值
    (0.40, 0.40, 0.20),  # 强化评论有用性
    (0.34, 0.33, 0.33),  # 等权
    (0.60, 0.15, 0.25),  # 强化关注度惩罚
]
```

想加一组就往后追加一个三元组。至少保留 3 组，这是任务书的硬性要求。

### 8.4 推荐权重

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

**`rating` 不要调到 0.40 以上。** 评分权重一高，结果必然退化成「Top250 前五名」，
失去策划价值。这是实际踩过的坑。

### 8.5 随机种子

```python
RANDOM_SEED: int = 20261109
```

控制所有随机过程（分层抽样、重复样本抽检）。**不要随便改**——改了数字会变，报告里的结论也要跟着重算。

## 九、报错对照表

以下是实际遇到过的报错与处理方式。

### 装依赖阶段

| 报错 | 原因 | 解决 |
|---|---|---|
| `Could not find a version that satisfies the requirement scipy==1.18.1` | 镜像源版本滞后 | 换官方源 `-i https://pypi.org/simple`，或把固定版本改成 `>=` |
| `Microsoft Visual C++ 14.0 is required` | Windows 上 scipy 需要编译工具 | 用预编译 wheel：`pip install --only-binary :all: scipy` |

### 运行阶段

| 报错 | 原因 | 解决 |
|---|---|---|
| `ModuleNotFoundError: No module named 'src'` | 不在项目根目录下运行 | `cd` 到根目录再跑 `python main.py`，不能在 `src/` 里跑 |
| `KeyError: 'movie_id'` | 上游文件没生成或格式不对 | 按依赖顺序检查：`ls data/raw/top250_raw.csv data/processed/reviews_dual.csv`，缺哪个重跑哪个 |
| `PermissionError: [Errno 13]` | Word 或 PowerPoint 正开着这个文件 | 关掉再跑 |
| 图表中文显示成方框 | matplotlib 没找到中文字体 | 见下一节 |

### 数据阶段

| 现象 | 原因 | 解决 |
|---|---|---|
| 评论覆盖率远低于 56.4% | 文件名规则对不上，片名匹配失败 | 检查 `config.py` 的 `REVIEW_FILE_PREFIX` |
| 被低估指数前十全是 9.5 分以上 | R 的尺度出错，导致高分片 U 恒为负 | 确认 S 与 R 各自做了 Z 标准化 |
| Word 目录页码是空的 | TOC 是域，python-docx 无法计算页码 | 打开后 `Ctrl+A` → `F9` 更新 |
| PPT 打开提示「文件已损坏」 | 上次运行中途被打断，文件写了一半 | 删掉重新生成 |

## 十、中文字体：最容易被忽略的坑

图表里的中文显示成方框（豆腐块），是 matplotlib 没找到中文字体。

项目里 `config.py` 定义了一组候选字体：

```python
FONT_CANDIDATES: list[str] = [
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
python -c "import matplotlib; print(matplotlib.get_cachedir())"
# 删掉打印出来的目录，然后重新运行
```

**为什么用候选列表而不是指定一个字体**：项目要在不同机器上跑，硬编码一个字体名，
换台机器就崩。给一组候选，代码里逐次尝试，取第一个存在的。

## 十一、查结果：每个数字的出处

报告里所有数字都能在这些文件里找到，写报告或答辩被问「这个数从哪来的」时直接查：

| 想知道什么 | 查哪个文件 |
|---|---|
| 评论质量各类有多少条 | `outputs/tables/quality_distribution.csv` |
| 一致性矩阵（A/B 类 × 四个档位） | `outputs/tables/consistency_matrix.csv` |
| 基础法 vs 改进法的 P/R/F1 | `outputs/tables/method_comparison.csv` |
| Q1 描述统计与相关系数 | `q1_descriptive.csv`、`q1_correlation.csv` |
| Q2 年代×类型交叉表 | `q2_era_genre_crosstab.csv` |
| Q3 被低估指数全表 | `q3_underrated_full.csv` |
| Q3 前十名 | `q3_underrated_top10.csv` |
| Q3 五种权重下排名变化 | `q3_weight_sensitivity.csv` |
| Q4 20 条样本与复核结论 | `q4_mismatch_20cases.csv` |
| Q5 五部推荐及得分 | `q5_remake_recommendations.csv` |
| Q5 引用的市场事实 | `q5_market_facts.csv` |
| 各阶段耗时与状态 | `outputs/run_summary.json` |

用 pandas 快速查看：

```bash
python -c "import pandas as pd; print(pd.read_csv('outputs/tables/q3_underrated_top10.csv').to_string())"
```

## 十二、一页速查

```bash
# 环境
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 全流程
python main.py

# 测试
python -m pytest tests/ -q

# 单步（按依赖顺序）
python -m src.cleaning
python -m src.quality_classification
python -m src.sentiment
python -m src.consistency_check
python -m src.underrated_index
python -m src.report_generator

# 离线重建（改解析后验证）
python -c "from src.acquisition import rebuild_raw_from_snapshots; print(rebuild_raw_from_snapshots().shape)"

# 强制重抓
set DOUBAN_FORCE_REFETCH=1 && python main.py

# 查日志
tail -50 outputs/logs/pipeline.log
```

---

**上一篇**：[03 关键步骤与操作顺序](03-workflow.md)
**下一篇**：[05 遇到的问题及解决方案](05-problems.md) —— 八个真实踩过的坑。