<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>跨平台套利扫描 · 实时报告</title>
<meta http-equiv="refresh" content="60">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #1a1a2e; color: #e0e0e0; display: flex; min-height: 100vh; }
.menu-toggle { display: none; position: fixed; top: 10px; left: 10px; z-index: 100; background: #e94560; color: #fff; border: none; width: 36px; height: 36px; border-radius: 6px; font-size: 20px; cursor: pointer; }
.sidebar { width: 260px; background: #16213e; padding: 20px; flex-shrink: 0; overflow-y: auto; transition: transform 0.3s; }
.sidebar h2 { color: #e94560; font-size: 18px; margin-bottom: 8px; }
.sidebar .subtitle { color: #888; font-size: 12px; line-height: 1.5; margin-bottom: 16px; }
.sidebar .date-group { margin-bottom: 12px; }
.sidebar .date-label { color: #aaa; font-size: 13px; margin-bottom: 4px; }
.sidebar a { display: block; color: #7ec8e3; text-decoration: none; font-size: 13px; padding: 4px 8px; border-radius: 4px; }
.sidebar a:hover { background: #0f3460; }
.sidebar a.active { background: #0f3460; color: #e94560; }
.sidebar-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 49; }
.content { flex: 1; padding: 30px; overflow-y: auto; }
.content h1 { font-size: 24px; color: #e94560; margin-bottom: 20px; }
.content h2 { font-size: 18px; color: #e94560; margin: 20px 0 10px; border-bottom: 1px solid #333; padding-bottom: 4px; }
.content h3 { font-size: 15px; color: #7ec8e3; margin: 14px 0 6px; }
.content table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; }
.content th { background: #16213e; padding: 8px 12px; text-align: left; font-size: 13px; }
.content td { padding: 6px 12px; font-size: 13px; border-bottom: 1px solid #333; }
.content tr:hover td { background: #1a1a3e; }
.content p { margin: 6px 0; font-size: 14px; line-height: 1.6; }
.content ul { margin: 8px 0 8px 20px; }
.content li { font-size: 14px; line-height: 1.6; }
.content strong { color: #e94560; }
.content hr { border: none; border-top: 1px solid #333; margin: 16px 0; }
.content code { background: #16213e; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
.content pre { background: #16213e; padding: 12px; border-radius: 6px; overflow-x: auto; }
.content a { color: #7ec8e3; }
.empty { color: #666; font-size: 15px; margin-top: 40px; text-align: center; }
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
@media (max-width: 768px) {
    body { flex-direction: column; }
    .menu-toggle { display: block; }
    .sidebar { position: fixed; top: 0; left: 0; bottom: 0; z-index: 50; width: 260px; transform: translateX(-100%); }
    .sidebar.open { transform: translateX(0); }
    .sidebar-overlay.open { display: block; }
    .content { padding: 50px 12px 20px; }
    .content h1 { font-size: 20px; }
    .content h2 { font-size: 16px; }
    .content h3 { font-size: 14px; }
    .content th, .content td { padding: 6px 8px; font-size: 12px; }
    .content p, .content li { font-size: 13px; }
}
</style>
<script>
function toggleSidebar() {
    document.querySelector('.sidebar').classList.toggle('open');
    document.querySelector('.sidebar-overlay').classList.toggle('open');
}
</script>
</head>
<body>
<button class="menu-toggle" onclick="toggleSidebar()">☰</button>
<div class="sidebar-overlay" onclick="toggleSidebar()"></div>
<div class="sidebar">
    <h2>套利扫描</h2>
    <div class="subtitle">Odds API + Polymarket + Kalshi<br>每 60 秒自动刷新页面</div>
    <div class="date-group">
        <a href="/" class="">最新报告</a>
    </div>
    
    <div class="date-group">
        <div class="date-label">2026-07-31</div>
        
        <a href="/report/live_paper_20260731_012515.md" class="active">1_012515</a>
        
    </div>
    
    <div class="date-group">
        <div class="date-label">2026-07-24</div>
        
        <a href="/report/live_paper_20260724_161332.md" class="">4_161332</a>
        
    </div>
    
    <div class="date-group">
        <div class="date-label">2026-07-15</div>
        
        <a href="/report/live_paper_20260715_025930.md" class="">5_025930</a>
        
    </div>
    
    <div class="date-group">
        <div class="date-label">2026-07-14</div>
        
        <a href="/report/live_paper_20260714_093752.md" class="">4_093752</a>
        
        <a href="/report/live_paper_20260714_092750.md" class="">4_092750</a>
        
        <a href="/report/live_paper_20260714_092315.md" class="">4_092315</a>
        
        <a href="/report/live_paper_20260714_091839.md" class="">4_091839</a>
        
        <a href="/report/live_paper_20260714_091404.md" class="">4_091404</a>
        
        <a href="/report/live_paper_20260714_090925.md" class="">4_090925</a>
        
        <a href="/report/live_paper_20260714_063123.md" class="">4_063123</a>
        
    </div>
    
    <div class="date-group">
        <div class="date-label">arb_-co-st</div>
        
        <a href="/report/arb_cost_analysis.md" class="">analysis</a>
        
    </div>
    
</div>
<div class="content">
<h1>实时模拟盘报告</h1>

<p><strong>运行时间:</strong> 2026-07-31 01:25:15 CST</p>
<p><strong>扫描耗时:</strong> 20.9 秒</p>
<p><strong>数据源:</strong> 博彩公司(The Odds API), Polymarket, Kalshi</p>

<h2>扫描概况</h2>

<tr><th>指标</th><th>数值</th></tr>
<div class="table-wrap"><table>
<tr><td>扫描比赛数</td><td>210</td></tr>
<tr><td>未开赛比赛</td><td>210</td></tr>
<tr><td>发现套利机会 (S<0.98)</td><td>1</td></tr>
<tr><td>本次开仓</td><td>0</td></tr>
<tr><td>本次结算</td><td>0</td></tr>
</table></div>

<h2>账户盈亏</h2>

<tr><th>指标</th><th>数值</th></tr>
<div class="table-wrap"><table>
<tr><td>初始资金</td><td>100,000.00</td></tr>
<tr><td>当前资金</td><td>28,795.21</td></tr>
<tr><td>总盈亏</td><td>-71,204.79</td></tr>
<tr><td>收益率</td><td>-71.20%</td></tr>
</table></div>

<h2>本次发现的套利机会</h2>

<h3>Indiana Fever vs PortlandFire</h3>
<li>联赛: wnba</li>
<li>开赛: 2026-08-01T02:00:00+00:00</li>
<li>套利指数 S: <strong>0.9750</strong></li>
<li>理论收益: <strong>2.56%</strong></li>
<li>是否开仓: 否</li>

<tr><th>结果</th><th>平台</th><th>赔率</th><th>投注</th></tr>
<div class="table-wrap"><table>
<tr><td>Indiana</td><td>kalshi (预测)</td><td>1.37</td><td>7487.18</td></tr>
<tr><td>PortlandFire</td><td>polymarket (预测)</td><td>4.08</td><td>2512.82</td></tr>
</table></div>

<h2>最接近套利的市场 (Top 10)</h2>

<p>即使 S ≥ 0.98 也列出，便于观察市场状态。</p>

<tr><th>比赛</th><th>联赛</th><th>S</th><th>理论收益%</th><th>主胜最佳</th><th>平局最佳</th><th>客胜最佳</th></tr>
<div class="table-wrap"><table>
<tr><td>Indiana Fever vs PortlandFire</td><td>wnba</td><td>0.9750</td><td>2.56</td><td>kalshi @1.37</td><td>- @0.00</td><td>polymarket @4.08</td></tr>
<tr><td>Inter Milan vs Monza</td><td>Serie A - Italy</td><td>0.9859</td><td>1.43</td><td>onexbet @1.26</td><td>smarkets @7.40</td><td>betfair_ex_uk @17.50</td></tr>
<tr><td>Newcastle United vs Liverpool</td><td>EPL</td><td>0.9930</td><td>0.71</td><td>betfair_ex_uk @3.35</td><td>betfair_ex_uk @4.00</td><td>onexbet @2.25</td></tr>
<tr><td>Dallas Wings vs Washington Mystics</td><td>wnba</td><td>0.9950</td><td>0.50</td><td>kalshi @1.67</td><td>- @0.00</td><td>polymarket @2.53</td></tr>
<tr><td>Nice vs Lorient</td><td>Ligue 1 - France</td><td>0.9988</td><td>0.12</td><td>onexbet @2.25</td><td>onexbet @3.78</td><td>betfair_ex_uk @3.45</td></tr>
<tr><td>Sevilla vs Rayo Vallecano</td><td>La Liga - Spain</td><td>0.9991</td><td>0.09</td><td>onexbet @2.32</td><td>onexbet @3.40</td><td>betfair_ex_uk @3.65</td></tr>
<tr><td>Toronto Tempo vs Dallas Wings</td><td>wnba</td><td>1.0000</td><td>0.00</td><td>polymarket @4.08</td><td>- @0.00</td><td>polymarket @1.32</td></tr>
<tr><td>Minnesota Lynx vs Toronto Tempo</td><td>wnba</td><td>1.0000</td><td>0.00</td><td>polymarket @1.17</td><td>- @0.00</td><td>polymarket @6.90</td></tr>
<tr><td>New York Liberty vs Las Vegas Aces</td><td>wnba</td><td>1.0000</td><td>0.00</td><td>polymarket @2.90</td><td>- @0.00</td><td>polymarket @1.53</td></tr>
<tr><td>Connecticut Sun vs Chicago Sky</td><td>wnba</td><td>1.0000</td><td>0.00</td><td>polymarket @2.90</td><td>- @0.00</td><td>polymarket @1.53</td></tr>
</table></div>

<h2>未结算持仓</h2>

<li><strong>Connecticut Sun vs Chicago Sky</strong> S=0.9700 投入=10000 理论收益=3.09%</li>
<li><strong>New York Liberty vs Las Vegas Aces</strong> S=0.9500 投入=10000 理论收益=5.26%</li>
<li><strong>Seattle Storm vs Atlanta Dream</strong> S=0.7750 投入=10000 理论收益=29.03%</li>
<li><strong>Indiana Fever vs PortlandFire</strong> S=0.9450 投入=10000 理论收益=5.82%</li>
<li><strong>Dallas Wings vs Washington Mystics</strong> S=0.9700 投入=10000 理论收益=3.09%</li>
<li><strong>Atlanta Dream vs Dallas Wings</strong> S=0.9750 投入=10000 理论收益=2.56%</li>
<li><strong>Golden State Valkyries vs Phoenix Mercury</strong> S=0.9750 投入=10000 理论收益=2.56%</li>

<h2>数据新鲜度</h2>

<tr><th>数据源</th><th>最后刷新</th></tr>
<div class="table-wrap"><table>
<tr><td>Polymarket</td><td>实时</td></tr>
<tr><td>Kalshi</td><td>实时</td></tr>
<tr><td>博彩公司</td><td>实时</td></tr>
</table></div>

<h2>监控平台与扣费假设</h2>

<tr><th>平台</th><th>类型</th><th>扣费（模拟盘）</th></tr>
<div class="table-wrap"><table>
<tr><td>Pinnacle</td><td>博彩</td><td>盈利佣金 0%</td></tr>
<tr><td>1xBet (onexbet)</td><td>博彩</td><td>盈利佣金 0%</td></tr>
<tr><td>Unibet UK</td><td>博彩</td><td>盈利佣金 0%</td></tr>
<tr><td>William Hill</td><td>博彩</td><td>盈利佣金 0%</td></tr>
<tr><td>Betfair Exchange</td><td>交易所</td><td>净盈利佣金 5%（表内 2%~5% 取保守）</td></tr>
<tr><td>Smarkets</td><td>交易所</td><td>净盈利佣金 2%</td></tr>
<tr><td>Matchbook</td><td>交易所</td><td>净盈利佣金 2%（表内 1%~2% 取保守）</td></tr>
<tr><td>Polymarket</td><td>预测</td><td>交易费 2%（表内 0%~2% 取保守）</td></tr>
<tr><td>Kalshi</td><td>预测</td><td>交易费约 1%</td></tr>
</table></div>

<h2>说明</h2>

<li>赔率为扫描时刻各平台 API 快照，非逐笔推送</li>
<li>已扣：滑点 0.5%、预测市场手续费（Polymarket 2% / Kalshi 1%）、交易所净盈利佣金、跨平台汇率损耗 0.3%</li>
<li>博彩公司盈利佣金按 0%；充提成本未按笔建模</li>
<li>仅 S < 0.98 时模拟开仓</li>
<li>网页每 60 秒自动刷新；数据来自 <code>reports/latest.md</code></li>

</div>
</body>
</html>