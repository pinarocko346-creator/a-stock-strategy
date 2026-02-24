"""
策略基类模块
定义所有策略必须实现的接口
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    STRONG_BUY = "strong_buy"
    STRONG_SELL = "strong_sell"
    WATCH = "watch"


@dataclass
class Signal:
    """交易信号数据类"""
    symbol: str
    signal_type: SignalType
    date: pd.Timestamp
    price: float
    score: float = 0.0  # 信号强度评分 0-100
    indicators: Dict[str, Any] = None  # 相关指标值
    reason: str = ""  # 信号原因说明
    
    def __post_init__(self):
        if self.indicators is None:
            self.indicators = {}
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'signal_type': self.signal_type.value,
            'date': self.date.strftime('%Y-%m-%d'),
            'price': round(self.price, 3),
            'score': round(self.score, 2),
            'indicators': self.indicators,
            'reason': self.reason
        }


class BaseStrategy(ABC):
    """
    策略基类
    
    所有自定义策略必须继承此类，并实现以下抽象方法：
    - calculate_indicators: 计算技术指标
    - generate_signals: 生成交易信号
    
    使用示例:
        class MyStrategy(BaseStrategy):
            def calculate_indicators(self, df):
                # 计算指标
                df['ma20'] = df['close'].rolling(20).mean()
                return df
            
            def generate_signals(self, df):
                # 生成信号
                signals = []
                # ... 信号逻辑 ...
                return signals
    """
    
    def __init__(self, name: str = "BaseStrategy", config: Dict = None):
        """
        初始化策略
        
        Args:
            name: 策略名称
            config: 策略配置参数
        """
        self.name = name
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.{name}")
        
        # 默认参数（子类可覆盖）
        self.min_data_days = self.config.get('min_data_days', 60)
        self.min_score_threshold = self.config.get('min_score_threshold', 50)
    
    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标
        
        TODO: 用户需要重写这个方法，添加自己的指标计算逻辑
        
        Args:
            df: 原始数据DataFrame，包含OHLCV列
                - open: 开盘价
                - close: 收盘价
                - high: 最高价
                - low: 最低价
                - volume: 成交量
        
        Returns:
            DataFrame: 添加了指标列的数据
        """
        pass
    
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> List[Signal]:
        """
        生成交易信号
        
        TODO: 用户需要重写这个方法，实现自己的信号生成逻辑
        
        Args:
            df: 包含指标的数据DataFrame（由calculate_indicators处理后的数据）
        
        Returns:
            List[Signal]: 信号列表
        """
        pass
    
    def analyze(self, df: pd.DataFrame, symbol: str) -> Tuple[pd.DataFrame, List[Signal]]:
        """
        执行完整分析流程
        
        Args:
            df: 原始数据
            symbol: 股票代码
        
        Returns:
            Tuple[DataFrame, List[Signal]]: (处理后的数据, 信号列表)
        """
        # 数据检查
        if df is None or len(df) < self.min_data_days:
            self.logger.warning(f"{symbol} 数据不足 {self.min_data_days} 天")
            return df, []
        
        # 确保必要的列存在
        required_cols = ['open', 'close', 'high', 'low', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            self.logger.error(f"{symbol} 缺少必要列: {missing_cols}")
            return df, []
        
        try:
            # 1. 计算指标
            df_with_indicators = self.calculate_indicators(df.copy())
            
            # 2. 生成信号
            signals = self.generate_signals(df_with_indicators)
            
            # 3. 过滤低分信号
            signals = [s for s in signals if s.score >= self.min_score_threshold]
            
            # 4. 按评分排序
            signals.sort(key=lambda x: x.score, reverse=True)
            
            return df_with_indicators, signals
            
        except Exception as e:
            self.logger.error(f"分析 {symbol} 时出错: {e}")
            return df, []
    
    def get_latest_signal(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        """
        获取最新一个信号
        
        Args:
            df: 原始数据
            symbol: 股票代码
        
        Returns:
            Signal or None: 最新信号
        """
        _, signals = self.analyze(df, symbol)
        
        if not signals:
            return None
        
        # 返回最新的信号
        latest = max(signals, key=lambda x: x.date)
        return latest
    
    def validate_data(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        验证数据是否满足策略要求
        
        Args:
            df: 待验证的数据
        
        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        if df is None:
            return False, "数据为空"
        
        if len(df) < self.min_data_days:
            return False, f"数据不足 {self.min_data_days} 天"
        
        required_cols = ['open', 'close', 'high', 'low', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            return False, f"缺少必要列: {missing_cols}"
        
        # 检查是否有NaN值
        if df[required_cols].isnull().any().any():
            return False, "数据包含空值"
        
        return True, "数据有效"
    
    def batch_analyze(
        self, 
        data_dict: Dict[str, pd.DataFrame]
    ) -> Dict[str, Dict]:
        """
        批量分析多只股票
        
        Args:
            data_dict: {symbol: DataFrame}
        
        Returns:
            Dict: 分析结果
        """
        results = {}
        
        for symbol, df in data_dict.items():
            try:
                df_processed, signals = self.analyze(df, symbol)
                
                results[symbol] = {
                    'success': True,
                    'data': df_processed,
                    'signals': signals,
                    'latest_signal': signals[0] if signals else None,
                    'signal_count': len(signals)
                }
                
            except Exception as e:
                self.logger.error(f"批量分析 {symbol} 失败: {e}")
                results[symbol] = {
                    'success': False,
                    'error': str(e)
                }
        
        return results
    
    def __str__(self) -> str:
        return f"{self.name}(min_days={self.min_data_days}, threshold={self.min_score_threshold})"
    
    def __repr__(self) -> str:
        return self.__str__()


# 辅助函数
def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算ATR（平均真实波幅）"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    return atr


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """计算RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_macd(
    prices: pd.Series, 
    fast: int = 12, 
    slow: int = 26, 
    signal: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """计算MACD
    
    Returns:
        Tuple: (macd_line, signal_line, histogram)
    """
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def calculate_bollinger_bands(
    prices: pd.Series, 
    period: int = 20, 
    std_dev: float = 2.0
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """计算布林带
    
    Returns:
        Tuple: (upper, middle, lower)
    """
    middle = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    return upper, middle, lower
