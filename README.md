# A 股选股策略 · 抄底波段222

基于「抄底波段222」公式的 A 股日线选股程序，数据源为 [akshare](https://github.com/akfamily/akshare)，无需 API 密钥。

## 筛选条件（需同时满足）

1. **日线出现抄底波段222 红色向上箭头**  
   即公式中的买入信号：`SIGNALBUY = CD1 OR CD2 OR CD3`，且 `COUNT(SIGNALBUY, 3) = 1`。
2. **风险系数 < 20**
3. **KDJ 在 20 下方金叉**（K 上穿 D，且 K、D 均 < 20）

## 抄底波段222 公式要点

- **相对强弱**：`0.5*RSI(3) + 0.31*RSI(5) + 0.19*RSI(8)`，RSI 使用同花顺 SMA 递归计算。
- **短线波段**：`0.5*wave(3) + 0.31*wave(5) + 0.19*wave(8)`，wave 为 8 日高低位归一。
- **风险系数**：`0.5*相对强弱 + 0.5*短线波段`。
- **红色箭头**：
  - CD1：风险系数<20 且 收>开 且 大单净量>0
  - CD2：风险系数<20 且 未创新低 且 收>低 且 大单净量>0
  - CD3：前一日风险系数<20 且 当日风险系数上升  

无 L2 大单数据时，程序用「成交额较前一日增加」作为大单净量>0 的代理。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行选股（会遍历全 A 股，耗时较长）
python stock_screener_bottom_band.py
```

## 输出

- `qualified_stocks_bottom_band_YYYYMMDD_HHMMSS.txt`：文本清单
- `qualified_stocks_bottom_band_YYYYMMDD_HHMMSS.csv`：CSV（可导入 Excel）

## 环境

- Python 3.7+
- akshare、pandas、numpy（见 `requirements.txt`）

## 免责声明

仅供学习与研究，不构成任何投资建议。投资有风险，入市需谨慎。
