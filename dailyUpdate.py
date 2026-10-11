import datetime
import logging
import os
import sys

import loadStocks as ld
import stockPolicy as sp

# 计划任务运行在 cp1252 控制台下，中文 print/logger 输出会抛 UnicodeEncodeError。
# 该异常会从 loadStocks 的 except 分支逃逸，导致 run_daily_update 提前 return、
# 后续步骤全部跳过。这里统一改用 UTF-8 并容错，必须在 StreamHandler 创建前执行。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

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

# 进度状态：供网页"更新K线"按钮轮询展示进度条。
# total 为总步骤数；step 为已完成步骤数；message 为当前阶段描述；
# running 表示是否有更新正在执行，避免并发触发。仅单进程内有效。
_PROGRESS = {
    'running': False,
    'step': 0,
    'total': 6,
    'percent': 0,
    'message': '',
    'done': False,
    'ok': None,
    'error': '',
}


def get_progress():
    """返回当前更新进度快照（供 /api/update-kline/status 轮询）。"""
    return dict(_PROGRESS)


def _set_progress(step=None, message=None, running=None, done=None, ok=None, error=None):
    """更新进度状态并同步 percent。"""
    if running is not None:
        _PROGRESS['running'] = running
    if done is not None:
        _PROGRESS['done'] = done
    if ok is not None:
        _PROGRESS['ok'] = ok
    if error is not None:
        _PROGRESS['error'] = error
    if step is not None:
        _PROGRESS['step'] = step
    if message is not None:
        _PROGRESS['message'] = message
    total = _PROGRESS['total'] or 1
    _PROGRESS['percent'] = int(_PROGRESS['step'] / total * 100)



def is_a_share_trading_day(day=None):
    """周末直接跳过；工作日由 daily API 是否返回数据判断休市。"""
    day = day or datetime.date.today()
    if day.weekday() >= 5:
        logger.info("%s 是周末，跳过股票数据更新", day.strftime('%Y-%m-%d'))
        return False
    # 避免调用每日额度很低的 trade_cal。法定休市日调用 daily 会返回空数据，
    # 批量更新逻辑会将其安全地视为无数据日期。
    return True


def run_daily_update(force=False, source='system'):
    """每日数据更新流程：获取股票列表（优先DB）→ 载入总表 → 为新股建表 → 加载近期日线数据

    force=True 时跳过交易日判断，无条件执行（供网页"更新K线"按钮手动触发）。
    source: 更新来源，'manual'=人工（网页按钮），'system'=系统自动（计划任务，默认）。
    返回 True 表示本次执行成功（含"非交易日正常跳过"），False 表示失败。
    调用方据此决定进程退出码，计划任务的 LastResult 才会如实反映执行结果，
    下游策略任务的依赖检查也才能正确判定是否跳过。
    """
    logger.info("========== 每日数据更新开始 ==========")
    _set_progress(step=0, message='准备开始…', running=True, done=False, ok=None, error='')

    if not force and not is_a_share_trading_day():
        logger.info("========== 非交易日，本次任务结束 ==========")
        _set_progress(step=_PROGRESS['total'], message='非交易日，已跳过', running=False, done=True, ok=True)
        return True

    # 步骤1：获取股票列表（优先从数据库读取，避免消耗stock_basic API配额）
    logger.info("[1/6] 获取股票列表...")
    _set_progress(message='[1/6] 获取股票列表…')
    try:
        df = ld.getStockBasic(source=source)
        logger.info(f"从API获取到 {len(df)} 只股票基本信息")
    except Exception as e:
        logger.error(f"getStockBasic 执行失败: {e}")
        _set_progress(message=f'获取股票列表失败: {e}', running=False, done=True, ok=False, error=str(e))
        return False
    _set_progress(step=1)

    # 步骤2：将所有股票基本信息载入总表
    logger.info("[2/6] 载入股票基本信息到总表 (loadAllBasic)...")
    _set_progress(message='[2/6] 载入股票基本信息到总表…')
    try:
        ld.loadAllBasic(df)
        logger.info("股票基本信息载入完成")
    except Exception as e:
        logger.error(f"loadAllBasic 执行失败: {e}")
        _set_progress(message=f'载入基本信息失败: {e}', running=False, done=True, ok=False, error=str(e))
        return False
    _set_progress(step=2)

    # 步骤3：确保统一日线表存在
    logger.info("[3/6] 确保 st_daily 日线表存在...")
    _set_progress(message='[3/6] 检查 st_daily 日线表…')
    try:
        ld.createStockTable(df)
        logger.info("st_daily 表检查完成")
    except Exception as e:
        logger.error(f"createStockTable 执行失败: {e}")
        _set_progress(message=f'建表失败: {e}', running=False, done=True, ok=False, error=str(e))
        return False
    _set_progress(step=3)

    # 步骤4：增量加载日线数据（只补缺失天数，已存在的记录会跳过）
    logger.info("[4/6] 增量加载日线数据...")
    _set_progress(message='[4/6] 增量加载日线数据（耗时较久）…')
    try:
        ld.incrementalUpdateDailyData(df, lookback_days=30)
        logger.info("日线数据加载完成")
    except Exception as e:
        logger.error(f"日线数据加载失败: {e}")
        _set_progress(message=f'日线数据加载失败: {e}', running=False, done=True, ok=False, error=str(e))
        return False
    _set_progress(step=4)

    # 步骤5：确认统一日线表可用（步骤4已直接写入）
    logger.info("[5/6] 检查 st_daily 日线表...")
    _set_progress(message='[5/6] 汇总 st_daily 日线表…')
    try:
        sp.createDailyTable()
        sp.buildDailyTable()
        logger.info("st_daily汇总完成")
    except Exception as e:
        logger.error(f"st_daily汇总失败: {e}")
        _set_progress(message=f'st_daily 汇总失败: {e}', running=False, done=True, ok=False, error=str(e))
        return False
    _set_progress(step=5)

    # 步骤6：执行放量涨幅筛选
    logger.info("[6/6] 执行放量涨幅筛选...")
    _set_progress(message='[6/6] 执行放量涨幅筛选…')
    try:
        sp.createSignalTable()
        result = sp.getLiangJiaFangLiang()
        logger.info(f"放量涨幅筛选完成，命中 {len(result)} 只股票")
    except Exception as e:
        logger.error(f"放量涨幅筛选失败: {e}")
        _set_progress(message=f'放量涨幅筛选失败: {e}', running=False, done=True, ok=False, error=str(e))
        return False
    _set_progress(step=6, message='更新完成', running=False, done=True, ok=True)

    logger.info("========== 每日数据更新完成 ==========")
    return True


if __name__ == '__main__':
    sys.exit(0 if run_daily_update() else 1)
