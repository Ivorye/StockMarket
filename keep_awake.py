"""Prevent Windows from sleeping while this program is running."""

import argparse
import ctypes
import time


ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def set_awake(keep_display_on=False):
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    if keep_display_on:
        flags |= ES_DISPLAY_REQUIRED
    if not ctypes.windll.kernel32.SetThreadExecutionState(flags):
        raise ctypes.WinError()


def restore_power_settings():
    if not ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS):
        raise ctypes.WinError()


def main():
    parser = argparse.ArgumentParser(
        description="執行期間阻止 Windows 進入休眠，按 Ctrl+C 結束。"
    )
    parser.add_argument(
        "--display",
        action="store_true",
        help="同時阻止螢幕自動關閉",
    )
    args = parser.parse_args()

    set_awake(args.display)
    mode = "系統休眠及螢幕關閉" if args.display else "系統休眠"
    print(f"已阻止{mode}。按 Ctrl+C 結束並恢復電源設定。")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n正在恢復原本的電源管理行為……")
    finally:
        restore_power_settings()


if __name__ == "__main__":
    main()
