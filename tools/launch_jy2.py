#!/usr/bin/env python3
"""jy2 啟動器：開 Ruffle 跑包內素材。PyInstaller --windowed 編成 金庸群俠傳2.exe。"""
import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amf import pkg_root  # noqa: E402
from trainer import migrate_legacy_slots, ruffle_running  # noqa: E402


def fail(message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, '金庸群俠傳2', 0x10)
    except Exception:
        pass
    finally:
        raise SystemExit(message)

pkg = pkg_root()
engine = os.path.join(pkg, 'resource', 'engine', 'ruffle.exe')
movie = os.path.join(pkg, 'resource', 'assets', 'jy2', 'jy2.swf')
save_dir = os.path.join(pkg, 'save')
if ruffle_running():
    fail('已經有 Ruffle 遊戲在執行。請先退出，避免兩個程序同時覆蓋存檔。')
for required in (engine, movie):
    if not os.path.isfile(required):
        fail('缺少必要檔案：%s' % required)
os.makedirs(save_dir, exist_ok=True)
try:
    migrate_legacy_slots()
except Exception as exc:
    fail('存檔搬遷檢查失敗：%s' % exc)
subprocess.Popen([
    engine, movie, '--save-directory', save_dir,
], cwd=pkg)
