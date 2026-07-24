# 全平台缓存套利分析（含成本）

- 数据源: `data/all_sources_cache.json`
- 构建时间: 2026-07-24 07:02 UTC
- 合并比赛: 156 场 · 可计算: 143 场
- 分源场数: sportsbooks=99, polymarket=52, kalshi=14, merged=156
- API: The Odds API（多 Key）+ Polymarket/Kalshi 直连

## 包含平台

| 平台 | 报价条数 |
|------|----------|
| unibet_uk | 248 |
| pinnacle | 237 |
| smarkets | 231 |
| onexbet | 228 |
| betfair_ex_uk | 206 |
| polymarket | 156 |
| williamhill | 141 |
| kalshi | 28 |
| matchbook | 27 |

## 结论

**全成本后有 1 场净套利**（最佳净收益 +7.96%）。

- 裸盘理论套利（S_raw < 1）: **6** 场（最高 +9.89%）
- 扣佣/手续费后（S_comm < 1）: **1** 场
- 全成本净利 > 0: **1** 场（最佳 +7.96%）

## 成本假设

| 项目 | 取值 |
|------|------|
| 每场总投入 | 10000 |
| 赔率滑点 | 0.5% |
| 跨平台汇率损耗 | 0.3% |
| betfair_ex_uk 佣金（净盈利） | 5.0% |
| smarkets 佣金（净盈利） | 2.0% |
| matchbook 佣金（净盈利） | 1.0% |
| polymarket 手续费 | 1.0% |
| kalshi 手续费 | 1.0% |

```
交易所有效赔率 = 1 + (odds - 1) × (1 - 佣金%)
预测市场执行赔率 = odds × (1 - 滑点%) / (1 + 1.0%)
净收益率 = (1/S_slip - 1 - 汇率损耗%) × 100
```

## 套利指数分布

- S_raw: min=0.9100 · median=1.0179
- S_slip: min=0.9237 · median=1.0342

| S 区间 | 裸盘场数 | 扣费+滑点后 |
|--------|----------|-------------|
| S<0.98 | 1 | 1 |
| 0.98–0.99 | 0 | 0 |
| 0.99–1.00 | 5 | 0 |
| 1.00–1.01 | 17 | 0 |
| 1.01–1.02 | 50 | 29 |
| 1.02–1.03 | 27 | 41 |
| 1.03–1.05 | 17 | 37 |
| 1.05–1.10 | 16 | 25 |
| S≥1.10 | 10 | 10 |

## 最接近套利 TOP20

| # | 比赛 | 联赛 | S_raw | 理论% | S_comm | 扣费% | 净% |
|---|------|------|-------|-------|--------|-------|-----|
| 1 NET+ | Vålerenga Fotball vs Hamarkameratene | norway-eliteserien | 0.9100 | +9.89% | 0.9100 | +9.89% | +7.96% |
| 2 | Fulham vs Chelsea | EPL | 1.0051 | -0.51% | 1.0051 | -0.51% | -1.31% |
| 3 RAW+ | Frosinone vs Juventus | Serie A - Italy | 0.9996 | +0.04% | 1.0052 | -0.52% | -1.32% |
| 4 RAW+ | Sevilla vs Rayo Vallecano | La Liga - Spain | 0.9982 | +0.18% | 1.0063 | -0.62% | -1.42% |
| 5 RAW+ | Arsenal vs Coventry City | EPL | 0.9997 | +0.03% | 1.0069 | -0.69% | -1.48% |
| 6 | Västerås SK vs Örgryte IS | Allsvenskan - Sweden | 1.0006 | -0.06% | 1.0074 | -0.74% | -1.53% |
| 7 | Washington Mystics vs Connecticut Sun | WNBA | 1.0079 | -0.79% | 1.0079 | -0.79% | -1.58% |
| 8 RAW+ | Brentford vs Tottenham Hotspur | EPL | 0.9961 | +0.40% | 1.0085 | -0.84% | -1.64% |
| 9 | Inter Milan vs Monza | Serie A - Italy | 1.0061 | -0.60% | 1.0091 | -0.91% | -1.70% |
| 10 RAW+ | Nice vs Lorient | Ligue 1 - France | 0.9989 | +0.12% | 1.0095 | -0.94% | -1.74% |
| 11 | Hanfmann vs Halys | atp | 1.0000 | +0.00% | 1.0000 | +0.00% | -1.79% |
| 12 | Hull City vs Manchester United | EPL | 1.0044 | -0.44% | 1.0103 | -1.02% | -1.82% |
| 13 | Degerfors IF vs Djurgardens IF | Allsvenskan - Sweden | 1.0048 | -0.48% | 1.0089 | -0.89% | -1.87% |
| 14 | Phoenix Mercury vs Golden State Valkyries | WNBA | 1.0112 | -1.11% | 1.0112 | -1.11% | -1.91% |
| 15 | Atlético Madrid vs Málaga | La Liga - Spain | 1.0088 | -0.87% | 1.0126 | -1.25% | -2.04% |
| 16 | Everton vs Crystal Palace | EPL | 1.0126 | -1.25% | 1.0134 | -1.32% | -2.12% |
| 17 | Deportivo La Coruña vs Elche CF | La Liga - Spain | 1.0062 | -0.61% | 1.0137 | -1.35% | -2.15% |
| 18 | RB Leipzig vs Borussia Monchengladbach | Bundesliga - Germany | 1.0139 | -1.37% | 1.0139 | -1.37% | -2.16% |
| 19 | Marseille vs Strasbourg | Ligue 1 - France | 1.0139 | -1.37% | 1.0139 | -1.37% | -2.16% |
| 20 | Atalanta BC vs Sassuolo | Serie A - Italy | 1.0124 | -1.23% | 1.0140 | -1.38% | -2.18% |

## TOP 明细（腿分配）

### 1. Vålerenga Fotball vs Hamarkameratene（norway-eliteserien）

- S_raw=0.9100（+9.89%）→ S_comm=0.9100（+9.89%）→ 净 +7.96%
- 扣成本后平台: polymarket

| 结果 | 平台 | 类型 | 裸盘 | 执行 | 费% | 投注 |
|------|------|------|------|------|-----|------|
| Vålerenga Fotball | polymarket | prediction | 2.273 | 2.239 | 1% | 4835.16 |
| Draw (Vålerenga Fotball vs. Hamarkameratene) | polymarket | prediction | 4.000 | 3.941 | 1% | 2747.25 |
| Hamarkameratene | polymarket | prediction | 4.545 | 4.478 | 1% | 2417.58 |

### 2. Fulham vs Chelsea（EPL）

- S_raw=1.0051（-0.51%）→ S_comm=1.0051（-0.51%）→ 净 -1.31%
- 扣成本后平台: onexbet, williamhill

| 结果 | 平台 | 类型 | 裸盘 | 执行 | 费% | 投注 |
|------|------|------|------|------|-----|------|
| Fulham | williamhill | sportsbook | 3.250 | 3.234 | - | 3061.18 |
| Draw | onexbet | sportsbook | 3.780 | 3.761 | - | 2631.97 |
| Chelsea | onexbet | sportsbook | 2.310 | 2.298 | - | 4306.85 |

### 3. Frosinone vs Juventus（Serie A - Italy）

- S_raw=0.9996（+0.04%）→ S_comm=1.0052（-0.52%）→ 净 -1.32%
- 扣成本后平台: betfair_ex_uk, onexbet

| 结果 | 平台 | 类型 | 裸盘 | 执行 | 费% | 投注 |
|------|------|------|------|------|-----|------|
| Frosinone | betfair_ex_uk | exchange | 8.200 | 7.801 | 5% | 1268.88 |
| Draw | onexbet | sportsbook | 4.550 | 4.527 | - | 2186.38 |
| Juventus | onexbet | sportsbook | 1.520 | 1.512 | - | 6544.74 |

### 4. Sevilla vs Rayo Vallecano（La Liga - Spain）

- S_raw=0.9982（+0.18%）→ S_comm=1.0063（-0.62%）→ 净 -1.42%
- 扣成本后平台: onexbet, smarkets

| 结果 | 平台 | 类型 | 裸盘 | 执行 | 费% | 投注 |
|------|------|------|------|------|-----|------|
| Sevilla | onexbet | sportsbook | 2.360 | 2.348 | - | 4210.92 |
| Draw | onexbet | sportsbook | 3.370 | 3.353 | - | 2948.90 |
| Rayo Vallecano | smarkets | exchange | 3.550 | 3.482 | 2% | 2840.18 |

### 5. Arsenal vs Coventry City（EPL）

- S_raw=0.9997（+0.03%）→ S_comm=1.0069（-0.69%）→ 净 -1.48%
- 扣成本后平台: betfair_ex_uk, onexbet

| 结果 | 平台 | 类型 | 裸盘 | 执行 | 费% | 投注 |
|------|------|------|------|------|-----|------|
| Arsenal | betfair_ex_uk | exchange | 1.210 | 1.194 | 5% | 8279.56 |
| Draw | onexbet | sportsbook | 8.200 | 8.159 | - | 1211.14 |
| Coventry City | onexbet | sportsbook | 19.500 | 19.402 | - | 509.30 |

### 6. Västerås SK vs Örgryte IS（Allsvenskan - Sweden）

- S_raw=1.0006（-0.06%）→ S_comm=1.0074（-0.74%）→ 净 -1.53%
- 扣成本后平台: matchbook, smarkets

| 结果 | 平台 | 类型 | 裸盘 | 执行 | 费% | 投注 |
|------|------|------|------|------|-----|------|
| Västerås SK | matchbook | exchange | 1.610 | 1.596 | 1% | 6188.84 |
| Draw | matchbook | exchange | 4.700 | 4.640 | 1% | 2128.73 |
| Örgryte IS | smarkets | exchange | 6.000 | 5.871 | 2% | 1682.42 |

### 7. Washington Mystics vs Connecticut Sun（WNBA）

- S_raw=1.0079（-0.79%）→ S_comm=1.0079（-0.79%）→ 净 -1.58%
- 扣成本后平台: onexbet, unibet_uk

| 结果 | 平台 | 类型 | 裸盘 | 执行 | 费% | 投注 |
|------|------|------|------|------|-----|------|
| Washington Mystics | unibet_uk | sportsbook | 1.440 | 1.433 | - | 6889.85 |
| Connecticut Sun | onexbet | sportsbook | 3.190 | 3.174 | - | 3110.15 |

### 8. Brentford vs Tottenham Hotspur（EPL）

- S_raw=0.9961（+0.40%）→ S_comm=1.0085（-0.84%）→ 净 -1.64%
- 扣成本后平台: betfair_ex_uk, onexbet

| 结果 | 平台 | 类型 | 裸盘 | 执行 | 费% | 投注 |
|------|------|------|------|------|-----|------|
| Brentford | betfair_ex_uk | exchange | 2.460 | 2.375 | 5% | 4154.11 |
| Draw | onexbet | sportsbook | 3.920 | 3.900 | - | 2529.55 |
| Tottenham Hotspur | onexbet | sportsbook | 2.990 | 2.975 | - | 3316.34 |

### 9. Inter Milan vs Monza（Serie A - Italy）

- S_raw=1.0061（-0.60%）→ S_comm=1.0091（-0.91%）→ 净 -1.70%
- 扣成本后平台: betfair_ex_uk, onexbet

| 结果 | 平台 | 类型 | 裸盘 | 执行 | 费% | 投注 |
|------|------|------|------|------|-----|------|
| Inter Milan | onexbet | sportsbook | 1.260 | 1.254 | - | 7864.55 |
| Draw | onexbet | sportsbook | 6.670 | 6.637 | - | 1485.66 |
| Monza | betfair_ex_uk | exchange | 16.000 | 15.174 | 5% | 649.79 |

### 10. Nice vs Lorient（Ligue 1 - France）

- S_raw=0.9989（+0.12%）→ S_comm=1.0095（-0.94%）→ 净 -1.74%
- 扣成本后平台: betfair_ex_uk, onexbet

| 结果 | 平台 | 类型 | 裸盘 | 执行 | 费% | 投注 |
|------|------|------|------|------|-----|------|
| Nice | onexbet | sportsbook | 2.250 | 2.239 | - | 4402.53 |
| Draw | onexbet | sportsbook | 3.780 | 3.761 | - | 2620.55 |
| Lorient | betfair_ex_uk | exchange | 3.450 | 3.311 | 5% | 2976.92 |
