#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "akshare>=1.15.0",
#     "pandas>=2.0.0",
#     "numpy>=1.24.0",
# ]
# ///

"""
A股全量历史数据获取脚本 - 用于抄底波段222策略回测
获取所有A股的日线数据，保存到本地数据库
"""

import os
import sys
import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

# 禁用代理
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

import pandas as pd
import akshare as ak

# 配置
WORKSPACE = Path("/Users/apple/.openclaw/workspace/a-stock-strategy")
DB_PATH = WORKSPACE / "a_share_historical.db"
STOCK_LIST_FILE = WORKSPACE / "a_stock_full_list.json"

# 获取多少天的历史数据（默认90天=3个月）
DAYS_OF_HISTORY = 90


def init_database():
    """初始化SQLite数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 创建K线数据表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS kline_data (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            amount REAL,
            amplitude REAL,
            pct_chg REAL,
            change REAL,
            turnover REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (code, date)
        )
    ''')
    
    # 创建股票列表表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_list (
            code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            list_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建更新日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS update_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            status TEXT,
            message TEXT,
            records_count INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ 数据库初始化完成: {DB_PATH}")


def load_stock_list():
    """加载股票列表"""
    if STOCK_LIST_FILE.exists():
        with open(STOCK_LIST_FILE, 'r', encoding='utf-8') as f:
            stocks = json.load(f)
        print(f"📁 从文件加载 {len(stocks)} 只股票")
        return stocks
    
    # 如果没有文件，从akshare获取
    print("🔄 从akshare获取股票列表...")
    df = ak.stock_info_a_code_name()
    stocks = df.to_dict('records')
    
    # 保存到文件
    with open(STOCK_LIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(stocks, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 获取到 {len(stocks)} 只股票")
    return stocks


def save_stock_list_to_db(stocks):
    """保存股票列表到数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for stock in stocks:
        cursor.execute('''
            INSERT OR REPLACE INTO stock_list (code, name, updated_at)
            VALUES (?, ?, ?)
        ''', (stock['code'], stock.get('name', ''), datetime.now()))
    
    conn.commit()
    conn.close()
    print(f"✅ 股票列表已保存到数据库: {len(stocks)} 只")


def get_stock_kline_akshare(code, start_date, end_date):
    """使用akshare获取单只股票的历史K线"""
    try:
        # 根据代码前缀判断交易所
        if code.startswith('6'):
            # 上海
            df = ak.stock_zh_a_hist(
                symbol=code, 
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"  # 前复权
            )
        else:
            # 深圳/北京
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily", 
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
        
        if df is None or len(df) == 0:
            return None
        
        # 标准化列名
        df = df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
            '振幅': 'amplitude',
            '涨跌幅': 'pct_chg',
            '涨跌额': 'change',
            '换手率': 'turnover'
        })
        
        df['code'] = code
        return df
        
    except Exception as e:
        print(f"  ❌ 获取 {code} 失败: {e}")
        return None


def save_kline_to_db(code, df):
    """保存K线数据到数据库"""
    if df is None or len(df) == 0:
        return 0
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    count = 0
    for _, row in df.iterrows():
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO kline_data 
                (code, date, open, high, low, close, volume, amount, 
                 amplitude, pct_chg, change, turnover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                code,
                str(row['date']),
                float(row['open']) if pd.notna(row['open']) else None,
                float(row['high']) if pd.notna(row['high']) else None,
                float(row['low']) if pd.notna(row['low']) else None,
                float(row['close']) if pd.notna(row['close']) else None,
                float(row['volume']) if pd.notna(row['volume']) else None,
                float(row['amount']) if pd.notna(row['amount']) else None,
                float(row['amplitude']) if 'amplitude' in row and pd.notna(row['amplitude']) else None,
                float(row['pct_chg']) if 'pct_chg' in row and pd.notna(row['pct_chg']) else None,
                float(row['change']) if 'change' in row and pd.notna(row['change']) else None,
                float(row['turnover']) if 'turnover' in row and pd.notna(row['turnover']) else None
            ))
            count += 1
        except Exception as e:
            print(f"  保存 {code} {row['date']} 失败: {e}")
    
    conn.commit()
    conn.close()
    return count


def log_update(code, status, message, records_count=0):
    """记录更新日志"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO update_log (code, status, message, records_count)
        VALUES (?, ?, ?, ?)
    ''', (code, status, message, records_count))
    conn.commit()
    conn.close()


def fetch_all_historical_data(batch_size=100, delay=0.5):
    """获取所有股票的历史数据"""
    # 计算日期范围
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=DAYS_OF_HISTORY)).strftime('%Y%m%d')
    
    print(f"📅 数据范围: {start_date} 至 {end_date} ({DAYS_OF_HISTORY}天)")
    
    # 加载股票列表
    stocks = load_stock_list()
    total = len(stocks)
    
    print(f"\n🚀 开始获取 {total} 只股票的历史数据...")
    print(f"⏱️ 预计耗时: {total * delay / 60:.1f} 分钟\n")
    
    success_count = 0
    fail_count = 0
    total_records = 0
    
    for i, stock in enumerate(stocks, 1):
        code = stock['code']
        name = stock.get('name', '')
        
        if i % batch_size == 0 or i == 1:
            print(f"\n📊 进度: {i}/{total} ({i/total*100:.1f}%) - 成功:{success_count} 失败:{fail_count}")
        
        try:
            # 获取K线数据
            df = get_stock_kline_akshare(code, start_date, end_date)
            
            if df is not None and len(df) > 0:
                # 保存到数据库
                records = save_kline_to_db(code, df)
                total_records += records
                success_count += 1
                log_update(code, 'success', f'获取 {records} 条记录', records)
                print(f"  ✓ {code} {name[:8]:<8} ({records}条)")
            else:
                fail_count += 1
                log_update(code, 'empty', '无数据返回')
                print(f"  ⚠ {code} {name[:8]:<8} 无数据")
                
        except Exception as e:
            fail_count += 1
            log_update(code, 'error', str(e))
            print(f"  ❌ {code} {name[:8]:<8} 错误: {e}")
        
        # 延迟避免被封
        time.sleep(delay)
    
    print(f"\n{'='*60}")
    print(f"✅ 数据获取完成!")
    print(f"  成功: {success_count} 只")
    print(f"  失败: {fail_count} 只")
    print(f"  总记录: {total_records:,} 条")
    print(f"  数据库: {DB_PATH}")
    print(f"{'='*60}")


def get_db_stats():
    """获取数据库统计信息"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 股票数量
    cursor.execute("SELECT COUNT(DISTINCT code) FROM kline_data")
    stock_count = cursor.fetchone()[0]
    
    # 总记录数
    cursor.execute("SELECT COUNT(*) FROM kline_data")
    total_records = cursor.fetchone()[0]
    
    # 日期范围
    cursor.execute("SELECT MIN(date), MAX(date) FROM kline_data")
    date_range = cursor.fetchone()
    
    # 最近更新
    cursor.execute("SELECT COUNT(*) FROM update_log WHERE updated_at > datetime('now', '-1 day')")
    recent_updates = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n📊 数据库统计:")
    print(f"  股票数量: {stock_count}")
    print(f"  总记录数: {total_records:,}")
    print(f"  日期范围: {date_range[0]} ~ {date_range[1]}")
    print(f"  今日更新: {recent_updates}")


def main():
    print("="*60)
    print("A股全量历史数据获取工具")
    print("="*60)
    
    # 初始化数据库
    init_database()
    
    # 检查参数
    if len(sys.argv) > 1:
        if sys.argv[1] == 'stats':
            get_db_stats()
            return
        elif sys.argv[1] == 'update':
            # 只更新最近几天的数据
            print("🔄 增量更新模式（待实现）")
            return
    
    # 保存股票列表
    stocks = load_stock_list()
    save_stock_list_to_db(stocks)
    
    # 获取历史数据
    fetch_all_historical_data(batch_size=100, delay=0.5)
    
    # 显示统计
    get_db_stats()


if __name__ == "__main__":
    main()
