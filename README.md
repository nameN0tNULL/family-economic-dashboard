# Family Economic Dashboard

一个用于长期家庭经济盘点的轻量项目。仓库把**全国官方数据自动采集**、**公开的城市/招聘/房地产信号**与**私人家庭财务输入**分开，并通过 GitHub Actions 定期采集、计算红黄绿状态、生成 HTML/Markdown/CSV 报告。

## 数据链路

```text
国家统计局 / 财政部 / 人民银行
  -> GitHub Actions 自动采集
  -> data/official_observations.csv
  -> data/provenance.json

区域 / 招聘 / 房地产 / 城市人口公开数据
  -> data/*.csv

公开输入合并
  -> 统计引擎
  -> 红黄绿 / 五维评分 / 共振 / 覆盖率
  -> dist/                 # 可提交、可发布到 GitHub Pages

私人家庭财务汇总（仅本地）
  -> data/private_household_finance.csv   # gitignored
  -> 派生月数/百分比，不输出原始金额
  -> private_dist/                         # gitignored，不发布
```

缺失数据**不参与评分**，报告同时展示数据覆盖率，避免把未采集指标错误地当作“中性”。

## 已接入的官方采集

`family_economic_dashboard/collect.py` 与 `collect_profit.py` 使用 Python 标准库访问官方网页，并保存来源 URL 和采集时间：

- 国家统计局：民间投资、全国城镇调查失业率、居民实际收入/消费、私营工业企业利润、规上工业应收账款平均回收期；
- 中国人民银行：住户中长期贷款、企事业单位中长期贷款；
- 财政部：全国地方一般公共预算本级收入同比、国有土地使用权出让收入同比；
- 房地产：70 城新房/二手房价格、开发投资、商品房销售、二手房网签面积、开发商到位资金；
- 城市：重点城市常住人口年度变化；
- 招聘：官方市场招聘薪酬基准。

财政部等站点对 GitHub Hosted Runner 偶尔会出现临时访问失败。采集器采用追加/覆盖同一主键的方式，因此失败不会删除之前成功采集的历史值；错误会写入 provenance。

## 家庭财务安全：私人本地构建

家庭现金、收入、支出和负债属于敏感信息。**不要把这些金额写入 `data/manual_observations.csv`，也不要提交到公开仓库。**

仓库提供安全模板：

```bash
cp data/private_household_finance.example.csv data/private_household_finance.csv
```

然后只在本地编辑 `data/private_household_finance.csv`。该文件已被 `.gitignore` 排除。

字段定义：

| 字段 | 含义 |
|---|---|
| `liquid_assets` | 可快速动用的现金、活期/定期存款、货币类资产；不含自住房和难以快速变现的长期资产 |
| `after_tax_income` | 家庭月度税后总收入 |
| `essential_expenses` | 必要生活支出，不含债务还款 |
| `debt_payments` | 房贷、消费贷等每月本息支出 |
| `total_expenses` | 月度全部支出，必须包含必要支出和债务还款 |
| `stable_income_if_primary_lost` | 假设主收入来源中断后，家庭仍能稳定获得的月度税后收入 |

建议填“典型月”或最近 3 个月平均值，减少一次性大额消费造成的噪声。

私密构建命令：

```bash
python -m family_economic_dashboard.cli \
  --private-household data/private_household_finance.csv \
  --output private_dist
```

然后在本机打开 `private_dist/index.html`。

安全措施：

- `data/private_household_finance.csv` 和 `private_dist/` 均被 Git 忽略；
- CLI 如果同时使用 `--private-household` 和 `--output dist` 会直接拒绝执行；
- 报告只显示派生指标（月数、百分比），不会写出原始现金、收入、负债金额；
- GitHub Pages 的公开构建不会读取私人家庭文件。

当前私人安全垫指标：

- **零收入现金跑道**：流动资产 ÷（必要生活支出 + 债务支出），低于 12 个月黄灯、低于 6 个月红灯；
- **偿债率**：月债务支出 ÷ 税后收入，达到 30% 黄灯、45% 红灯；
- **家庭储蓄率**：（税后收入 − 总支出）÷ 税后收入，低于 10% 黄灯、低于 0% 红灯；
- **固定必要支出率**：（必要生活支出 + 债务支出）÷ 税后收入，达到 70% 黄灯、90% 红灯；
- **主收入中断现金跑道**：扣除主收入后、考虑剩余稳定收入的压力情景，低于 12 个月黄灯、低于 6 个月红灯。

全国居民实际收入、消费增速与住户信用数据只作为低权重背景，不能抵消家庭自身高杠杆或现金跑道不足。

## 其他手工数据

以下非敏感或已汇总的数据仍可按需要维护：

- 固定条件下的招聘岗位数、薪资中位数、猎头/面试机会；
- 本地二手房成交量、成交周期、租金；
- 本地财政收入、土地收入；
- 自己行业的订单/利润指数。

公开仓库中不要保存账号、身份证号、银行卡号、完整流水、公司内部敏感信息或家庭原始金额。

## GitHub Actions

### `Collect official data`

`.github/workflows/collect.yml`：

- 支持手工 `workflow_dispatch`；
- 每月 23 日 02:30 UTC（北京时间 10:30）自动运行；
- 运行测试；
- 从国家统计局、财政部、人民银行抓取官方数据；
- 构建公开仪表盘；
- 如数据变化，提交官方观察值、provenance 和 `dist/`；
- 上传 `official-data-collection` Artifact；
- 成功后触发 GitHub Pages 部署。

### `Build dashboard`

`.github/workflows/build.yml` 在 `main` push、Pull Request、手工触发及固定周期运行，执行测试并生成公开 `dist/`。它不会加载私人家庭财务文件。

## 本地运行

公开构建：

```bash
python -m unittest discover -s tests -v
python -m family_economic_dashboard.cli --output dist
```

采集官方数据后再构建：

```bash
python -m family_economic_dashboard.collect
python -m family_economic_dashboard.collect_profit
python -m family_economic_dashboard.cli --output dist
```

指定盘点日期：

```bash
python -m family_economic_dashboard.cli --as-of 2026-08-31 --output dist
```

## 项目结构

```text
config/indicators.json                         指标、权重、阈值、采集类型
config/sources.json                            官方入口
data/official_observations.csv                 Actions 自动采集的官方数据
data/private_household_finance.example.csv     私密家庭输入模板（示例值）
data/private_household_finance.csv             私密实际输入（gitignored）
data/provenance.json                           最新采集来源和错误审计
family_economic_dashboard/household_finance.py 家庭财务派生与隐私保护
family_economic_dashboard/collect.py           官方主采集器
family_economic_dashboard/engine.py            统计、评分、覆盖率、共振
family_economic_dashboard/report.py            基础 HTML/Markdown/CSV 报告
dist/                                           公开 Dashboard
private_dist/                                   本地私密 Dashboard（gitignored）
.github/workflows/                              自动采集、构建与 Pages 发布
tests/                                          统计、解析与隐私边界测试
```

## 使用原则

1. 官方数据自动采集；家庭原始财务金额只留本地。
2. 固定指标定义、固定数据来源，保证跨期可比。
3. 单次抓取失败不覆盖历史成功值，并在 provenance 中留痕。
4. 先看私人家庭现金流与杠杆，再看全国宏观背景。
5. 半年盘点重点看趋势、覆盖率及多指标共振，不把低覆盖率综合分当作完整家庭结论。
