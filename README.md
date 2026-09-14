# Family Economic Dashboard

一个面向家庭长期决策的周期性经济盘点工具。它把招聘、家庭现金流、房地产/城市、企业经营、地方财政等指标统一成可长期比较的红黄绿信号，并通过 GitHub Actions 自动生成 Markdown、HTML 和 CSV 汇总报告。

## 统计节奏

- **每月采集**：招聘、家庭现金流、二手房、信贷等高频数据。
- **每季度判断**：地方财政、企业利润、民间投资、行业数据。
- **每半年盘点**：建议每年 1 月和 7 月做家庭级综合复盘。
- **每年校准**：人口、城市结构等慢变量。

核心原则是保持指标定义和采集口径稳定，重点比较 **本期、环比、半年变化、同比和同维度共振**，而不是追逐单月新闻。

## 项目结构

```text
config/indicators.json      指标、维度、权重、红黄灯阈值
data/observations.csv       追加式历史数据
family_economic_dashboard/  统计与报告生成代码
.github/workflows/build.yml  自动测试与构建
tests/                      统计逻辑测试
dist/                       构建结果（不提交 Git）
```

实现只依赖 **Python 3.12 标准库**，GitHub Actions 无需 `pip install`，降低长期维护成本。

## 数据格式

`data/observations.csv`：

```csv
date,indicator,value,note
2026-09-01,job_postings,1394,固定搜索条件下的职位数
2026-09-01,cash_runway_months,15.75,可动用现金/每月必要支出
```

仓库自带的是**演示数据**，只用于验证统计和构建流程。正式使用时请替换为真实采集值。不要把账户号、身份证号、完整银行流水等敏感信息提交到仓库；家庭指标只保留汇总数字即可。

## 评分和共振

每个指标在 `config/indicators.json` 里定义：比较口径（绝对值/半年/同比）、风险方向、黄灯阈值、红灯阈值和指标权重。

状态映射：绿灯 100、黄灯 65、红灯 30、缺失 50。五大维度按 **就业 25% / 家庭财务 25% / 房地产与城市 20% / 企业经济 20% / 财政政策 10%** 汇总。

同一维度达到 **2 个红灯**记为“需要关注”，达到 **3 个红灯**记为“风险明显”。

## 本地运行

```bash
python -m unittest discover -s tests -v
python -m family_economic_dashboard.cli --output dist
```

指定盘点日期：

```bash
python -m family_economic_dashboard.cli --as-of 2026-07-31 --output dist
```

生成：`dist/index.html`、`dist/report.md`、`dist/indicator_summary.csv`、`dist/dimension_summary.csv`。

## GitHub Actions

`.github/workflows/build.yml` 在 push 到 `main`、Pull Request、手工触发以及每月 15 日自动运行。流程先测试，再构建 `dist/`，最后上传名为 `family-economic-dashboard` 的 Artifact，保留 90 天。

## 长期使用规则

1. 每月固定日期向 `data/observations.csv` 追加数据。
2. 不随意改变指标定义和采集口径；需要改变时优先新增版本说明。
3. 每半年重点看五大维度和“连续恶化 + 多指标共振”。
4. 数据缺失时不要用猜测值填补。
5. 新增指标前先明确来源、频率、风险方向和阈值。
