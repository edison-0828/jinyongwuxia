#!/usr/bin/env python3
"""jy2 啟動器：開 Ruffle 跑包內素材。PyInstaller --windowed 編成 金庸群俠傳2.exe。"""
import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amf import pkg_root  # noqa: E402
from trainer import Sol, edit_guard, find_slot, migrate_legacy_slots, ruffle_running  # noqa: E402


def show_message(message, title='金庸群俠傳2', flags=0):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, title, flags)
    except Exception:
        pass


def fail(message):
    try:
        show_message(message, flags=0x10)
    finally:
        raise SystemExit(message)


def latest_slot():
    slots = []
    for slot in (1, 2, 3):
        try:
            path = find_slot(slot)
        except FileNotFoundError:
            continue
        slots.append((os.path.getmtime(path), slot, path))
    return max(slots, default=None)


def ask_initial_chinese_name():
    """Collect a pending name without relying on Flash/Ruffle IME support."""
    try:
        import tkinter as tk
        from tkinter import messagebox, simpledialog
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            '首次中文取名助手',
            'Ruffle 暫不支援中文輸入法。\n\n'
            '請在接下來的視窗輸入正式中文姓名；進入遊戲時，姓和名先填任意英文。'
            '建立存檔並退出遊戲後，啟動器會自動把存檔姓名換成中文。',
            parent=root,
        )
        xing = simpledialog.askstring('首次中文取名助手', '正式姓氏：', parent=root)
        if xing is None:
            return None
        ming = simpledialog.askstring('首次中文取名助手', '正式名字：', parent=root)
        if ming is None:
            return None
        xing, ming = xing.strip(), ming.strip()
        if not xing or not ming:
            messagebox.showwarning('首次中文取名助手', '姓和名都不可留空，本次將略過自動改名。', parent=root)
            return None
        return xing, ming
    except Exception:
        return None
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def apply_name_to_latest_slot(xing, ming):
    latest = latest_slot()
    if latest is None:
        raise FileNotFoundError('沒有找到新存檔；請在遊戲內建立存檔後再退出')
    _, slot, path = latest
    with edit_guard(path):
        sol = Sol(path)
        for key in ('name_1', 'name_2', 'name'):
            if key not in sol.entries or sol.entries[key]['type'] != 0x02:
                raise ValueError('slot%s 缺少姓名欄位 %s' % (slot, key))
        sol.set_named('name_1', xing)
        sol.set_named('name_2', ming)
        sol.set_full_name(xing, ming)
        backup = sol.backup()
        sol.save()
    return slot, path, backup


def main():
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

    pending_name = ask_initial_chinese_name() if latest_slot() is None else None
    game = subprocess.Popen([
        engine, movie, '--save-directory', save_dir,
    ], cwd=pkg)
    if pending_name is None:
        return

    game.wait()
    try:
        slot, _, _ = apply_name_to_latest_slot(*pending_name)
    except Exception as exc:
        show_message('中文姓名尚未寫入：%s\n\n可先建立存檔，再使用「金庸群俠傳2修改器」。' % exc,
                     title='首次中文取名助手', flags=0x30)
        return
    show_message('中文姓名已寫入存檔槽 %d。下次啟動遊戲後讀取該存檔即可。' % slot,
                 title='首次中文取名助手', flags=0x40)


if __name__ == '__main__':
    main()
