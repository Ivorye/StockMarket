# -*- coding: utf-8 -*-
"""一次性计划任务 StockBackfillDaily 的入口。

tushare daily 的每日总量配额(20000次/天)耗尽后，当日 20:00 的例行更新会失败。
本脚本在次日 0 点配额恢复后重跑补齐，成功则删除该一次性任务。

不走 runStrategiesAfterDailyUpdate.py：它的依赖检查要求 StockDailyUpdate
在「今天20:00之后」成功，而本任务在凌晨 0:05 触发时该阈值尚未到达，必然被误判为
跳过。此处日线刚补齐即直接执行策略，语义等价。
"""
import logging
import os
import subprocess
import sys

# 计划任务运行在 cp1252 控制台下，中文 logger 输出会抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(BASE, 'venv', 'Scripts', 'python.exe')
TASK_NAME = 'StockBackfillDaily'

log_dir = os.path.join(BASE, 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'backfill.log'), encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger('backfill')


def run(script):
    name = os.path.basename(script)
    logger.info('---- %s ----', name)
    result = subprocess.run([PYTHON, script], cwd=BASE)
    logger.info('%s 退出码: %s', name, result.returncode)
    return result.returncode


def main():
    logger.info('========== 配额恢复后补齐日线 ==========')
    rc = run(os.path.join(BASE, 'dailyUpdate.py'))
    if rc != 0:
        logger.error('日线更新失败(exit=%s)，保留任务以便手动重试: schtasks /run /tn %s', rc, TASK_NAME)
        return rc

    logger.info('日线已补齐，直接执行策略（跳过20:00依赖检查，此处数据刚就绪）')
    rc = run(os.path.join(BASE, 'runAllStrategies.py'))
    if rc != 0:
        logger.error('策略执行失败(exit=%s)，保留任务以便手动重试: schtasks /run /tn %s', rc, TASK_NAME)
        return rc

    logger.info('补齐完成，删除一次性任务 %s', TASK_NAME)
    subprocess.run(['schtasks', '/delete', '/tn', TASK_NAME, '/f'], capture_output=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
