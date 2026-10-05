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
log_file = os.path.join(log_dir, 'strategies.log')
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
    """判断策略对应日期是否为 A 股交易日。

    改为查询本地 st_daily，不再调用 tushare trade_cal（1次/小时）：
    该接口一旦超限，原来会直接导致全部 8 个策略被跳过。
    本地最新交易日等于目标日，即表示"该日是交易日且日线已入库"，
    比交易日历更贴近策略的真实前提——没有当日数据时跑策略也只会得到过时结果。
    """
    day = day or datetime.date.today()
    if day.weekday() >= 5:
        logger.info("%s 是周末，跳过策略筛选", day.strftime('%Y-%m-%d'))
        return False

    date_str = day.strftime('%Y%m%d')
    try:
        db = ld.connectDB()
        try:
            cursor = db.cursor()
            cursor.execute("SELECT MAX(trade_date) FROM st_daily")
            latest = cursor.fetchone()[0]
            cursor.close()
        finally:
            db.close()
        if latest == date_str:
            return True
        logger.info("本地最新交易日为 %s，尚无 %s 的日线数据（休市或日线未更新），跳过策略筛选",
                    latest, date_str)
        return False
    except Exception as exc:
        logger.error("读取本地交易日失败，保守跳过本次策略筛选: %s", exc)
        return False


def run_all_strategies():
    """运行所有筛选策略，结果记录到日志"""
    logger.info("========== 全策略筛选开始 ==========")
    sp.ensureStocksNameColumn()

    if not is_a_share_trading_day():
        logger.info("========== 非交易日，本次策略任务结束 ==========")
        return {}

    today = datetime.date.today()
    start_date = (today - datetime.timedelta(days=30)).strftime('%Y%m%d')
    end_date = today.strftime('%Y%m%d')
    logger.info(f"筛选区间: {start_date} ~ {end_date}")

    results = {}

    # 策略1: 巨量上涨（放量>=2倍且涨超4%，之后缩量调整振幅<3%）
    logger.info("--- [1/8] 巨量上涨筛选 ---")
    try:
        r = sp.getJuliangshangzhang(startDate=start_date, endDate=end_date, multiple=2)
        results['巨量上涨'] = r
        logger.info(f"巨量上涨: {len(r)} 只")
    except Exception as e:
        logger.error(f"巨量上涨筛选失败: {e}")

    # 策略2: 向上跳空缺口
    logger.info("--- [2/8] 向上跳空缺口筛选 ---")
    try:
        r = sp.getxiangshangtiaokongquekou(startDate=start_date, endDate=end_date)
        results['向上跳空缺口'] = r
        logger.info(f"向上跳空缺口: {len(r)} 只")
    except Exception as e:
        logger.error(f"向上跳空缺口筛选失败: {e}")

    # 策略3: 跳空上涨过（含量能确认）
    logger.info("--- [3/8] 跳空上涨筛选 ---")
    try:
        r = sp.gettiaokongshangzhangguo(startDate=start_date, endDate=end_date)
        results['跳空上涨'] = r
        logger.info(f"跳空上涨: {len(r)} 只")
    except Exception as e:
        logger.error(f"跳空上涨筛选失败: {e}")

    # 策略4: 放量日（当日成交量>=前日3倍）
    logger.info("--- [4/8] 放量日筛选 ---")
    try:
        r = sp.getFangliangDay0(startDate=start_date, endDate=end_date, multiple=3)
        results['放量日'] = r
        logger.info(f"放量日: {len(r)} 只")
    except Exception as e:
        logger.error(f"放量日筛选失败: {e}")

    # 策略5: 区间涨幅超30%
    logger.info("--- [5/8] 区间涨幅筛选 ---")
    try:
        r = sp.getZhangFu(startDate=start_date, endDate=end_date, pct=30)
        results['区间涨幅30%'] = r
        logger.info(f"区间涨幅30%: {len(r)} 只")
    except Exception as e:
        logger.error(f"区间涨幅筛选失败: {e}")

    # 策略6: 最近30個交易日平緩上漲且漲幅超過30%
    logger.info("--- [6/8] 30日平緩上漲篩選 ---")
    try:
        r = sp.getSmoothUptrend(trading_days=30, min_gain_pct=30)
        results['30日平緩上漲30%'] = r
        logger.info(f"30日平緩上漲30%: {len(r)} 只")
    except Exception as e:
        logger.error(f"30日平緩上漲篩選失敗: {e}")

    # 策略7: 最近10个交易日内的上升旗形（急涨旗杆 + 缩量下倾整理）
    logger.info("--- [7/8] 10日上升旗形筛选 ---")
    try:
        r = sp.getBullFlag(trading_days=10)
        results['10日上升旗形'] = r
        logger.info(f"10日上升旗形: {len(r)} 只")
    except Exception as e:
        logger.error(f"10日上升旗形筛选失敗: {e}")

    # 策略8: 小旗杆（放量大涨日后3~5天缩量整理且不破首日开盘+3%）
    logger.info("--- [8/8] 小旗杆筛选 ---")
    try:
        r = sp.getSmallPole()
        results['小旗杆'] = r
        logger.info(f"小旗杆: {len(r)} 只")
    except Exception as e:
        logger.error(f"小旗杆筛选失败: {e}")

    # 汇总输出
    logger.info("========== 策略筛选结果汇总 ==========")
    total = 0
    for name, stocks in results.items():
        count = len(stocks) if stocks else 0
        total += count
        logger.info(f"  {name}: {count} 只")
        if stocks:
            for s in stocks[:20]:
                logger.info(f"    {s}")
            if count > 20:
                logger.info(f"    ... 共 {count} 只，仅显示前20只")
    logger.info(f"  合计信号数: {total}")
    logger.info("========== 全策略筛选完成 ==========")

    return results


if __name__ == '__main__':
    run_all_strategies()
