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
    """判断策略对应日期是否为 A 股交易日。"""
    day = day or datetime.date.today()
    if day.weekday() >= 5:
        logger.info("%s 是周末，跳过策略筛选", day.strftime('%Y-%m-%d'))
        return False

    date_str = day.strftime('%Y%m%d')
    try:
        pro = ts.pro_api(ld.TUSHARE_TOKEN)
        calendar = pro.trade_cal(
            exchange='SSE', start_date=date_str, end_date=date_str,
            fields='cal_date,is_open')
        if calendar is None or calendar.empty:
            logger.warning("未取得 %s 的交易日历，保守跳过本次策略筛选", date_str)
            return False
        is_open = int(calendar.iloc[0]['is_open']) == 1
        if not is_open:
            logger.info("%s 是 A 股休市日，跳过策略筛选", day.strftime('%Y-%m-%d'))
        return is_open
    except Exception as exc:
        logger.error("查询 %s 交易日历失败，保守跳过本次策略筛选: %s", date_str, exc)
        return False


def run_all_strategies():
    """运行所有筛选策略，结果记录到日志"""
    logger.info("========== 全策略筛选开始 ==========")

    if not is_a_share_trading_day():
        logger.info("========== 非交易日，本次策略任务结束 ==========")
        return {}

    today = datetime.date.today()
    start_date = (today - datetime.timedelta(days=30)).strftime('%Y%m%d')
    end_date = today.strftime('%Y%m%d')
    logger.info(f"筛选区间: {start_date} ~ {end_date}")

    results = {}

    # 策略1: 巨量上涨（放量>=2倍且涨超4%，之后缩量调整振幅<3%）
    logger.info("--- [1/5] 巨量上涨筛选 ---")
    try:
        r = sp.getJuliangshangzhang(startDate=start_date, endDate=end_date, multiple=2)
        results['巨量上涨'] = r
        logger.info(f"巨量上涨: {len(r)} 只")
    except Exception as e:
        logger.error(f"巨量上涨筛选失败: {e}")

    # 策略2: 向上跳空缺口
    logger.info("--- [2/5] 向上跳空缺口筛选 ---")
    try:
        r = sp.getxiangshangtiaokongquekou(startDate=start_date, endDate=end_date)
        results['向上跳空缺口'] = r
        logger.info(f"向上跳空缺口: {len(r)} 只")
    except Exception as e:
        logger.error(f"向上跳空缺口筛选失败: {e}")

    # 策略3: 跳空上涨过（含量能确认）
    logger.info("--- [3/5] 跳空上涨筛选 ---")
    try:
        r = sp.gettiaokongshangzhangguo(startDate=start_date, endDate=end_date)
        results['跳空上涨'] = r
        logger.info(f"跳空上涨: {len(r)} 只")
    except Exception as e:
        logger.error(f"跳空上涨筛选失败: {e}")

    # 策略4: 放量日（当日成交量>=前日3倍）
    logger.info("--- [4/5] 放量日筛选 ---")
    try:
        r = sp.getFangliangDay0(startDate=start_date, endDate=end_date, multiple=3)
        results['放量日'] = r
        logger.info(f"放量日: {len(r)} 只")
    except Exception as e:
        logger.error(f"放量日筛选失败: {e}")

    # 策略5: 区间涨幅超30%
    logger.info("--- [5/5] 区间涨幅筛选 ---")
    try:
        r = sp.getZhangFu(startDate=start_date, endDate=end_date, pct=30)
        results['区间涨幅30%'] = r
        logger.info(f"区间涨幅30%: {len(r)} 只")
    except Exception as e:
        logger.error(f"区间涨幅筛选失败: {e}")

    # 策略6: 最近30個交易日平緩上漲且漲幅超過30%
    logger.info("--- [6/6] 30日平緩上漲篩選 ---")
    try:
        r = sp.getSmoothUptrend(trading_days=30, min_gain_pct=30)
        results['30日平緩上漲30%'] = r
        logger.info(f"30日平緩上漲30%: {len(r)} 只")
    except Exception as e:
        logger.error(f"30日平緩上漲篩選失敗: {e}")

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
