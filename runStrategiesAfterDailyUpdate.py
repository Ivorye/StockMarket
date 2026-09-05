import datetime
import logging
import os
import subprocess
import sys


log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, 'strategies.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def _run_powershell(command):
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-Command', command],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def daily_update_finished_successfully():
    command = (
        "$task=Get-ScheduledTask -TaskName 'StockDailyUpdate' -TaskPath '\\';"
        "$info=Get-ScheduledTaskInfo -TaskName 'StockDailyUpdate' -TaskPath '\\';"
        "$threshold=(Get-Date).Date.AddHours(20);"
        "[pscustomobject]@{"
        "State=$task.State.ToString();"
        "LastRunTime=$info.LastRunTime.ToString('o');"
        "LastResult=$info.LastTaskResult;"
        "IsReady=($task.State.ToString() -eq 'Ready');"
        "RanAfterThreshold=($info.LastRunTime -ge $threshold);"
        "Succeeded=($info.LastTaskResult -eq 0)"
        "} | ConvertTo-Json -Compress"
    )
    import json
    status = json.loads(_run_powershell(command))
    logger.info(
        "StockDailyUpdate status: state=%s, last_run=%s, result=%s, ran_after_20=%s",
        status['State'], status['LastRunTime'], status['LastResult'], status['RanAfterThreshold'],
    )
    return status['IsReady'] and status['RanAfterThreshold'] and status['Succeeded']


def main():
    logger.info("========== 策略任务依赖检查开始 ==========")
    if not daily_update_finished_successfully():
        logger.warning("StockDailyUpdate 今天20:00后未正常完成，跳过策略任务")
        return 0

    project_dir = os.path.dirname(os.path.abspath(__file__))
    strategy_script = os.path.join(project_dir, 'runAllStrategies.py')
    logger.info("StockDailyUpdate 已正常完成，开始执行策略任务")
    result = subprocess.run([sys.executable, strategy_script], cwd=project_dir)
    logger.info("策略任务退出码: %s", result.returncode)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
