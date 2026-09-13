# 跨平台体育套利扫描系统

跨 **博彩公司**、**Polymarket**、**Kalshi**、**Myriad**、**Betfair** 等平台扫描体育赛事市场，自动合并同场比赛赔率，检测无风险套利机会。

**重要声明：本系统仅用于扫描和纸面交易模拟，不执行真实订单。Betfair 接入为只读模式。**

## 支持平台

| 平台 | 类型 | API | 认证 | 状态 |
|------|------|-----|------|------|
| Pinnacle / 1xBet / Unibet 等 | 博彩公司 | The Odds API | 需 API Key | 只读扫描 |
| Polymarket | 预测市场 | Gamma API | 免费公开 | 只读扫描 |
| Kalshi | 预测市场 | Trade API v2 | 免费公开 | 只读扫描 |
| Myriad | 预测市场 | Myriad API | 可选 API Key | 只读扫描 |
| Betfair | 交易所 | Exchange API | 需凭证 | 只读扫描 |

**支持运动项目：** 足球（胜平负）、篮球（胜负）、网球（胜负）、棒球、冰球、美式足球

## 核心逻辑

```
博彩公司赔率 ──┐
Polymarket 价格 ─┼→ 球队名匹配合并 → 每结果取最高赔率 → 套利检测
Kalshi 价格 ────┘
```

**价格转换：**
- Polymarket: 买入价 `p` (0~1) → 赔率 = `1/p`
- Kalshi: 价格 `c` (0~100¢) → 赔率 = `100/c`
- 博彩公司: 直接使用十进制赔率

**套利条件：**

```
S = 1/o_home + 1/o_draw + 1/o_away
理论收益(%) = (1/S - 1) × 100
```

默认仅当 **S < 0.98** 时报警（至少 2% 安全边际，覆盖手续费/滑点等损耗）。

可在 `config.yaml` 或 `.env` 中调整 `max_arb_index`。

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行扫描

```bash
# 演示（无需 API Key，使用内置示例数据）
python demo.py

# 仅扫描预测市场（无需博彩 API Key）
python main.py --no-sportsbooks

# 全平台扫描（需配置 ODDS_API_KEY）
cp .env.example .env
# 编辑 .env 文件，填入您的 API Key
python main.py

# 循环扫描 + 保存报告
python main.py --loop --interval 180 -o reports/arb.json
```

### API Key 获取

- **The Odds API**: 注册获取 https://the-odds-api.com （500次/月免费配额）
- **Myriad**: https://docs.myriad.markets/builders/myriad-api-reference （可选）
- **Betfair**: https://developer.betfair.com/exchange-api/ （需开发者账号）

## 纸面交易模拟

系统提供完整的纸面交易模拟功能，包含手续费、滑点、汇率损耗等真实成本。

```bash
# 实时数据纸面交易 + 自动生成报告（推荐）
python simulate.py live --reset --no-sportsbooks

# 场景回测（固定示例数据，无需 API）
python simulate.py demo

# 循环实时模拟
python simulate.py run --no-sportsbooks --loop --interval 180

# 查看报告
python simulate.py report
# 或查看 reports/latest.md
```

## 费用感知回测分析

使用缓存数据进行完整的费用感知分析：

```bash
# 1. 构建缓存（需 API Key）
python scripts/build_all_sources_cache.py

# 2. 分析套利机会（包含手续费、滑点、汇率损耗）
python scripts/analyze_cache_arb.py

# 3. 查看分析结果
cat data/arb_cost_analysis.json

# 4. 导出 Markdown 报告
python scripts/export_arb_cost_md.py
# 查看 reports/arb_cost_analysis.md
```

**注意：** 如果没有真实缓存数据，分析脚本会提示先运行 `build_all_sources_cache.py`。也可以使用 `pytest tests/` 运行合成数据测试。

## 配置

编辑 `config.yaml`：

```yaml
sources:
  sportsbooks: true      # 博彩公司
  polymarket: true       # Polymarket
  kalshi: true           # Kalshi
  polymarket_leagues:    # 扫描的 Polymarket 联赛
    - fifwc
    - epl
  kalshi_leagues:        # 扫描的 Kalshi 联赛
    - worldcup
    - epl
```

## 项目结构

```
taoli/
├── main.py              # 命令行入口
├── demo.py              # 跨平台演示
├── config.yaml          # 数据源 & 联赛配置
└── src/
    ├── arbitrage.py     # 套利计算核心
    ├── converters.py    # 预测市场价格 → 赔率
    ├── polymarket.py    # Polymarket 接入
    ├── kalshi.py        # Kalshi 接入
    ├── odds_api.py      # 博彩公司接入
    ├── team_matcher.py  # 跨平台比赛匹配
    ├── scanner.py       # 扫描编排
    └── models.py        # 数据模型
```

## 典型套利场景

预测市场与博彩公司对同一比赛的定价经常出现偏差，尤其是 **平局** 市场：

- Polymarket 平局 ask = 0.30 → 赔率 3.33
- 1xBet 平局 = 4.20
- Pinnacle 主胜 = 2.60

组合最佳赔率后可能满足套利条件。

## 费用模型

系统在纸面交易和回测中考虑以下真实成本：

- **交易所佣金**：Betfair 5%，Smarkets 2%，Matchbook 2%（从净盈利中扣除）
- **预测市场手续费**：Polymarket 2%，Kalshi 1%，Myriad 2%
- **滑点**：默认 0.5%（可在 `config.yaml` 中调整）
- **汇率/转账损耗**：默认 0.3%（跨平台资金流动）

配置位置：`config.yaml` 的 `paper_trade` 和 `exchanges` 节

## 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行带覆盖率报告
pytest tests/ --cov=src --cov-report=html

# 运行特定测试
pytest tests/test_arbitrage.py -v
```

## 后台运行（可选）

```bash
# 后台运行扫描
nohup python3 simulate.py live --loop --interval 180 > scan.log 2>&1 &

# 后台运行 Web 界面
gunicorn -w 2 -b 0.0.0.0:8080 web:app > web.log 2>&1 &

# 停止进程
pkill -f "simulate.py"
pkill -f "gunicorn"

# 查看运行状态
ps aux | grep -E "simulate.py|gunicorn" | grep -v grep
```

## 注意事项

- **仅用于研究和学习**：本系统不执行真实交易订单
- 预测市场使用 **bestAsk**（可执行买入价），不是中间价
- 实际套利需考虑：手续费、滑点、限额、资金到账时间、平台规则
- 大赛（世界杯）流动性高但套利窗口短；小联赛偏差大但流动性低
- API 配额有限：The Odds API 免费版 500次/月，建议设置合理的缓存和扫描间隔
