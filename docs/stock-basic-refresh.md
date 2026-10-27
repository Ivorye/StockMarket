# 股票列表刷新与限频

`dailyUpdate.py`、网页更新按钮和 `StockApplication.py` 经由 `loadStocks.getStockBasic()` 使用同一刷新入口。
策略优先读取 `stocks`，只有缓存为空时才走此入口；数据库读取失败不再静默回退 API。

- 当天已成功刷新且缓存非空：直接使用 `stocks`，不再请求 `stock_basic`。
- 次日首次更新：若冷却已结束，重新请求列表，发现新股并更新股票名称等基本资料。
- 每次请求前先保存冷却时间，至少间隔 1 小时 5 秒；调用失败、入库失败及进程退出都不会立即重试。
- 接口提示日额度超限：延后至次日，且仍满足最短冷却间隔。
- MySQL `GET_LOCK('stockshare.stock_basic.refresh', 0)` 防止参与该协议的多个进程同时刷新。
- 冷却及最近成功日期存于 `st_api_request_state`，首次使用自动创建；成功状态仍兼容 `st_execution_status`。
- 刷新控制或 API 不可用时优先使用旧缓存，并明确警告列表可能未更新；没有缓存时明确失败。
- 股票列表更新与成功状态在同一事务提交；按 `st_code` 匹配旧股票，新股使用当前最大 ID 之后的新 ID，不再使用接口行号配合 `INSERT IGNORE`。

此协议只保护使用本入口的代码。其他电脑、旧进程或直接调用 Tushare 的独立脚本仍可能使用同一 token 的额度；旧工具 `stockPolicy.loadAllStockBasicsIntoMysql()` 仍为独立 API 调用，不用于当前每日更新流程。
网页服务需要重启才能加载新代码；计划任务下一次启动脚本时生效。

离线测试（Mock API 与数据库，不消耗额度，不修改真实数据）：

```powershell
.\venv\Scripts\python.exe -B -m unittest discover -s tests -p test_stock_basic_cache.py -v
```
