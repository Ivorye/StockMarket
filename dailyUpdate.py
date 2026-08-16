import os
import sys
import time
import logging
import loadStocks as ld

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


def run_daily_update():
    """每日数据更新流程：获取最新股票列表 → 载入总表 → 为新股建表"""
    logger.info("========== 每日数据更新开始 ==========")

    # 步骤1：获取最新股票列表
    logger.info("[1/3] 获取最新股票列表 (getStockBasic)...")
    try:
        df = ld.getStockBasic()
        logger.info(f"获取到 {len(df)} 只股票基本信息")
    except Exception as e:
        logger.error(f"getStockBasic 执行失败: {e}")
        return

    # 步骤2：将所有股票基本信息载入总表
    logger.info("[2/3] 载入股票基本信息到总表 (loadAllBasic)...")
    try:
        ld.loadAllBasic(df)
        logger.info("股票基本信息载入完成")
    except Exception as e:
        logger.error(f"loadAllBasic 执行失败: {e}")
        return

    # 步骤3：为新股票建表
    logger.info("[3/3] 为新股票创建日线表 (createStockTable)...")
    try:
        ld.createStockTable(df)
        logger.info("新股票建表完成")
    except Exception as e:
        logger.error(f"createStockTable 执行失败: {e}")
        return

    logger.info("========== 每日数据更新完成 ==========")


if __name__ == '__main__':
    run_daily_update()
