"""
股票选股策略 - 抄底波段222 版（基于 akshare）
按你提供的「抄底波段222」公式实现：
  1. 日线出现红色向上箭头 = SIGNALBUY 且 COUNT(SIGNALBUY,3)=1
     SIGNALBUY = CD1 OR CD2 OR CD3（见公式）
  2. 风险系数 < 20
  3. KDJ 在 20 下方金叉
大单净量 r 无 L2 时用「成交额较前一日增加」作为代理。
"""

import pandas as pd
import numpy as np
import akshare as ak
import time
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')


def sma_recursive(x: pd.Series, n: int, m: int) -> pd.Series:
    """
    同花顺/通达信 SMA(X, N, M)：递归平滑
    SMA = (M*X + (N-M)*REF(SMA,1)) / N，首根取 X。
    """
    out = pd.Series(index=x.index, dtype=float)
    for i in range(len(x)):
        if i == 0 or pd.isna(x.iloc[i]):
            out.iloc[i] = x.iloc[i]
        else:
            prev = out.iloc[i - 1]
            if pd.isna(prev):
                out.iloc[i] = x.iloc[i]
            else:
                out.iloc[i] = (m * x.iloc[i] + (n - m) * prev) / n
    return out


class StockScreenerBottomBand:
    def __init__(self, use_big_order_proxy=True):
        """
        use_big_order_proxy: 无大单数据时用成交额增加代替 r>0，True=使用代理。
        """
        self.qualified_stocks = []
        self.use_big_order_proxy = use_big_order_proxy

    def _r_proxy(self, df: pd.DataFrame) -> pd.Series:
        """大单净量代理：无 L2 时用 成交额较前一日增加 视为 r>0 的代理。"""
        if 'amount' not in df.columns or len(df) < 2:
            return pd.Series(1.0, index=df.index)  # 无数据时视为满足
        amt = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
        ref_amt = amt.shift(1)
        return (amt > ref_amt).astype(float).replace(0, np.nan)  # 1 表示 r>0 代理成立

    def calculate_risk_coefficient_222(self, df: pd.DataFrame):
        """
        抄底波段222：相对强弱 + 短线波段 + 风险系数（与公式完全一致）
        - 相对强弱: 0.5*RSI1+0.31*RSI2+0.19*RSI3，RSI 用 SMA(MAX(CLOSE-LC,0),n,1)/SMA(ABS(CLOSE-LC),n,1)*100
        - 短线波段: 0.5*wave1+0.31*wave2+0.19*wave3，wave 为 SMA(100*(C-LLV(L,8))/(HHV(H,8)-LLV(L,8)), n, 1)
        - 风险系数: 0.5*相对强弱+0.5*短线波段
        """
        close = df['close'].astype(float)
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        LC = close.shift(1)
        clc = close - LC
        max_clc = clc.clip(lower=0)
        abs_clc = clc.abs().replace(0, np.nan)

        # RSI$i = SMA(MAX(CLOSE-LC,0), ni, 1) / SMA(ABS(CLOSE-LC), ni, 1) * 100
        def rsi_n(n):
            s1 = sma_recursive(max_clc, n, 1)
            s2 = sma_recursive(abs_clc, n, 1)
            r = (s1 / s2 * 100).fillna(50)
            return r

        RSI1 = rsi_n(3)
        RSI2 = rsi_n(5)
        RSI3 = rsi_n(8)
        相对强弱 = 0.5 * RSI1 + 0.31 * RSI2 + 0.19 * RSI3

        # wave_raw = 100*(CLOSE-LLV(LOW,8))/(HHV(HIGH,8)-LLV(LOW,8))
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
        """
        抄底波段222 红色向上箭头：
        CD1 = 风险系数<20 AND CLOSE>OPEN AND r>0
        CD2 = 风险系数<20 AND LOW>=REF(LOW,1) AND CLOSE>LOW AND r>0
        CD3 = REF(风险系数,1)<20 AND 风险系数>REF(风险系数,1)
        SIGNALBUY = (CD1=1 OR CD2=1 OR CD3=1)
        X = SIGNALBUY AND COUNT(SIGNALBUY,3)=1  → 画红色箭头
        判断最后一根 K 线是否满足 X。
        """
        if df is None or len(df) < 5:
            return False
        if not all(c in df.columns for c in ['close', 'open', 'high', 'low']):
            return False

        风险系数 = self.calculate_risk_coefficient_222(df)
        ref_风险 = 风险系数.shift(1)
        ref_low = df['low'].shift(1)

        close = df['close'].astype(float)
        open_ = df['open'].astype(float)
        low = df['low'].astype(float)

        if self.use_big_order_proxy:
            r_ok = self._r_proxy(df)
            r_gt_0 = (r_ok == 1.0)
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
        """计算 KDJ"""
        low_n = df['low'].rolling(window=n, min_periods=1).min()
        high_n = df['high'].rolling(window=n, min_periods=1).max()
        denom = (high_n - low_n).replace(0, np.nan)
        rsv = (df['close'] - low_n) / denom * 100
        rsv = rsv.fillna(50)
        k = rsv.ewm(alpha=1/m1, adjust=False).mean()
        d = k.ewm(alpha=1/m2, adjust=False).mean()
        j = 3 * k - 2 * d
        return k, d, j

    def check_kdj_golden_cross_below_20(self, k, d, threshold=20):
        """
        检查是否在 20 下方金叉：当日 K 上穿 D，且金叉时 K、D 均 < 20。
        """
        if len(k) < 2:
            return False
        if pd.isna(k.iloc[-1]) or pd.isna(d.iloc[-1]) or pd.isna(k.iloc[-2]) or pd.isna(d.iloc[-2]):
            return False

        golden_cross = (k.iloc[-2] <= d.iloc[-2]) and (k.iloc[-1] > d.iloc[-1])
        below_20 = (k.iloc[-1] < threshold) and (d.iloc[-1] < threshold)

        return golden_cross and below_20

    def get_stock_kline(self, stock_code, period='daily', count=120):
        """获取日线 K 线（默认 120 根）"""
        try:
            if len(stock_code) == 6:
                code = stock_code
            elif len(stock_code) < 6:
                code = stock_code.zfill(6)
            else:
                code = stock_code.split('.')[-1] if '.' in stock_code else stock_code[-6:]

            if code.startswith('6'):
                df = ak.stock_zh_a_hist(symbol=code, period='daily', adjust="qfq")
            elif code.startswith('0') or code.startswith('3'):
                df = ak.stock_zh_a_hist(symbol=code, period='daily', adjust="qfq")
            else:
                return None

            if df is None or len(df) == 0:
                return None

            df = df.rename(columns={
                '日期': 'date', '开盘': 'open', '收盘': 'close',
                '最高': 'high', '最低': 'low', '成交量': 'volume', '成交额': 'amount'
            })
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')
            df = df.tail(count).reset_index(drop=True)

            for col in ['open', 'close', 'high', 'low']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        except Exception as e:
            print(f"获取 {stock_code} K线失败: {e}")
            return None

    def screen_stock(self, stock_code):
        """
        筛选单只股票：抄底波段红箭头 + 风险系数<20 + KDJ 20 下方金叉。
        """
        try:
            df = self.get_stock_kline(stock_code, period='daily', count=120)
            if df is None or len(df) < 30:
                return False, None
            if not all(col in df.columns for col in ['close', 'high', 'low', 'open']):
                return False, None

            # 1) 抄底波段222 红色向上箭头（CD1/CD2/CD3 + COUNT(SIGNALBUY,3)=1）
            if not self.check_bottom_band_red_arrow_222(df):
                return False, None

            # 2) 风险系数 < 20（与公式一致）
            风险系数 = self.calculate_risk_coefficient_222(df)
            if pd.isna(风险系数.iloc[-1]) or 风险系数.iloc[-1] >= 20:
                return False, None

            # 3) KDJ 20 下方金叉
            k, d, j = self.calculate_kdj(df)
            if not self.check_kdj_golden_cross_below_20(k, d, threshold=20):
                return False, None

            return True, {
                'code': stock_code,
                '风险系数': round(风险系数.iloc[-1], 2),
                'K值': round(k.iloc[-1], 2),
                'D值': round(d.iloc[-1], 2),
                'J值': round(j.iloc[-1], 2),
            }
        except Exception as e:
            print(f"处理 {stock_code} 出错: {e}")
            return False, None

    def get_all_a_stocks(self):
        """获取全部 A 股代码"""
        try:
            print("正在获取 A 股列表...")
            stock_info = ak.stock_info_a_code_name()
            if stock_info is None or len(stock_info) == 0:
                return []
            codes = stock_info['code'].tolist()
            print(f"✓ 共 {len(codes)} 只 A 股")
            return codes
        except Exception as e:
            print(f"获取股票列表失败: {e}")
            return []

    def run_screening(self):
        """执行选股并保存清单"""
        print("=" * 80)
        print("选股策略（抄底波段222）：红箭头(CD1/CD2/CD3) + 风险系数<20 + KDJ20下方金叉")
        print("=" * 80)

        all_stocks = self.get_all_a_stocks()
        if not all_stocks:
            return

        print("\n开始筛选，请稍候...\n")
        total = len(all_stocks)

        for i, code in enumerate(all_stocks, 1):
            if i % 50 == 0:
                print(f"进度: {i}/{total} ({i/total*100:.1f}%) - 已选入 {len(self.qualified_stocks)} 只")
            ok, info = self.screen_stock(code)
            if ok:
                self.qualified_stocks.append(info)
                print(f"✓ [{i}/{total}] {info['code']} 风险系数:{info['风险系数']} K:{info['K值']} D:{info['D值']} J:{info['J值']}")
            if i % 10 == 0:
                time.sleep(1)
            else:
                time.sleep(0.2)

        print(f"\n{'=' * 80}")
        print(f"筛选完成，共 {len(self.qualified_stocks)} 只入选")
        print("=" * 80)

        if not self.qualified_stocks:
            print("当前无符合条件的股票。")
            return

        self.qualified_stocks.sort(key=lambda x: x['风险系数'])
        self.save_results()

    def save_results(self):
        """保存 TXT 与 CSV 股票清单"""
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        txt_path = f"qualified_stocks_bottom_band_{ts}.txt"
        csv_path = f"qualified_stocks_bottom_band_{ts}.csv"

        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("选股清单（抄底波段222 + 风险系数<20 + KDJ20下方金叉）\n")
            f.write("=" * 80 + "\n")
            f.write(f"筛选时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"共 {len(self.qualified_stocks)} 只\n")
            f.write("=" * 80 + "\n\n")
            for s in self.qualified_stocks:
                f.write(f"{s['code']}  风险系数:{s['风险系数']}  K:{s['K值']}  D:{s['D值']}  J:{s['J值']}\n")

        pd.DataFrame(self.qualified_stocks).to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"结果已保存: {txt_path}, {csv_path}")


def main():
    screener = StockScreenerBottomBand()
    screener.run_screening()


if __name__ == "__main__":
    main()
