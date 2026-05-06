# Index Tracker

## 解析文件使用说明

本仓库会生成两类 CSV 数据：指数成分股和官方储备资产。CSV 文件均使用 UTF-8 编码，可直接用 Python、Excel、数据库导入工具或其他数据处理工具读取。

### 指数成分股

当前维护的指数成分股文件：

| 指数 | 最新成分股文件 | 历史归档目录 | 数据源 |
| --- | --- | --- | --- |
| 沪深300 | `00300-沪深300/cons.csv` | `00300-沪深300/archive/` | `000300cons.xls` |
| 科创50 | `000688-科创50/cons.csv` | `000688-科创50/archive/` | `000688cons.xls` |
| 中证500 | `000905-中证500/cons.csv` | `000905-中证500/archive/` | `000905cons.xls` |

`cons.csv` 是单列表：

| 字段 | 含义 |
| --- | --- |
| `code` | 成分券代码，按 6 位字符串保存，例如 `000001` |

使用方式示例：

```python
import pandas as pd

hs300 = pd.read_csv("00300-沪深300/cons.csv", dtype={"code": str})
star50 = pd.read_csv("000688-科创50/cons.csv", dtype={"code": str})
csi500 = pd.read_csv("000905-中证500/cons.csv", dtype={"code": str})
```

当远端成分券代码与本地 `cons.csv` 完全一致时，不会改动文件；当不一致时，会把下载到的原始文件按运行日期保存为 `archive/yyyyMMdd.xlsx`，并覆盖更新对应目录下的 `cons.csv`。

### 官方储备资产

官方储备资产文件位于：

```text
reserve-assets/assets.csv
```

字段说明：

| 字段 | 含义 |
| --- | --- |
| `month` | 数据月份，格式为 `YYYY-MM` |
| `item_no` | 官方表格项目编号；合计行为空 |
| `item_cn` | 中文项目名 |
| `item_en` | 英文项目名 |
| `unit` | 计量单位 |
| `value` | 数值，保留官方页面展示精度 |
| `source_url` | 数据来源页面 |

使用方式示例：

```python
import pandas as pd

assets = pd.read_csv("reserve-assets/assets.csv", dtype={"month": str})
total_usd = assets[
    (assets["item_en"] == "Total")
    & (assets["unit"] == "100million USD")
]
```

`assets.csv` 来自国家外汇管理局官方储备资产页面。脚本会解析页面中已发布的月份数据，因此同一个文件会随着官方页面更新而覆盖刷新。

## GitHub Actions 使用说明

本仓库包含两个 GitHub Actions 工作流。

### 指数成分股更新

工作流文件：

```text
.github/workflows/update-hs300-cons.yml
```

触发规则：

- 定时触发：北京时间每个工作日 09:00。
- 手动触发：在 GitHub 仓库的 `Actions` 页面选择 `Update CSI Constituents`，点击 `Run workflow`。

执行逻辑：

1. 读取 `法定节假日.csv`，如果当天日期 `yyyyMMdd` 在文件中，则跳过。
2. 下载沪深300、科创50和中证500的成分券文件。
3. 解析 `成份券代码Constituent Code` 列。
4. 与对应目录下的 `cons.csv` 的 `code` 列逐项完全比较。
5. 有变化时归档原始下载文件，并覆盖更新 `cons.csv`。
6. 有文件变更时自动提交并推送到仓库。

### 官方储备资产更新

工作流文件：

```text
.github/workflows/update-safe-assets.yml
```

触发规则：

- 定时触发：北京时间每月 10 日 09:00。
- 脚本限制：定时任务只在 2026 年执行。
- 手动触发：在 GitHub 仓库的 `Actions` 页面选择 `Update SAFE Assets`，点击 `Run workflow`。手动触发会强制刷新，不受日期限制。

执行逻辑：

1. 获取国家外汇管理局官方储备资产页面。
2. 解析页面表格中已经发布的 2026 年月份数据。
3. 覆盖写入 `reserve-assets/assets.csv`。
4. 有文件变更时自动提交并推送到仓库。

### 权限和本地运行

两个工作流都需要仓库允许 GitHub Actions 写入内容：

```text
Settings -> Actions -> General -> Workflow permissions -> Read and write permissions
```

本地运行前先安装依赖：

```bash
pip install -r requirements.txt
```

本地更新指数成分股：

```bash
python scripts/update_hs300_cons.py
```

本地强制刷新官方储备资产：

```bash
FORCE_RUN=1 python scripts/update_safe_assets.py
```
