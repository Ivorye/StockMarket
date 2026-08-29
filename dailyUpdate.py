import datetime
import logging
import os
import sys

import tushare as ts

import loadStocks as ld
import stockPolicy as sp

# 创建logs目录
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

# 配置日志：同时输出到文件和控制台
log_file = os.path.join(log_dir, 'daily_update.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def is_a_share_trading_day(day=None):
    """判断指定日期是否为 A 股交易日；日历不可用时保守返回 False。"""
    day = day or datetime.date.today()
    if day.weekday() >= 5:
        logger.info("%s 是周末，跳过股票数据更新", day.strftime('%Y-%m-%d'))
        return False

    date_str = day.strftime('%Y%m%d')
    try:
        pro = ts.pro_api(ld.TUSHARE_TOKEN)
        calendar = pro.trade_cal(
            exchange='SSE', start_date=date_str, end_date=date_str,
            fields='cal_date,is_open')
        if calendar is None or calendar.empty:
            logger.warning("未取得 %s 的交易日历，保守跳过本次更新", date_str)
            return False
        is_open = int(calendar.iloc[0]['is_open']) == 1
        if not is_open:
            logger.info("%s 是 A 股休市日，跳过股票数据更新", day.strftime('%Y-%m-%d'))
        return is_open
    except Exception as exc:
        logger.error("查询 %s 交易日历失败，保守跳过本次更新: %s", date_str, exc)
        return False


def run_daily_update():
    """每日数据更新流程：获取股票列表（优先DB）→ 载入总表 → 为新股建表 → 加载近期日线数据"""
    logger.info("========== 每日数据更新开始 ==========")

    if not is_a_share_trading_day():
        logger.info("========== 非交易日，本次任务结束 ==========")
        return

    # 步骤1：获取股票列表（优先从数据库读取，避免消耗stock_basic API配额）
    logger.info("[1/6] 获取股票列表...")
    try:
        df = ld.getStockBasic()
        logger.info(f"从API获取到 {len(df)} 只股票基本信息")
    except Exception as e:
        logger.error(f"getStockBasic 执行失败: {e}")
        return

    # 步骤2：将所有股票基本信息载入总表
    logger.info("[2/6] 载入股票基本信息到总表 (loadAllBasic)...")
    try:
        ld.loadAllBasic(df)
        logger.info("股票基本信息载入完成")
    except Exception as e:
        logger.error(f"loadAllBasic 执行失败: {e}")
        return

    # 步骤3：确保统一日线表存在
    logger.info("[3/6] 确保 st_daily 日线表存在...")
    try:
        ld.createStockTable(df)
        logger.info("st_daily 表检查完成")
    except Exception as e:
        logger.error(f"createStockTable 执行失败: {e}")
        return

    # 步骤4：增量加载日线数据（只补缺失天数，已存在的记录会跳过）
    logger.info("[4/6] 增量加载日线数据...")
    try:
        ld.incrementalUpdateDailyData(df, lookback_days=30)
        logger.info("日线数据加载完成")
    except Exception as e:
        logger.error(f"日线数据加载失败: {e}")
        return

    # 步骤5：确认统一日线表可用（步骤4已直接写入）
    logger.info("[5/6] 检查 st_daily 日线表...")
    try:
        sp.createDailyTable()
        sp.buildDailyTable()
        logger.info("st_daily汇总完成")
    except Exception as e:
        logger.error(f"st_daily汇总失败: {e}")
        return

    # 步骤6：执行放量涨幅筛选
    logger.info("[6/6] 执行放量涨幅筛选...")
    try:
        sp.createSignalTable()
        result = sp.getLiangJiaFangLiang()
        logger.info(f"放量涨幅筛选完成，命中 {len(result)} 只股票")
    except Exception as e:
        logger.error(f"放量涨幅筛选失败: {e}")

    logger.info("========== 每日数据更新完成 ==========")


if __name__ == '__main__':
    run_daily_update()
