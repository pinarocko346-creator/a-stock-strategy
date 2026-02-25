"""
诊断「选股结果为 0」：逐条件统计通过数量，并检查数据是否正常。
用法: cd a-stock-strategy && python debug_screen_zero.py
"""
import os
os.environ.setdefault('NO_PROXY', '*')
os.environ.setdefault('no_proxy', '*')

import pandas as pd

def run_a_debug():
    """A 股：抽 80 只检查数据 + 三条件通过数"""
    print("=" * 60)
    print("A 股诊断（抄底波段222）")
    print("=" * 60)
    try:
        import akshare as ak
        from stock_screener_bottom_band import (
            StockScreenerBottomBand,
            sma_recursive,
        )
    except Exception as e:
        print(f"导入失败: {e}")
        return

    screener = StockScreenerBottomBand(use_big_order_proxy=True)
    try:
        info = ak.stock_info_a_code_name()
        codes = info['code'].tolist()[:80]
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        codes = ['000001', '600519', '000858', '002594']

    pass_1 = pass_2 = pass_3 = pass_all = 0
    data_ok = 0
    for i, code in enumerate(codes):
        df = screener.get_stock_kline(code, period='daily', count=120)
        if df is None or len(df) < 30:
            continue
        if not all(c in df.columns for c in ['close', 'high', 'low', 'open']):
            continue
        data_ok += 1

        c1 = screener.check_bottom_band_red_arrow_222(df)
        if c1:
            pass_1 += 1

        风险系数 = screener.calculate_risk_coefficient_222(df)
        c2 = (pd.notna(风险系数.iloc[-1]) and 风险系数.iloc[-1] < 20)
        if c2:
            pass_2 += 1

        k, d, j = screener.calculate_kdj(df)
        c3 = screener.check_kdj_golden_cross_below_20(k, d, threshold=20)
        if c3:
            pass_3 += 1

        if c1 and c2 and c3:
            pass_all += 1
            print(f"  全过: {code} 风险={风险系数.iloc[-1]:.1f} K={k.iloc[-1]:.1f} D={d.iloc[-1]:.1f}")

    print(f"\n数据有效: {data_ok}/{len(codes)} 只")
    print(f"通过条件1(红箭头): {pass_1}")
    print(f"通过条件2(风险<20): {pass_2}")
    print(f"通过条件3(KDJ20下金叉): {pass_3}")
    print(f"三条件全过: {pass_all}")
    if pass_3 == 0 and pass_2 > 0:
        print("\n→ 建议: 条件3(KDJ 20下方金叉)过严，可改为 30 下方金叉或放宽为「近期金叉」")
    return pass_all


def run_us_debug():
    """美股：抽 50 只检查"""
    print("\n" + "=" * 60)
    print("美股诊断（抄底波段222）")
    print("=" * 60)
    try:
        from us_stock_screener_bottom_band import USStockScreenerBottomBand
        from us_stock_data_fetcher import get_us_stock_list_default, get_us_daily_ohlcv
    except Exception as e:
        print(f"导入失败: {e}")
        return

    symbols = get_us_stock_list_default()[:50]
    screener = USStockScreenerBottomBand(use_big_order_proxy=True)
    pass_1 = pass_2 = pass_3 = pass_all = 0
    data_ok = 0
    for sym in symbols:
        df = get_us_daily_ohlcv(sym, period='6mo', count=120)
        if df is None or len(df) < 30:
            continue
        if not all(c in df.columns for c in ['close', 'high', 'low', 'open']):
            continue
        data_ok += 1

        c1 = screener.check_bottom_band_red_arrow_222(df)
        if c1:
            pass_1 += 1
        风险系数 = screener.calculate_risk_coefficient_222(df)
        c2 = (pd.notna(风险系数.iloc[-1]) and 风险系数.iloc[-1] < 20)
        if c2:
            pass_2 += 1
        k, d, j = screener.calculate_kdj(df)
        c3 = screener.check_kdj_golden_cross_below_20(k, d, threshold=20)
        if c3:
            pass_3 += 1
        if c1 and c2 and c3:
            pass_all += 1
            print(f"  全过: {sym} 风险={风险系数.iloc[-1]:.1f} K={k.iloc[-1]:.1f} D={d.iloc[-1]:.1f}")

    print(f"\n数据有效: {data_ok}/{len(symbols)} 只")
    print(f"通过条件1(红箭头): {pass_1}")
    print(f"通过条件2(风险<20): {pass_2}")
    print(f"通过条件3(KDJ20下金叉): {pass_3}")
    print(f"三条件全过: {pass_all}")
    if pass_3 == 0 and pass_2 > 0:
        print("\n→ 建议: 条件3 过严，可改为 KDJ 30 下方金叉")
    return pass_all


if __name__ == "__main__":
    run_a_debug()
    run_us_debug()
    print("\n诊断结束")
