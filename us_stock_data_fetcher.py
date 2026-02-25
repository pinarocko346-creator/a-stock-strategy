"""
美股数据获取模块
使用 yfinance 获取美股日线，列名与 A 股模块对齐（open/close/high/low/volume/amount）
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None


def get_us_daily_ohlcv(
    symbol: str,
    period: str = "6mo",
    count: Optional[int] = 120,
) -> Optional[pd.DataFrame]:
    """
    获取美股日线 K 线，列名统一为小写：date, open, close, high, low, volume, amount。
    amount 用 close * volume 近似，供大单代理等逻辑使用。
    """
    if yf is None:
        raise ImportError("请安装 yfinance: pip install yfinance")

    ticker = symbol if isinstance(symbol, str) else str(symbol)
    # yfinance 需要标准代码，如 AAPL、MSFT
    if "." in ticker:
        ticker = ticker.split(".")[0].strip().upper()
    else:
        ticker = ticker.strip().upper()

    try:
        obj = yf.Ticker(ticker)
        # period: 1mo, 3mo, 6mo, 1y, 2y 等
        df = obj.history(period=period, interval="1d", auto_adjust=True)
        if df is None or len(df) == 0:
            return None

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        # 列名映射：Date -> date, Open -> open, Close -> close, High -> high, Low -> low, Volume -> volume
        rename = {"date": "date", "open": "open", "close": "close", "high": "high", "low": "low", "volume": "volume"}
        for k, v in list(rename.items()):
            if v in df.columns and k != v:
                df = df.rename(columns={v: k})
        if "date" not in df.columns and "datetime" in df.columns:
            df = df.rename(columns={"datetime": "date"})
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        if "amount" not in df.columns and "close" in df.columns and "volume" in df.columns:
            df["amount"] = (df["close"] * df["volume"]).astype(float)

        for col in ["open", "close", "high", "low", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if count:
            df = df.tail(count).reset_index(drop=True)
        return df
    except Exception as e:
        logger.warning(f"获取 {ticker} 日线失败: {e}")
        return None


def get_us_stock_list_default() -> List[str]:
    """
    默认美股池：常见标的（可替换为从文件或 API 拉取全市场）。
    """
    return [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "JPM", "V",
        "JNJ", "WMT", "PG", "MA", "HD", "DIS", "PYPL", "BAC", "XOM", "UNH",
        "ADBE", "CRM", "NFLX", "CSCO", "PEP", "KO", "INTC", "CMCSA", "ABT", "COST",
        "AVGO", "TMO", "NEE", "DHR", "ACN", "NKE", "PM", "TXN", "BMY", "HON",
        "AMGN", "ORCL", "LOW", "UPS", "RTX", "QCOM", "INTU", "SPGI", "CAT", "AXP",
        "AMAT", "DE", "BKNG", "SBUX", "GILD", "MDLZ", "ADI", "LMT", "CVX", "C",
        "BLK", "PLD", "SYK", "REGN", "MMC", "CI", "SO", "ZTS", "DUK", "BDX",
        "EOG", "MO", "BSX", "APD", "SLB", "EQIX", "CL", "WM", "APTV", "ITW",
        "HCA", "ETN", "KLAC", "PSA", "SHW", "FIS", "PSX", "ECL", "MPC", "GM",
        "FCX", "NOC", "AON", "CME", "ICE", "USB", "PGR", "GD", "MET", "AIG",
    ]


def load_us_symbols_from_file(path: str) -> List[str]:
    """从文本文件读取股票代码列表，每行一个代码。"""
    p = Path(path)
    if not p.exists():
        return []
    symbols = []
    for line in p.read_text(encoding="utf-8").strip().splitlines():
        s = line.strip().upper()
        if s and not s.startswith("#"):
            symbols.append(s.split()[0] if s.split() else s)
    return symbols
