# 足球胜平负跨平台套利扫描系统

跨 **博彩公司**、**Polymarket**、**Kalshi** 三个平台扫描足球胜平负市场，自动合并同场比赛赔率，检测无风险套利机会。

## 支持平台

| 平台 | 类型 | API | 认证 |
|------|------|-----|------|
| Pinnacle / Bet365 / 1xBet 等 | 博彩公司 | The Odds API | 需 API Key |
| Polymarket | 预测市场 | Gamma API | 免费公开 |
| Kalshi | 预测市场 | Trade API v2 | 免费公开 |

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

```bash
pip install -r requirements.txt

# 演示（无需 API Key）
python demo.py

# 仅扫描预测市场（无需博彩 API Key）
python main.py --no-sportsbooks

# 全平台扫描（需配置 ODDS_API_KEY）
copy .env.example .env
python main.py

# 循环扫描 + 保存报告
python main.py --loop --interval 60 -o reports/arb.json
```

## 模拟盘

```bash
# 实时数据模拟盘 + 自动生成报告（推荐）
python simulate.py live --reset --no-sportsbooks

# 场景回测（固定示例数据，无需 API）
python simulate.py demo

# 循环实时模拟
python simulate.py run --no-sportsbooks --loop --interval 120

# 查看报告
python simulate.py report
# 或 reports/latest.md
```

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

## 注意事项

- 预测市场使用 **bestAsk**（可执行买入价），不是中间价
- 实际套利需考虑：手续费、滑点、限额、资金到账时间
- 大赛（世界杯）流动性高但套利窗口短；小联赛偏差大但流动性低

## 使用方法



```
nohup python3 main.py --loop > scan.log 2>&1 & gunicorn -w 2 -b 0.0.0.0:80 web:app > web.log 2>&1 &

nohup python3 simulate.py live --loop --interval 180 > scan.log 2>&1 & gunicorn -w 2 -b 0.0.0.0:80 web:app > web.log 2>&1 &

pkill -f "simulate.py"

pkill -f "gunicorn"

ps aux | grep -E "simulate.py|gunicorn" | grep -v grep
```
