"""
A股数据获取模块
使用akshare获取A股数据，支持数据缓存
"""
import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Union
import pandas as pd
import akshare as ak

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataFetcher:
    """A股数据获取器，支持缓存机制"""
    
    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._stock_list_cache = None
        self._stock_list_cache_time = None
        
    def _get_cache_key(self, prefix: str, params: dict) -> str:
        """生成缓存键"""
        param_str = json.dumps(params, sort_keys=True)
        return f"{prefix}_{hashlib.md5(param_str.encode()).hexdigest()[:12]}"
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{cache_key}.pkl"
    
    def _load_from_cache(self, cache_key: str, max_age_hours: int = 24) -> Optional[pd.DataFrame]:
        """从缓存加载数据"""
        cache_path = self._get_cache_path(cache_key)
        
        if not cache_path.exists():
            return None
        
        # 检查缓存是否过期
        cache_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - cache_time > timedelta(hours=max_age_hours):
            logger.info(f"缓存已过期: {cache_key}")
            return None
        
        try:
            logger.info(f"从缓存加载: {cache_key}")
            return pd.read_pickle(cache_path)
        except Exception as e:
            logger.warning(f"读取缓存失败: {e}")
            return None
    
    def _save_to_cache(self, cache_key: str, df: pd.DataFrame):
        """保存数据到缓存"""
        cache_path = self._get_cache_path(cache_key)
        try:
            df.to_pickle(cache_path)
            logger.info(f"数据已缓存: {cache_key}")
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")
    
    def get_stock_list(self, use_cache: bool = True) -> pd.DataFrame:
        """
        获取全A股股票列表
        
        Returns:
            DataFrame: 包含股票代码、名称等信息
        """
        # 内存缓存检查
        if use_cache and self._stock_list_cache is not None:
            if datetime.now() - self._stock_list_cache_time < timedelta(hours=24):
                return self._stock_list_cache
        
        cache_key = "stock_list_all"
        
        if use_cache:
            cached = self._load_from_cache(cache_key, max_age_hours=24)
            if cached is not None:
                self._stock_list_cache = cached
                self._stock_list_cache_time = datetime.now()
                return cached
        
        try:
            logger.info("正在获取A股股票列表...")
            # 获取上海和深圳A股
            df_sh = ak.stock_info_sh_name_code()
            df_sz = ak.stock_info_sz_name_code()
            
            # 标准化列名
            df_sh = df_sh[['证券代码', '证券简称']].copy()
            df_sh.columns = ['代码', '名称']
            df_sh['市场'] = 'SH'
            
            df_sz = df_sz[['A股代码', 'A股简称']].copy()
            df_sz.columns = ['代码', '名称']
            df_sz['市场'] = 'SZ'
            
            # 合并
            df = pd.concat([df_sh, df_sz], ignore_index=True)
            
            # 过滤ST股票和科创板（可选）
            df = df[~df['名称'].str.contains('ST|退市', na=False)]
            
            # 添加完整代码
            df['完整代码'] = df['市场'] + df['代码']
            
            if use_cache:
                self._save_to_cache(cache_key, df)
                self._stock_list_cache = df
                self._stock_list_cache_time = datetime.now()
            
            logger.info(f"成功获取 {len(df)} 只股票")
            return df
            
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            raise
    
    def get_daily_data(
        self, 
        symbol: str, 
        period: str = "daily",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: str = "qfq",  # 前复权
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        获取股票日线数据
        
        Args:
            symbol: 股票代码（如 '000001' 或 'SH000001'）
            period: 周期 (daily/weekly/monthly)
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            adjust: 复权方式 (qfq-前复权, hfq-后复权, 空-不复权)
            use_cache: 是否使用缓存
        
        Returns:
            DataFrame: 包含OHLCV数据
        """
        # 标准化代码
        symbol = symbol.upper().replace('SH', '').replace('SZ', '')
        
        # 默认日期范围
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')
        if start_date is None:
            start = datetime.now() - timedelta(days=365)
            start_date = start.strftime('%Y%m%d')
        
        cache_params = {
            'symbol': symbol,
            'period': period,
            'start': start_date,
            'end': end_date,
            'adjust': adjust
        }
        cache_key = self._get_cache_key("daily", cache_params)
        
        if use_cache:
            cached = self._load_from_cache(cache_key, max_age_hours=6)  # 日线数据6小时缓存
            if cached is not None:
                return cached
        
        try:
            logger.debug(f"获取 {symbol} 的日线数据...")
            
            # 使用akshare获取数据
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust
            )
            
            if df is None or df.empty:
                logger.warning(f"{symbol} 无数据")
                return pd.DataFrame()
            
            # 标准化列名
            df.columns = [col.lower() for col in df.columns]
            
            # 确保日期列是datetime类型
            df['日期'] = pd.to_datetime(df['日期'])
            df.set_index('日期', inplace=True)
            
            # 添加股票代码
            df['symbol'] = symbol
            
            if use_cache:
                self._save_to_cache(cache_key, df)
            
            return df
            
        except Exception as e:
            logger.error(f"获取 {symbol} 数据失败: {e}")
            return pd.DataFrame()
    
    def get_fundamental_data(self, symbol: str, use_cache: bool = True) -> Dict:
        """
        获取股票基本面数据
        
        Args:
            symbol: 股票代码
            use_cache: 是否使用缓存
        
        Returns:
            Dict: 包含市盈率、市净率、市值等数据
        """
        symbol = symbol.upper().replace('SH', '').replace('SZ', '')
        
        cache_key = self._get_cache_key("fundamental", {'symbol': symbol})
        
        if use_cache:
            cached = self._load_from_cache(cache_key, max_age_hours=24)
            if cached is not None:
                return cached.to_dict('records')[0] if not cached.empty else {}
        
        try:
            logger.debug(f"获取 {symbol} 基本面数据...")
            
            # 获取个股信息
            df = ak.stock_individual_info_em(symbol=symbol)
            
            if df is None or df.empty:
                return {}
            
            # 转换为字典
            info = dict(zip(df['item'], df['value']))
            
            # 提取关键指标
            result = {
                'symbol': symbol,
                'name': info.get('股票简称', ''),
                'pe_ttm': self._safe_float(info.get('市盈率-动态')),
                'pb': self._safe_float(info.get('市净率')),
                'total_market_cap': self._safe_float(info.get('总市值')),
                'float_market_cap': self._safe_float(info.get('流通市值')),
                'turnover': self._safe_float(info.get('换手率')),
                'industry': info.get('行业', ''),
            }
            
            if use_cache:
                self._save_to_cache(cache_key, pd.DataFrame([result]))
            
            return result
            
        except Exception as e:
            logger.error(f"获取 {symbol} 基本面数据失败: {e}")
            return {}
    
    def get_batch_data(
        self, 
        symbols: List[str], 
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_data_days: int = 60
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取多只股票数据
        
        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            min_data_days: 最小数据天数要求
        
        Returns:
            Dict: {symbol: DataFrame}
        """
        results = {}
        
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"[{i}/{len(symbols)}] 获取 {symbol} 数据...")
            
            try:
                df = self.get_daily_data(symbol, start_date=start_date, end_date=end_date)
                
                if len(df) >= min_data_days:
                    results[symbol] = df
                else:
                    logger.warning(f"{symbol} 数据不足 {min_data_days} 天，跳过")
                    
            except Exception as e:
                logger.error(f"获取 {symbol} 失败: {e}")
                continue
        
        logger.info(f"成功获取 {len(results)}/{len(symbols)} 只股票数据")
        return results
    
    def clear_cache(self, older_than_hours: Optional[int] = None):
        """
        清理缓存文件
        
        Args:
            older_than_hours: 清理超过指定小时数的缓存，None则清理全部
        """
        try:
            count = 0
            for cache_file in self.cache_dir.glob("*.pkl"):
                if older_than_hours is not None:
                    file_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
                    if file_age <= timedelta(hours=older_than_hours):
                        continue
                
                cache_file.unlink()
                count += 1
            
            logger.info(f"已清理 {count} 个缓存文件")
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
    
    @staticmethod
    def _safe_float(value, default=0.0):
        """安全转换为浮点数"""
        try:
            if value is None or value == '-':
                return default
            # 处理带单位的值（如"1.2亿"）
            if isinstance(value, str):
                value = value.replace('亿', 'e8').replace('万', 'e4')
            return float(value)
        except:
            return default


# 便捷函数
def fetch_stock_list() -> pd.DataFrame:
    """获取股票列表（便捷函数）"""
    fetcher = DataFetcher()
    return fetcher.get_stock_list()


def fetch_daily_data(symbol: str, **kwargs) -> pd.DataFrame:
    """获取日线数据（便捷函数）"""
    fetcher = DataFetcher()
    return fetcher.get_daily_data(symbol, **kwargs)


if __name__ == "__main__":
    # 测试
    fetcher = DataFetcher()
    
    # 测试股票列表
    stocks = fetcher.get_stock_list()
    print(f"股票列表: {len(stocks)} 只")
    print(stocks.head())
    
    # 测试日线数据
    df = fetcher.get_daily_data('000001', start_date='20240101')
    print(f"\n平安银行数据: {len(df)} 条")
    print(df.head())
    
    # 测试基本面数据
    fund = fetcher.get_fundamental_data('000001')
    print(f"\n基本面数据:")
    print(fund)
