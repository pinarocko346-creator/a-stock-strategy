# A股量化策略框架

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `a_stock_template.py` | **主要文件** - 填入你的指标逻辑 |

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install akshare pandas numpy
```

### 2. 填入你的指标

打开 `a_stock_template.py`，找到两个 `TODO` 区域：

#### TODO 1: 计算技术指标

```python
def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
    # ========== 在这里填入你的指标计算 ==========
    
    # 已有示例指标：
    # - 移动平均线 (ma5, ma10, ma20)
    # - MACD
    # - RSI
    # - 布林带
    
    # 填入你的自定义指标：
    df['my_indicator'] = df['close'] * df['volume'] / 10000
    
    return df
```

#### TODO 2: 买卖条件和评分

```python
def generate_signals(self, df: pd.DataFrame) -> Dict:
    score = 0
    reasons = []
    
    # ========== 在这里填入你的买入条件 ==========
    
    # 示例条件（可删除或修改）：
    if latest['close'] > latest['ma5'] > latest['ma10']:
        score += 25
        reasons.append('均线多头排列')
    
    # 填入你的自定义条件：
    if latest['my_indicator'] > 100:
        score += 20
        reasons.append('自定义指标触发')
    
    # 评分规则：
    # score >= 60: 买入信号
    # score <= 20: 卖出信号
    # 其他: 观望
    
    return {'signal': signal, 'score': score, 'reasons': reasons}
```

### 3. 运行扫描

```bash
python a_stock_template.py
```

---

## 📊 可用数据字段

### 原始数据（自动获取）

| 字段 | 说明 |
|------|------|
| `open` | 开盘价 |
| `high` | 最高价 |
| `low` | 最低价 |
| `close` | 收盘价 |
| `volume` | 成交量 |

### 示例指标（已计算）

| 指标 | 说明 |
|------|------|
| `ma5`, `ma10`, `ma20` | 5/10/20日移动平均线 |
| `macd` | MACD线 |
| `macd_signal` | MACD信号线 |
| `macd_hist` | MACD柱状图 |
| `rsi` | 相对强弱指标 |
| `bb_upper` | 布林带上轨 |
| `bb_middle` | 布林带中轨 |
| `bb_lower` | 布林带下轨 |

---

## 📝 示例策略

### 示例1: 双均线金叉策略

```python
def generate_signals(self, df: pd.DataFrame) -> Dict:
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    score = 0
    reasons = []
    
    # 金叉：短期均线上穿长期均线
    if prev['ma5'] <= prev['ma20'] and latest['ma5'] > latest['ma20']:
        score += 50
        reasons.append('MA5金叉MA20')
    
    # 价格在均线上方
    if latest['close'] > latest['ma20']:
        score += 30
        reasons.append('价格在MA20上方')
    
    # 成交量放大
    avg_volume = df['volume'].rolling(20).mean().iloc[-1]
    if latest['volume'] > avg_volume * 1.5:
        score += 20
        reasons.append('成交量放大')
    
    signal = 'buy' if score >= 60 else 'hold'
    
    return {'signal': signal, 'score': score, 'reasons': reasons}
```

### 示例2: 超跌反弹策略

```python
def generate_signals(self, df: pd.DataFrame) -> Dict:
    latest = df.iloc[-1]
    
    score = 0
    reasons = []
    
    # RSI超卖
    if latest['rsi'] < 30:
        score += 40
        reasons.append(f'RSI超卖({latest["rsi"]:.1f})')
    
    # 跌破布林带下轨
    if latest['close'] < latest['bb_lower']:
        score += 30
        reasons.append('跌破布林带下轨')
    
    # 近期跌幅较大
    price_20d_ago = df['close'].iloc[-20]
    if (latest['close'] - price_20d_ago) / price_20d_ago < -0.15:
        score += 30
        reasons.append('20日跌幅超15%')
    
    signal = 'buy' if score >= 60 else 'hold'
    
    return {'signal': signal, 'score': score, 'reasons': reasons}
```

---

## ⚙️ 配置参数

### 修改扫描数量

```python
# 默认扫描200只股票
results = scanner.scan(max_stocks=200)

# 扫描全A股（约5000只，较慢）
results = scanner.scan(max_stocks=5000)
```

### 修改策略名称

```python
class AStockStrategy:
    def __init__(self):
        self.name = "双均线金叉策略"  # 填入你的策略名称
        self.description = "MA5上穿MA20买入"
```

---

## 📤 添加到GitHub Actions

### 1. 创建工作流文件

`.github/workflows/a-stock-daily.yml`

```yaml
name: A股策略扫描

on:
  schedule:
    # 交易日15:30后运行 (UTC 07:30)
    - cron: '30 7 * * 1-5'
  workflow_dispatch:

jobs:
  scan:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - uses: actions/setup-python@v5
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        pip install akshare pandas numpy
    
    - name: Run A股扫描
      run: python a_stock_strategy/a_stock_template.py
    
    - name: Upload report
      uses: actions/upload-artifact@v4
      with:
        name: a-stock-report
        path: a_stock_report_*.md
    
    - name: Send to Discord
      env:
        DISCORD_WEBHOOK: ${{ secrets.DISCORD_WEBHOOK_URL }}
      run: |
        REPORT=$(ls a_stock_report_*.md | head -1)
        curl -H "Content-Type: application/json" \
             -X POST \
             -d "{\"content\": \"📊 A股策略扫描完成\\n$(head -20 $REPORT)\"}" \
             $DISCORD_WEBHOOK
```

### 2. 推送到GitHub

```bash
git add .
git commit -m "Add A股策略框架"
git push origin main
```

---

## 🎯 进阶用法

### 添加更多指标

```python
def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
    # KDJ指标
    low_list = df['low'].rolling(9, min_periods=9).min()
    high_list = df['high'].rolling(9, min_periods=9).max()
    rsv = (df['close'] - low_list) / (high_list - low_list) * 100
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    df['J'] = 3 * df['K'] - 2 * df['D']
    
    # ATR（平均真实波幅）
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['close'].shift())
    df['tr3'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    
    return df
```

### 多条件组合

```python
def generate_signals(self, df: pd.DataFrame) -> Dict:
    # 可以同时检查多个时间周期
    latest = df.iloc[-1]
    
    # 趋势条件（日线）
    trend_ok = latest['close'] > latest['ma20']
    
    # 动量条件
    momentum_ok = latest['macd'] > 0 and latest['rsi'] > 50
    
    # 波动率条件
    volatility_ok = latest['atr'] / latest['close'] < 0.05
    
    if trend_ok and momentum_ok and volatility_ok:
        score = 80
        reasons = ['趋势向上', '动量强劲', '波动率正常']
    
    return {'signal': 'buy', 'score': score, 'reasons': reasons}
```

---

## ⚠️ 注意事项

1. **数据频率**: akshare可能有请求限制，扫描全A股可能较慢
2. **历史数据**: 默认获取60天数据，如需更多请修改 `days` 参数
3. **复权处理**: 默认使用前复权，避免除权除息影响
4. **交易时间**: A股交易日9:30-11:30, 13:00-15:00

---

## 📚 参考

- [akshare文档](https://www.akshare.xyz/)
- [pandas教程](https://pandas.pydata.org/docs/)
- [技术分析指标](https://school.stockcharts.com/)

---

**现在打开 `a_stock_template.py`，填入你的指标，开始扫描吧！** 🦐
