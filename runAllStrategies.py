import datetime
import logging
import os
import sys

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


def run_all_strategies():
    """运行所有筛选策略，结果记录到日志"""
    logger.info("========== 全策略筛选开始 ==========")

    today = datetime.date.today()
    start_date = (today - datetime.timedelta(days=30)).strftime('%Y%m%d')
    end_date = today.strftime('%Y%m%d')
    logger.info(f"筛选区间: {start_date} ~ {end_date}")

    results = {}

    # 策略1: 放量涨幅（当日成交量>=前日3倍 且 涨幅>6%，结果写入st_daily_signal表）
    logger.info("--- [1/6] 放量涨幅筛选 ---")
    try:
        r = sp.getLiangJiaFangLiang(startDate='20210101', endDate=end_date)
        results['放量涨幅'] = r
        logger.info(f"放量涨幅: {len(r)} 只")
    except Exception as e:
        logger.error(f"放量涨幅筛选失败: {e}")

    # 策略2: 巨量上涨（放量>=2倍且涨超4%，之后缩量调整振幅<3%）
    logger.info("--- [2/6] 巨量上涨筛选 ---")
    try:
        r = sp.getJuliangshangzhang(startDate=start_date, endDate=end_date, multiple=2)
        results['巨量上涨'] = r
        logger.info(f"巨量上涨: {len(r)} 只")
    except Exception as e:
        logger.error(f"巨量上涨筛选失败: {e}")

    # 策略3: 向上跳空缺口
    logger.info("--- [3/6] 向上跳空缺口筛选 ---")
    try:
        r = sp.getxiangshangtiaokongquekou(startDate=start_date, endDate=end_date)
        results['向上跳空缺口'] = r
        logger.info(f"向上跳空缺口: {len(r)} 只")
    except Exception as e:
        logger.error(f"向上跳空缺口筛选失败: {e}")

    # 策略4: 跳空上涨过（含量能确认）
    logger.info("--- [4/6] 跳空上涨筛选 ---")
    try:
        r = sp.gettiaokongshangzhangguo(startDate=start_date, endDate=end_date)
        results['跳空上涨'] = r
        logger.info(f"跳空上涨: {len(r)} 只")
    except Exception as e:
        logger.error(f"跳空上涨筛选失败: {e}")

    # 策略5: 翻倍股（基于DB，使用最近两个交易日）
    logger.info("--- [5/6] 翻倍股筛选 ---")
    try:
        r = sp.getFanbeigu(startDate=start_date, endDate=end_date, multiple=2)
        results['翻倍股'] = r
        logger.info(f"翻倍股: {len(r)} 只")
    except Exception as e:
        logger.error(f"翻倍股筛选失败: {e}")

    # 策略6: 放量日（当日成交量>=前日3倍）
    logger.info("--- [6/6] 放量日筛选 ---")
    try:
        r = sp.getFangliangDay0(startDate=start_date, endDate=end_date, multiple=3)
        results['放量日'] = r
        logger.info(f"放量日: {len(r)} 只")
    except Exception as e:
        logger.error(f"放量日筛选失败: {e}")

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
