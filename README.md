# Family Economic Dashboard

一个用于长期家庭经济盘点的轻量项目。仓库把**全国官方数据自动采集**与**个人/本地数据手工录入**分开，并通过 GitHub Actions 定期采集、计算红黄绿状态、生成 HTML/Markdown/CSV 报告。

## 数据链路

```text
国家统计局 ─┐
财政部     ├─> GitHub Actions: Collect official data
人民银行   ┘             │
                         ├─> data/official_observations.csv
                         └─> data/provenance.json

招聘/家庭/本地房产/本地财政/行业数据
                         └─> data/manual_observations.csv

两类数据合并
  -> 统计引擎
  -> 红黄绿 / 五维评分 / 共振 / 覆盖率
  -> dist/index.html
  -> dist/report.md
  -> dist/indicator_summary.csv
  -> dist/dimension_summary.csv
```

缺失数据**不参与评分**，报告同时展示数据覆盖率，避免把未采集指标错误地当作“中性”。

## 已接入的官方采集

`family_economic_dashboard/collect.py` 与 `collect_profit.py` 使用 Python 标准库直接访问官方网页，并保存来源 URL 和采集时间：

- 国家统计局：民间投资、全国城镇调查失业率、私营工业企业利润、规上工业应收账款平均回收期。
- 中国人民银行：住户中长期贷款、企事业单位中长期贷款。
- 财政部：全国地方一般公共预算本级收入同比、国有土地使用权出让收入同比。

财政部站点对 GitHub Hosted Runner 偶尔会返回 HTTP 502。采集器采用追加/覆盖同一 `(date, indicator)` 的方式，因此临时访问失败不会删除之前成功采集的历史数据；失败情况会记录在 `data/provenance.json`。

## 需要手工录入的数据

以下数据与个人、行业或具体城市强相关，不建议由公共 GitHub Runner 强行抓取：

- 固定条件下的招聘岗位数、薪资中位数、猎头/面试机会；
- 家庭现金可撑月数、月供/税后收入；
- 本地二手房成交量、成交周期、租金、人口；
- 本地财政收入、土地收入；
- 自己行业的订单/利润。

统一追加到 `data/manual_observations.csv`：

```csv
date,indicator,value,note
2026-09-30,job_postings,1200,上海+产品经理+5-10年+30-50K 固定搜索条件
2026-09-30,cash_runway_months,14.2,可动用现金/每月必要支出
```

不要提交账号、身份证号、银行卡号或完整流水；只保存计算后的汇总值。

## GitHub Actions

### `Collect official data`

`.github/workflows/collect.yml`：

- 支持手工 `workflow_dispatch`；
- 每月 23 日 02:30 UTC（北京时间 10:30）自动运行；
- 运行测试；
- 从国家统计局、财政部、人民银行抓取官方数据；
- 构建一次仪表盘；
- 如数据变化，自动把 `official_observations.csv` 和 `provenance.json` 提交回 `main`；
- 上传 `official-data-collection` Artifact，保留 90 天。

### `Build dashboard`

`.github/workflows/build.yml` 在 `main` push、Pull Request、手工触发及固定周期运行。它执行测试并生成最终 `dist/` Artifact。

## 本地运行

```bash
python -m unittest discover -s tests -v
python -m family_economic_dashboard.collect
python -m family_economic_dashboard.collect_profit
python -m family_economic_dashboard.cli --output dist
```

只构建、不联网采集：

```bash
python -m family_economic_dashboard.cli --output dist
```

指定盘点日期：

```bash
python -m family_economic_dashboard.cli --as-of 2026-08-31 --output dist
```

## 项目结构

```text
config/indicators.json                 指标、权重、阈值、采集类型
config/sources.json                    官方入口
data/official_observations.csv         Actions 自动采集的真实官方数据
data/manual_observations.csv           个人/本地手工数据
data/provenance.json                   最新采集来源和错误审计
family_economic_dashboard/collect.py   官方主采集器
family_economic_dashboard/collect_profit.py  NBS 工业利润兼容采集器
family_economic_dashboard/engine.py    统计、评分、覆盖率、共振
family_economic_dashboard/report.py    HTML/Markdown/CSV 报告
.github/workflows/collect.yml          周期采集
.github/workflows/build.yml            测试和最终构建
tests/                                 统计与解析测试
```

## 使用原则

1. 官方数据自动采集，个人和本地数据只提交汇总值。
2. 固定指标定义、固定搜索条件和固定数据来源，保证跨期可比。
3. 单次抓取失败不覆盖历史成功值，并在 provenance 中留痕。
4. 半年盘点重点看趋势、覆盖率以及同维度多指标共振，不把低覆盖率综合分当作完整家庭结论。
