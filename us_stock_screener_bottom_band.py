"""
美股选股策略 - 抄底波段222（与 A 股同逻辑，数据源改为 yfinance）
筛选条件（与 A 股一致）：
  1. 日线出现红色向上箭头 = SIGNALBUY 且 COUNT(SIGNALBUY,3)=1
     SIGNALBUY = CD1 OR CD2 OR CD3（风险系数、K 线、大单代理）
  2. 风险系数 < 20
  3. KDJ 在 20 下方金叉
"""

import time
from datetime import datetime
import warnings
import pandas as pd
import numpy as np

from us_stock_data_fetcher import get_us_daily_ohlcv, get_us_stock_list_default, load_us_symbols_from_file

warnings.filterwarnings("ignore")


def tonghuashun_sma(series, n: int, m: int):
    """同花顺 SMA，与 A 股版一致。"""
    if hasattr(series, "tolist"):
        series = series.tolist()
    elif hasattr(series, "values"):
        series = series.tolist()
    series = list(series)
    if n <= m or len(series) == 0:
        raise ValueError("同花顺 SMA 参数需满足 N > M，且输入序列非空")
    sma_result = []
    for i in range(len(series)):
        if i == 0:
            sma_val = series[i]
        else:
            sma_val = (m * series[i] + (n - m) * sma_result[i - 1]) / n
        sma_result.append(sma_val)
    return sma_result


def sma_recursive(x: pd.Series, n: int, m: int) -> pd.Series:
    """对 pd.Series 做同花顺 SMA。"""
    arr = x.astype(float).tolist()
    result = tonghuashun_sma(arr, n, m)
    return pd.Series(result, index=x.index, dtype=float)


class USStockScreenerBottomBand:
    """美股抄底波段222 选股器，条件与 A 股完全一致，仅数据源为美股日线。"""

    def __init__(self, use_big_order_proxy=True):
        self.qualified_stocks = []
        self.use_big_order_proxy = use_big_order_proxy

    def _r_proxy(self, df: pd.DataFrame) -> pd.Series:
        """大单净量代理：成交额较前一日增加视为 r>0。"""
        if "amount" not in df.columns or len(df) < 2:
            return pd.Series(1.0, index=df.index)
        amt = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
        ref_amt = amt.shift(1)
        return (amt > ref_amt).astype(float).replace(0, np.nan)

    def calculate_risk_coefficient_222(self, df: pd.DataFrame):
        """抄底波段222 风险系数，与 A 股版一致。"""
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        LC = close.shift(1)
        clc = close - LC
        max_clc = clc.clip(lower=0)
        abs_clc = clc.abs().replace(0, np.nan)

        def rsi_n(n):
            s1 = sma_recursive(max_clc, n, 1)
            s2 = sma_recursive(abs_clc, n, 1)
            r = (s1 / s2 * 100).fillna(50)
            return r

        RSI1 = rsi_n(3)
        RSI2 = rsi_n(5)
        RSI3 = rsi_n(8)
        相对强弱 = 0.5 * RSI1 + 0.31 * RSI2 + 0.19 * RSI3

        llv8 = low.rolling(8, min_periods=1).min()
        hhv8 = high.rolling(8, min_periods=1).max()
        denom = (hhv8 - llv8).replace(0, np.nan)
        wave_raw = (100 * (close - llv8) / denom).fillna(50)

        wave1 = sma_recursive(wave_raw, 3, 1)
        wave2 = sma_recursive(wave_raw, 5, 1)
        wave3 = sma_recursive(wave_raw, 8, 1)
        短线波段 = 0.5 * wave1 + 0.31 * wave2 + 0.19 * wave3

        风险系数 = 0.5 * 相对强弱 + 0.5 * 短线波段
        return 风险系数

    def check_bottom_band_red_arrow_222(self, df: pd.DataFrame) -> bool:
        """抄底波段222 红色向上箭头：CD1/CD2/CD3，SIGNALBUY，COUNT(SIGNALBUY,3)=1。"""
        if df is None or len(df) < 5:
            return False
        if not all(c in df.columns for c in ["close", "open", "high", "low"]):
            return False

        风险系数 = self.calculate_risk_coefficient_222(df)
        ref_风险 = 风险系数.shift(1)
        ref_low = df["low"].shift(1)

        close = df["close"].astype(float)
        open_ = df["open"].astype(float)
        low = df["low"].astype(float)

        if self.use_big_order_proxy:
            r_ok = self._r_proxy(df)
            r_gt_0 = r_ok == 1.0
        else:
            r_gt_0 = pd.Series(True, index=df.index)

        CD1 = (风险系数 < 20) & (close > open_) & r_gt_0
        CD2 = (风险系数 < 20) & (low >= ref_low) & (close > low) & r_gt_0
        CD3 = (ref_风险 < 20) & (风险系数 > ref_风险)

        SIGNALBUY = CD1 | CD2 | CD3
        count_3 = SIGNALBUY.rolling(3, min_periods=1).sum()
        X = SIGNALBUY & (count_3 == 1)

        if len(X) == 0:
            return False
        last = X.iloc[-1]
        return bool(last) if not pd.isna(last) else False

    def calculate_kdj(self, df, n=9, m1=3, m2=3):
        """计算 KDJ。"""
        low_n = df["low"].rolling(window=n, min_periods=1).min()
        high_n = df["high"].rolling(window=n, min_periods=1).max()
        denom = (high_n - low_n).replace(0, np.nan)
        rsv = (df["close"] - low_n) / denom * 100
        rsv = rsv.fillna(50)
        k = rsv.ewm(alpha=1 / m1, adjust=False).mean()
        d = k.ewm(alpha=1 / m2, adjust=False).mean()
        j = 3 * k - 2 * d
        return k, d, j

    def check_kdj_golden_cross_below_20(self, k, d, threshold=20):
        """K 上穿 D 且金叉时 K、D 均 < 20。"""
        if len(k) < 2:
            return False
        if pd.isna(k.iloc[-1]) or pd.isna(d.iloc[-1]) or pd.isna(k.iloc[-2]) or pd.isna(d.iloc[-2]):
            return False
        golden_cross = (k.iloc[-2] <= d.iloc[-2]) and (k.iloc[-1] > d.iloc[-1])
        below_20 = (k.iloc[-1] < threshold) and (d.iloc[-1] < threshold)
        return golden_cross and below_20

    def get_stock_kline(self, symbol: str, count: int = 120):
        """获取美股日线 K 线（与 A 股列名一致）。"""
        df = get_us_daily_ohlcv(symbol, period="6mo", count=count)
        if df is None or len(df) == 0:
            return None
        return df

    def screen_stock(self, symbol: str):
        """筛选单只股票：红箭头 + 风险系数<20 + KDJ 20 下方金叉。"""
        try:
            df = self.get_stock_kline(symbol, count=120)
            if df is None or len(df) < 30:
                return False, None
            if not all(col in df.columns for col in ["close", "high", "low", "open"]):
                return False, None

            if not self.check_bottom_band_red_arrow_222(df):
                return False, None

            风险系数 = self.calculate_risk_coefficient_222(df)
            if pd.isna(风险系数.iloc[-1]) or 风险系数.iloc[-1] >= 20:
                return False, None

            k, d, j = self.calculate_kdj(df)
            if not self.check_kdj_golden_cross_below_20(k, d, threshold=20):
                return False, None

            return True, {
                "code": symbol,
                "风险系数": round(风险系数.iloc[-1], 2),
                "K值": round(k.iloc[-1], 2),
                "D值": round(d.iloc[-1], 2),
                "J值": round(j.iloc[-1], 2),
            }
        except Exception as e:
            print(f"处理 {symbol} 出错: {e}")
            return False, None

    def get_us_stocks(self, symbol_file: str = None) -> list:
        """获取待筛美股列表：优先从文件读取，否则用默认池。"""
        if symbol_file:
            symbols = load_us_symbols_from_file(symbol_file)
            if symbols:
                print(f"从文件加载 {len(symbols)} 只美股")
                return symbols
        symbols = get_us_stock_list_default()
        print(f"使用默认美股池: {len(symbols)} 只")
        return symbols

    def run_screening(self, symbol_file: str = None):
        """执行选股并保存清单。"""
        print("=" * 80)
        print("美股选股（抄底波段222）：红箭头 + 风险系数<20 + KDJ20下方金叉")
        print("=" * 80)

        symbols = self.get_us_stocks(symbol_file)
        if not symbols:
            return

        print("\n开始筛选，请稍候...\n")
        total = len(symbols)

        for i, sym in enumerate(symbols, 1):
            if i % 20 == 0:
                print(f"进度: {i}/{total} ({i/total*100:.1f}%) - 已选入 {len(self.qualified_stocks)} 只")
            ok, info = self.screen_stock(sym)
            if ok:
                self.qualified_stocks.append(info)
                print(f"✓ [{i}/{total}] {info['code']} 风险系数:{info['风险系数']} K:{info['K值']} D:{info['D值']} J:{info['J值']}")
            time.sleep(0.15)

        print(f"\n{'=' * 80}")
        print(f"筛选完成，共 {len(self.qualified_stocks)} 只入选")
        print("=" * 80)

        if not self.qualified_stocks:
            print("当前无符合条件的股票。")
            return

        self.qualified_stocks.sort(key=lambda x: x["风险系数"])
        self.save_results()

    def save_results(self):
        """保存 TXT 与 CSV。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        txt_path = f"qualified_stocks_us_bottom_band_{ts}.txt"
        csv_path = f"qualified_stocks_us_bottom_band_{ts}.csv"

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("美股选股清单（抄底波段222 + 风险系数<20 + KDJ20下方金叉）\n")
            f.write("=" * 80 + "\n")
            f.write(f"筛选时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"共 {len(self.qualified_stocks)} 只\n")
            f.write("=" * 80 + "\n\n")
            for s in self.qualified_stocks:
                f.write(f"{s['code']}  风险系数:{s['风险系数']}  K:{s['K值']}  D:{s['D值']}  J:{s['J值']}\n")

        pd.DataFrame(self.qualified_stocks).to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"结果已保存: {txt_path}, {csv_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="美股抄底波段222选股")
    parser.add_argument("--symbols", type=str, default=None, help="股票代码列表文件路径，每行一个代码")
    args = parser.parse_args()

    screener = USStockScreenerBottomBand()
    screener.run_screening(symbol_file=args.symbols)


if __name__ == "__main__":
    main()
