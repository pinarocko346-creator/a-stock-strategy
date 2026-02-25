#!/usr/bin/env python3
"""
A股量化策略框架 - 填入你的指标

使用方法:
1. 在 calculate_indicators() 中填入你的技术指标计算
2. 在 generate_signals() 中填入你的买卖条件
3. 运行: python a_stock_template.py
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AStockStrategy:
    """
    A股策略模板 - 填入你的指标
    """
    
    def __init__(self):
        self.name = "我的A股策略"
        self.description = "填入你的策略描述"
    
    # ============================================================
    # TODO: 填入你的技术指标计算
    # ============================================================
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标
        
        参数:
            df: 包含 OHLCV 数据的 DataFrame
                - open: 开盘价
                - high: 最高价  
                - low: 最低价
                - close: 收盘价
                - volume: 成交量
        
        返回:
            添加了指标列的 DataFrame
        """
        # ========== 在这里填入你的指标计算 ==========
        
        # 示例1: 移动平均线
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma10'] = df['close'].rolling(window=10).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        
        # 示例2: MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # 示例3: RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 示例4: 布林带
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        
        # ========== 在这里填入你的自定义指标 ==========
        # 例如：
        # df['my_indicator'] = df['close'] * df['volume'] / 10000
        
        return df
    
    # ============================================================
    # TODO: 填入你的买卖条件和评分逻辑
    # ============================================================
    def generate_signals(self, df: pd.DataFrame) -> Dict:
        """
        生成交易信号和评分
        
        参数:
            df: 包含指标的数据框
        
        返回:
            {
                'signal': 'buy'/'sell'/'hold',
                'score': 0-100,
                'reasons': ['理由1', '理由2'],
                'indicators': {}
            }
        """
        if len(df) < 30:
            return {'signal': 'hold', 'score': 0, 'reasons': ['数据不足']}
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        score = 0
        reasons = []
        
        # ========== 在这里填入你的买入条件 ==========
        
        # 条件1: 均线多头排列
        if latest['close'] > latest['ma5'] > latest['ma10'] > latest['ma20']:
            score += 25
            reasons.append('均线多头排列')
        
        # 条件2: MACD金叉
        if prev['macd'] < prev['macd_signal'] and latest['macd'] > latest['macd_signal']:
            score += 20
            reasons.append('MACD金叉')
        
        # 条件3: RSI在合理区间
        if 30 < latest['rsi'] < 70:
            score += 15
            reasons.append(f'RSI正常({latest["rsi"]:.1f})')
        
        # 条件4: 突破布林带上轨（强势）
        if latest['close'] > latest['bb_upper']:
            score += 10
            reasons.append('突破布林带上轨')
        
        # 条件5: 放量上涨
        if latest['volume'] > df['volume'].rolling(20).mean().iloc[-1] * 1.5:
            score += 15
            reasons.append('放量上涨')
        
        # ========== 在这里填入你的自定义条件 ==========
        # 例如：
        # if latest['my_indicator'] > 100:
        #     score += 15
        #     reasons.append('自定义指标触发')
        
        # 确定信号
        if score >= 60:
            signal = 'buy'
        elif score <= 20:
            signal = 'sell'
        else:
            signal = 'hold'
        
        return {
            'signal': signal,
            'score': score,
            'reasons': reasons,
            'indicators': {
                'close': round(latest['close'], 2),
                'ma5': round(latest['ma5'], 2),
                'ma20': round(latest['ma20'], 2),
                'macd': round(latest['macd'], 3),
                'rsi': round(latest['rsi'], 2),
                'volume': int(latest['volume'])
            }
        }


class AStockScanner:
    """A股扫描器"""
    
    def __init__(self, strategy: AStockStrategy):
        self.strategy = strategy
        self.results = []
    
    def get_stock_list(self) -> pd.DataFrame:
        """获取A股列表"""
        logger.info("获取A股列表...")
        df = ak.stock_zh_a_spot_em()
        return df[['代码', '名称', '最新价', '涨跌幅', '换手率', '市盈率-动态']]
    
    def fetch_data(self, symbol: str, days: int = 60) -> Optional[pd.DataFrame]:
        """获取股票历史数据"""
        try:
            # 转换股票代码格式
            if symbol.startswith('6'):
                symbol_full = f"{symbol}.SH"
            else:
                symbol_full = f"{symbol}.SZ"
            
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=(datetime.now() - timedelta(days=days)).strftime('%Y%m%d'),
                end_date=datetime.now().strftime('%Y%m%d'),
                adjust="qfq"
            )
            
            if df is None or len(df) < 30:
                return None
            
            # 标准化列名
            df.columns = [col.lower().replace('-', '_') for col in df.columns]
            df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume'
            }, inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"获取 {symbol} 数据失败: {e}")
            return None
    
    def scan(self, max_stocks: int = 100) -> List[Dict]:
        """扫描股票池"""
        stock_list = self.get_stock_list()
        logger.info(f"扫描 {min(max_stocks, len(stock_list))} 只股票...")
        
        results = []
        
        for idx, row in stock_list.head(max_stocks).iterrows():
            symbol = row['代码']
            name = row['名称']
            
            # 获取数据
            df = self.fetch_data(symbol)
            if df is None:
                continue
            
            # 计算指标
            df = self.strategy.calculate_indicators(df)
            
            # 生成信号
            signal_data = self.strategy.generate_signals(df)
            
            if signal_data['score'] > 0:
                result = {
                    'symbol': symbol,
                    'name': name,
                    'signal': signal_data['signal'],
                    'score': signal_data['score'],
                    'reasons': signal_data['reasons'],
                    'indicators': signal_data['indicators'],
                    'current_price': row['最新价'],
                    'change_pct': row['涨跌幅']
                }
                results.append(result)
                
                if len(results) % 10 == 0:
                    logger.info(f"已扫描 {len(results)} 只候选股票")
        
        # 按分数排序
        results.sort(key=lambda x: x['score'], reverse=True)
        return results
    
    def generate_report(self, results: List[Dict]) -> str:
        """生成Markdown报告"""
        report_time = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        md = f"""# 📊 A股策略扫描报告

**策略名称**: {self.strategy.name}  
**扫描时间**: {report_time}  
**股票池**: 全A股  

---

## 🏆 TOP 20 推荐股票

| 排名 | 代码 | 名称 | 信号 | 评分 | 当前价 | 涨跌幅 | 触发理由 |
|------|------|------|------|------|--------|--------|----------|
"""
        
        for i, r in enumerate(results[:20], 1):
            reasons = ', '.join(r['reasons'][:3])
            md += f"| {i} | **{r['symbol']}** | {r['name']} | {r['signal']} | **{r['score']}** | {r['current_price']} | {r['change_pct']}% | {reasons} |\n"
        
        md += """
---

## 📈 详细分析

"""
        
        for i, r in enumerate(results[:10], 1):
            md += f"""### {i}. {r['symbol']} - {r['name']}
- **信号**: {r['signal']}
- **评分**: {r['score']}/100
- **当前价格**: ¥{r['current_price']} ({r['change_pct']}%)
- **触发条件**: {', '.join(r['reasons'])}
- **关键指标**:
  - 收盘价: ¥{r['indicators'].get('close', 'N/A')}
  - MA5: ¥{r['indicators'].get('ma5', 'N/A')}
  - MA20: ¥{r['indicators'].get('ma20', 'N/A')}
  - MACD: {r['indicators'].get('macd', 'N/A')}
  - RSI: {r['indicators'].get('rsi', 'N/A')}

"""
        
        md += """
---

*报告由A股策略框架自动生成*  
*免责声明: 本报告仅供参考，不构成投资建议*
"""
        
        return md


def main():
    """主函数"""
    print("="*60)
    print("A股量化策略扫描")
    print("="*60)
    
    # 创建策略实例
    strategy = AStockStrategy()
    
    # 创建扫描器
    scanner = AStockScanner(strategy)
    
    # 执行扫描
    results = scanner.scan(max_stocks=200)
    
    # 生成报告
    report = scanner.generate_report(results)
    
    # 保存报告
    filename = f"a_stock_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ 扫描完成!")
    print(f"📄 报告已保存: {filename}")
    print(f"🎯 发现 {len(results)} 只候选股票")
    
    # 打印TOP 5
    print("\n🏆 TOP 5:")
    for i, r in enumerate(results[:5], 1):
        print(f"  {i}. {r['symbol']} {r['name']} - {r['score']}分 - {r['signal']}")


if __name__ == "__main__":
    main()
