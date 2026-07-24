# 实时模拟盘报告

**运行时间:** 2026-07-24 14:47:32 CST
**扫描耗时:** 28.6 秒
**数据源:** 博彩公司(The Odds API), Polymarket, Kalshi

## 扫描概况

| 指标 | 数值 |
|------|------|
| 扫描比赛数 | 155 |
| 未开赛比赛 | 155 |
| 发现套利机会 (S<0.98) | 1 |
| 本次开仓 | 1 |
| 本次结算 | 1 |

## 账户盈亏

| 指标 | 数值 |
|------|------|
| 初始资金 | 100,000.00 |
| 当前资金 | 100,804.07 |
| 总盈亏 | +804.07 |
| 收益率 | +0.80% |

## 本次发现的套利机会

### Vålerenga Fotball vs Hamarkameratene
- 联赛: norway-eliteserien
- 开赛: 2026-07-31T17:00:00+00:00
- 套利指数 S: **0.9100**
- 理论收益: **9.89%**
- 是否开仓: 是

| 结果 | 平台 | 赔率 | 投注 |
|------|------|------|------|
| Vålerenga Fotball | polymarket (预测) | 2.27 | 4835.16 |
| Draw (Vålerenga Fotball vs. Hamarkameratene) | polymarket (预测) | 4.00 | 2747.25 |
| Hamarkameratene | polymarket (预测) | 4.55 | 2417.58 |

## 最接近套利的市场 (Top 10)

即使 S ≥ 0.98 也列出，便于观察市场状态。

| 比赛 | 联赛 | S | 理论收益% | 主胜最佳 | 平局最佳 | 客胜最佳 |
|------|------|---|-----------|---------|---------|---------|
| Vålerenga Fotball vs Hamarkameratene | norway-eliteserien | 0.9100 | 9.89 | polymarket @2.27 | polymarket @4.00 | polymarket @4.55 |
| Brentford vs Tottenham Hotspur | EPL | 0.9961 | 0.40 | betfair_ex_uk @2.46 | onexbet @3.92 | onexbet @2.99 |
| Degerfors IF vs Djurgardens IF | Allsvenskan - Sweden | 0.9980 | 0.20 | smarkets @4.90 | betfair_ex_uk @4.10 | polymarket @1.82 |
| Sevilla vs Rayo Vallecano | La Liga - Spain | 0.9982 | 0.18 | onexbet @2.36 | onexbet @3.37 | betfair_ex_uk @3.60 |
| Nice vs Lorient | Ligue 1 - France | 0.9988 | 0.12 | onexbet @2.25 | onexbet @3.78 | betfair_ex_uk @3.45 |
| Inter Milan vs Monza | Serie A - Italy | 0.9991 | 0.09 | onexbet @1.26 | onexbet @6.67 | betfair_ex_uk @18.00 |
| Frosinone vs Juventus | Serie A - Italy | 0.9996 | 0.04 | betfair_ex_uk @8.20 | onexbet @4.55 | onexbet @1.52 |
| Arsenal vs Coventry City | EPL | 0.9997 | 0.03 | betfair_ex_uk @1.21 | onexbet @8.20 | onexbet @19.50 |
| Rublev vs Van Assche | atp | 1.0000 | 0.00 | kalshi @1.16 | - @0.00 | kalshi @7.14 |
| Bouzkova vs Valentova | wta | 1.0000 | 0.00 | kalshi @1.56 | - @0.00 | kalshi @2.78 |

## 已结算记录

| 比赛 | 结果 | 净利 | 开仓时间 |
|------|------|------|---------|
| Vålerenga Fotball vs Hamarkameratene | home | +804.07 | 2026-07-24T06:47:29 |

## 数据新鲜度

| 数据源 | 最后刷新 |
|--------|---------|
| Polymarket | 实时 |
| Kalshi | 实时 |
| 博彩公司 | 21 小时前 |

## 说明

- 赔率为扫描时刻各平台 API 快照，非逐笔推送
- 已扣滑点 0.5%、预测市场手续费 1%、交易所净盈利佣金、汇率损耗 0.3%
- 仅 S < 0.98 时模拟开仓
