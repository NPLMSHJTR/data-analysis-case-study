# 数据字典

本文档定义项目中所有数据文件的字段、类型与口径。所有口径在分析开始前确定，过程中未调整。

---

## 一、电影表 `data/raw/top250_raw.csv`

| 字段 | 类型 | 含义 | 来源 | 完整率 |
|---|---|---|---|---|
| `movie_id` | string | 豆瓣影片唯一标识 | 榜单页链接 | 100% |
| `title` | string | 中文片名 | 榜单页 | 100% |
| `original_title` | string | 外文原名 | 榜单页 | 89.2% |
| `other_titles` | string | 港台译名等其他片名 | 榜单页 | 99.6% |
| `rank` | int | Top250 排名 1—250 | 榜单页 | 100% |
| `douban_rating` | float | 豆瓣评分（10 分制） | 榜单页 | 100% |
| `rating_count` | int | **评分人数**（参与打分人数，非观影人数） | 榜单页 | 100% |
| `release_year` | int | 上映年份 | 榜单页信息段 | 100% |
| `country` | string | 主国家/地区（多地区取首个） | 榜单页信息段 | 100% |
| `country_all` | string | 完整国家/地区串 | 榜单页信息段 | 100% |
| `director` | string | 导演署名（含外文名） | 榜单页信息段 | 100% |
| `actors` | string | 主演署名 | 榜单页信息段 | 96.0% |
| `genres` | string | 类型串（空格分隔） | 榜单页信息段 | 100% |
| `runtime` | string | 片长 | **未采集**（详情页需登录） | 0% |
| `collect_time` | string | 采集时间 | 程序写入 | 100% |
| `source` | string | 来源标识 | 程序写入 | 100% |

### 缺失说明

- `original_title` 缺失 27 条：纯华语片页面本身无外文名，非采集失败
- `actors` 缺失 10 条：豆瓣把主演压缩为「主…」，属页面固有缺陷
- `runtime` 全空：主动放弃采集，因片长不参与任何研究问题

### 口径

**`rating_count` 不是观影人数**。豆瓣标注为「评价人数」，指参与打分的用户数。
本报告全文使用「评分人数」。

---

## 二、评论原始表 `data/raw/reviews_raw.csv`

| 字段 | 类型 | 含义 | 备注 |
|---|---|---|---|
| `review_id` | string | 评论唯一标识 | 格式 `{movie_id}_{序号}` |
| `movie_id` | string | 关联影片 ID | 未匹配到榜单的为空 |
| `movie_name` | string | 影片中文名 | — |
| `rating` | int | 用户星级 1—5 | 原始字段 `star` |
| `review_text` | string | 原始评论文本 | 仅去首尾空白 |
| `review_time` | string | 评论发表时间 | `YYYY-MM-DD HH:MM:SS` |
| `useful_count` | int | 评论有用数 | 原始字段 `support` |
| `author_id_hash` | string | 用户标识 MD5 前 16 位 | **已脱敏** |
| `dataset_sentiment_score` | float | 数据集作者的第三方情感分 | **本项目不采用** |
| `source` | string | 来源标识 | — |

---

## 三、标签表 `data/processed/reviews_labeled.csv`

在原始表基础上新增：

| 字段 | 类型 | 含义 |
|---|---|---|
| `clean_text` | string | 清洗后文本 |
| `text_length` | int | 清洗后字符数 |
| `struct_ok` | bool | 字段结构是否正常（时间列能否解析） |
| `is_duplicate` | bool | 是否为同片重复/高度相似副本 |
| `is_truncated` | bool | 是否超长被截断 |
| `quality_label` | string | 第一维度标签 `A/B/C/D/E/X` |
| `quality_reason` | string | 判定理由（中文） |
| `include_sentiment` | bool | 是否进整体情感统计（A 或 B） |
| `include_content` | bool | 是否进内容分析（仅 A） |

### 标签含义

| 标签 | 名称 | 进情感统计 | 进内容分析 |
|---|---|---|---|
| A | 有效评论 | 是 | 是 |
| B | 低信息量 | 是 | 否 |
| C | 无关评论 | 否 | 否 |
| D | 疑似异常 | 否 | 否 |
| E | 待人工判断 | 否 | 否 |
| X | 剔除 | 否 | 否 |

> **B 类不等于无效**。「烂片」表达明确负面态度，保留在整体情感统计中，
> 但不进入需要信息密度的内容分析。

---

## 四、双维度结果表 `data/processed/reviews_dual.csv`

在标签表基础上新增：

| 字段 | 类型 | 含义 | 取值 |
|---|---|---|---|
| `sentiment_score` | float | 情感分 | [−1, 1] |
| `sentiment_label` | string | 情感标签 | `pos/neu/neg` |
| `sentiment_confidence` | float | 判定置信度 | [0, 1] |
| `sentiment_method` | string | 判定方法 | `lexicon` / `fallback` / `none` |
| `sentiment_hits` | string | 命中词（前缀「否定」表示反转） | — |
| `star_norm` | float | 星级归一值 | [−1, 1] |
| `gap` | float | star_norm − sentiment_score | [−2, 2] |
| `abs_gap` | float | \|gap\| | [0, 2] |
| `consistency` | string | **第二维度标签** | 一致/轻度不一致/严重矛盾/无法判定 |
| `consistency_reason` | string | 判定说明 | — |
| `disposition` | string | 最终处置 | 见下表 |

### 处置取值

| disposition | 含义 | 进入哪类分析 |
|---|---|---|
| `content` | A 类且一致或轻度不一致 | 内容分析 + 情感统计 |
| `sentiment` | B 类，或 A 类但置信度不足 | 仅情感统计 |
| `mismatch_only` | A 类且严重矛盾 | 仅矛盾样本表 |
| `manual` | A 类但一致性无法判定 | 待人工判断 |
| `excluded` | C/D/E/X | 完全排除 |

---

## 五、人工验证表 `data/processed/manual_validation.csv`

| 字段 | 类型 | 含义 |
|---|---|---|
| `sample_no` | int | 样本序号 1—300 |
| `review_id` | string | 关联评论 |
| `movie_name` | string | 影片名 |
| `rating` | int | 星级 |
| `quality_label` | string | 模型预测标签 |
| `quality_reason` | string | 模型判定理由 |
| `text_length` | int | 文本长度 |
| `clean_text` | string | 清洗后文本 |
| `human_label` | string | **人工标注的内容标签** |
| `human_sentiment` | string | **人工标注的情感标签** |
| `human_note` | string | 备注（本项目未使用） |
| `annotation_source` | string | 标注方式说明 |

> 人工标注由研究者逐条阅读原文完成，标注时未查看模型输出。
> **注意**：本表没有独立的「一致性」列，因此一致性判定的准确率未被直接验证。
> 这是本项目最大的方法缺口，已在报告第十章说明。

---

## 六、统计表 `outputs/tables/*.csv`

| 文件 | 内容 | 对应章节 |
|---|---|---|
| `data_review_coverage.csv` | 每部影片的评论覆盖数 | 第三章 |
| `quality_distribution.csv` | 六类标签的数量与占比 | 第四章 |
| `consistency_matrix.csv` | 双维度交叉计数（A/B × 四档） | 第四章 |
| `consistency_by_star.csv` | 各星级 × 四档一致性 | 第四章 |
| `method_comparison.csv` | 两套方法的 P/R/F1/误杀率 | 第四章 |
| `method_comparison_by_movie.csv` | 影片层面的保留率差异 | 第四章 |
| `sentiment_eval_overall.csv` | 情感模型整体指标 | 第四章 |
| `sentiment_eval_by_class.csv` | 情感模型分项指标 | 第四章 |
| `sentiment_eval_confusion.csv` | 情感混淆矩阵 | 第四章 |
| `q1_descriptive.csv` | 评分与评分人数描述统计 | 第五章 |
| `q1_correlation.csv` | 相关系数 | 第五章 |
| `q1_rating_histogram.csv` | 评分档位频数 | 第五章 |
| `q2_era_distribution.csv` | 年代分布 | 第六章 |
| `q2_genre_distribution.csv` | 主类型分布 | 第六章 |
| `q2_era_genre_crosstab.csv` | 年代×类型交叉计数 | 第六章 |
| `q2_share_by_era.csv` | 年代内部类型占比 | 第六章 |
| `q2_share_of_total.csv` | 占全样本比例 | 第六章 |
| `q2_era_genre_long.csv` | 交叉表长格式（按数量排序） | 第六章 |
| `q2_era_rating.csv` | 各年代评分统计 | 第六章 |
| `q3_underrated_full.csv` | 全部影片指数（含低置信度） | 第七章 |
| `q3_underrated_top10.csv` | 正式前十名 | 第七章 |
| `q3_high_rating_low_attention.csv` | 高评分低关注前十 | 第七章 |
| `q3_high_rating_high_attention.csv` | 高评分高关注前十 | 第七章 |
| `q3_sentiment_above_rating.csv` | 文本情感高于预期前十 | 第七章 |
| `q3_weight_sensitivity.csv` | 五组权重排名稳定性 | 第七章 |
| `q4_correlation.csv` | 星级与情感相关 | 第八章 |
| `q4_star_sentiment_counts.csv` | 星级×情感计数 | 第八章 |
| `q4_star_sentiment_distribution.csv` | 各星级内部情感占比 | 第八章 |
| `q4_mismatch_rates.csv` | 两个方向的不一致发生率 | 第八章 |
| `q4_cases_pool.csv` | 候选池（80 条，供复核选择） | — |
| `q4_mismatch_20cases.csv` | **最终 20 条样本与复核结论** | 第八章 |
| `q5_market_facts.csv` | 12 条市场事实（含来源与日期） | 第九章 |
| `q5_genre_heat.csv` | 类型市场热度赋分 | 第九章 |
| `q5_release_windows.csv` | 档期窗口与适配类型 | 第九章 |
| `q5_remake_recommendations.csv` | 五部推荐影片 | 第九章 |

---

## 七、外部数据集 `data/external/douban_top250_reviews/*.csv`

原始分片文件，共 148 个，每个对应一部影片：

| 字段 | 含义 |
|---|---|
| `time` | 评论时间（含换行与缩进，载入时清理） |
| `uname` | 用户昵称（载入后哈希脱敏） |
| `comment` | 评论文本 |
| `star` | 星级 1—5 |
| `title` | 星级文字（力荐/推荐/还行/较差/很差） |
| `support` | 有用数 |
| `sentiment_score` | 数据集作者的第三方情感分（本项目不采用） |

> 文件名前缀 `douban_movie_xsk_1-5` 为原数据集命名，无实际含义。
> 影片《活着》对应文件表头残缺，255 条记录字段整体错位，已标记为结构损坏并剔除。