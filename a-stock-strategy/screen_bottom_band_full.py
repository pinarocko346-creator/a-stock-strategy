#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy>=1.24.0",
# ]
# ///

"""
A股抄底波段222策略 - 本地数据库版
从本地SQLite数据库读取数据，全量扫描
"""

import os
import sys
import sqlite3
import json
import time
from datetime import datetime
from pathlib import Path

os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

import pandas as pd
import numpy as np

# 配置
WORKSPACE = Path("/Users/apple/.openclaw/workspace/a-stock-strategy")
DB_PATH = WORKSPACE / "a_share_historical.db"


def tonghuashun_sma(series, n: int, m: int):
    """同花顺 SMA 算法"""
    if hasattr(series, 'tolist'):
        series = series.tolist()
    elif hasattr(series, 'values'):
        series = series.tolist()
    series = list(series)
    if n <= m or len(series) == 0:
        raise ValueError("同花顺 SMA 参数需满足 N > M")
    sma_result = []
    for i in range(len(series)):
        if i == 0:
            sma_val = series[i]
        else:
            sma_val = (m * series[i] + (n - m) * sma_result[i - 1]) / n
        sma_result.append(sma_val)
    return sma_result


def sma_recursive(x: pd.Series, n: int, m: int) -> pd.Series:
    """对 pd.Series 做同花顺 SMA"""
    arr = x.astype(float).tolist()
    result = tonghuashun_sma(arr, n, m)
    return pd.Series(result, index=x.index, dtype=float)


def get_stock_kline_from_db(code: str, days: int = 120) -> pd.DataFrame:
    """从本地数据库获取股票K线"""
    conn = sqlite3.connect(DB_PATH)
    
    query = """
        SELECT date, open, high, low, close, volume, amount
        FROM kline_data
        WHERE code = ?
        ORDER BY date DESC
        LIMIT ?
    """
    
    df = pd.read_sql_query(query, conn, params=(code, days))
    conn.close()
    
    if len(df) < 30:
        return None
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    # 转换数值类型
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df


def get_all_stocks_from_db() -> list:
    """从数据库获取所有股票代码（剔除ST）"""
    # 加载股票列表（包含名称）
    stock_list_file = WORKSPACE / "a_stock_full_list.json"
    st_codes = set()
    
    if stock_list_file.exists():
        with open(stock_list_file, 'r', encoding='utf-8') as f:
            stocks = json.load(f)
        for s in stocks:
            name = s.get('name', '')
            if 'ST' in name or '退' in name:
                st_codes.add(s['code'])
        print(f"   已剔除 {len(st_codes)} 只ST股票")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT code FROM kline_data ORDER BY code")
    all_codes = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    # 过滤ST股票
    codes = [c for c in all_codes if c not in st_codes]
    return codes


def calculate_risk_coefficient_222(df: pd.DataFrame) -> pd.Series:
    """计算抄底波段222风险系数"""
    close = df['close'].astype(float)
    high = df['high'].astype(float)
    low = df['low'].astype(float)
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


def check_bottom_band_red_arrow_222(df: pd.DataFrame) -> tuple:
    """检查抄底波段222红色向上箭头"""
    if df is None or len(df) < 5:
        return False, None

    风险系数 = calculate_risk_coefficient_222(df)
    ref_风险 = 风险系数.shift(1)
    ref_low = df['low'].shift(1)

    close = df['close'].astype(float)
    open_ = df['open'].astype(float)
    low = df['low'].astype(float)

    # 成交额代理
    if 'amount' in df.columns:
        amt = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
        ref_amt = amt.shift(1)
        r_gt_0 = amt > ref_amt
    else:
        r_gt_0 = pd.Series(True, index=df.index)

    # 同花顺抄底波段222公式（成交额增加作为大单净量r>0的代理）
    # CD1: 风险<20 + 阳线 + r>0(成交额增加)
    cd1 = (风险系数 < 20) & (close > open_) & r_gt_0

    # CD2: 风险<20 + 非阳线 + 低>=昨低 + 收>低 + r>0
    cd2 = (风险系数 < 20) & (close <= open_) & (low >= ref_low) & (close > low) & r_gt_0

    # CD3: 昨风险<20 + 今风险>昨风险
    cd3 = (ref_风险 < 20) & (风险系数 > ref_风险)

    # SIGNALBUY
    signal_buy = cd1 | cd2 | cd3

    # 检查最近3天内首次出现
    if len(signal_buy) >= 3:
        recent_signals = signal_buy.tail(3)
        has_signal = recent_signals.any()
        if has_signal:
            latest_risk = 风险系数.iloc[-1]
            return True, latest_risk

    return False, None


def screen_stock(code: str) -> dict:
    """筛选单只股票"""
    try:
        df = get_stock_kline_from_db(code, days=120)
        if df is None or len(df) < 30:
            return None

        # 检查成交量（100万 = 1,000,000股，降低门槛）
        last_volume = df['volume'].iloc[-1]
        if pd.isna(last_volume) or last_volume < 1_000_000:
            return None

        # 检查红色箭头信号 + 风险系数
        has_signal, risk_coef = check_bottom_band_red_arrow_222(df)
        if not has_signal:
            return None

        # 移除风险系数限制，只看红色箭头信号
        # if risk_coef is None or pd.isna(risk_coef) or risk_coef >= 35:
        #     return None

        latest = df.iloc[-1]

        return {
            'code': code,
            'risk_coef': float(risk_coef),
            'close': float(latest['close']),
            'volume': float(latest['volume']),
            'amount': float(latest['amount']) if 'amount' in latest else 0,
        }
    except Exception as e:
        return None


def run_screening():
    """执行全量选股"""
    print("=" * 80)
    print("A股抄底波段222策略 - 本地数据库全量扫描")
    print("=" * 80)
    print(f"数据库: {DB_PATH}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 80)

    # 获取所有股票
    codes = get_all_stocks_from_db()
    total = len(codes)
    print(f"\n📊 数据库共有 {total} 只股票")
    print("🚀 开始筛选...\n")

    qualified = []
    for i, code in enumerate(codes, 1):
        if i % 500 == 0:
            print(f"   进度: {i}/{total} ({i/total*100:.1f}%) - 已选 {len(qualified)} 只")

        result = screen_stock(code)
        if result:
            qualified.append(result)
            print(f"   ✓ {code} 风险{result['risk_coef']:.1f} 价格¥{result['close']:.2f}")

    print(f"\n{'=' * 80}")
    print(f"✅ 筛选完成！共 {len(qualified)} 只股票入选")
    print(f"{'=' * 80}")

    if not qualified:
        print("当前无符合条件的股票。")
        return []

    # 保存CSV
    df = pd.DataFrame(qualified)
    df['volume_million'] = (df['volume'] / 1_000_000).round(2)
    df = df[['code', 'close', 'volume_million', 'risk_coef']]
    df = df.sort_values('risk_coef')

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path = WORKSPACE / f"qualified_stocks_bottom_band_full_{ts}.csv"
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"\n💾 结果已保存: {csv_path}")

    return qualified


def main():
    results = run_screening()

    # 打印结果
    if results:
        print("\n📋 入选股票列表:")
        for i, r in enumerate(sorted(results, key=lambda x: x['risk_coef'])[:20], 1):
            print(f"{i}. {r['code']} 风险{r['risk_coef']:.1f} ¥{r['close']:.2f} 量{r['volume']/1_000_000:.1f}M")


if __name__ == "__main__":
    main()
