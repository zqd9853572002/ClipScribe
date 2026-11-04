# -*- coding: utf-8 -*-
"""应用启动层：隐藏控制台、创建 Tk 根窗口、安装异常兜底并进入主循环。

顶层 try/except 保留拆分前的行为：失败时打印 traceback，并尽力弹窗提示。
"""

import sys
import traceback
import tkinter as tk
from tkinter import messagebox

from .config import migrate_legacy_config_dir
from .i18n import t
from .ui.main_window import AudioToVideoApp


def _hide_console() -> None:
    """🛑 隐藏 Windows 黑窗口（异常由 main() 统一弹窗提示）。"""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except Exception:
            pass


def _start() -> None:
    try:
        root = tk.Tk()
    except Exception:
        print(traceback.format_exc())
        return

    def report_exception(exc, value, tb):
        detail = "".join(traceback.format_exception(exc, value, tb))
        try:
            messagebox.showerror(t("dlg.app_error_title"), detail[-1500:])
        except Exception:
            print(detail)

    root.report_callback_exception = report_exception
    AudioToVideoApp(root)
    root.mainloop()


def main() -> None:
    # 启动的第一步：在任何配置 / 模型路径被读取之前，把旧的
    # %APPDATA%\Mp3ToMp4 迁到 %APPDATA%\ClipScribe。
    # 函数内部已吞掉全部异常（失败时继续用旧目录），这里再兜一层，
    # 保证迁移永远不可能阻止应用启动。
    try:
        migrate_legacy_config_dir()
    except Exception:
        pass
    _hide_console()
    try:
        _start()
    except Exception:
        trace = traceback.format_exc()
        print(trace)
        try:
            fallback = tk.Tk()
            fallback.withdraw()
            messagebox.showerror(t("dlg.startup_failed_title"), trace[-1500:])
            fallback.destroy()
        except Exception:
            pass
