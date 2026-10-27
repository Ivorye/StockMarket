"""StockMarket FastAPI 启动入口。

Windows + Python 3.9 下，uvicorn 默认使用 ProactorEventLoop，其 accept 循环在客户端
提前断开连接时会抛出 OSError [WinError 64] 并导致监听器崩溃（日志中的
"IocpProactor.accept ... WinError 64 / Accept failed on a socket"）。

这里在启动前显式把事件循环策略切到 SelectorEventLoop，改用 select() 实现，
从根本上规避该问题。用法与 `uvicorn main:app` 一致：

    python run_server.py                # 默认 127.0.0.1:8000
    python run_server.py --port 9000
"""

import asyncio
import sys

import uvicorn


def main() -> None:
    port = 8000
    host = "127.0.0.1"
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1]); i += 2; continue
        if args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]; i += 2; continue
        i += 1

    config = uvicorn.Config("main:app", host=host, port=port,
                            log_level="info", loop="asyncio")
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        # 在自建 Selector 事件循环上运行，避开 Proactor accept 的 WinError 64。
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()
    else:
        server.run()


if __name__ == "__main__":
    main()
