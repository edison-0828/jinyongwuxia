#!/usr/bin/env python3
"""jy2 存檔修改器 (CLI)。讀寫 Ruffle 的 gamezly系 .sol,stdlib only。
用量:
  trainer.py list [--slot 1|2|3] [--file PATH] [過濾字]
  trainer.py get <KEY> [...]
  trainer.py set <KEY> <VALUE> [...]      # 數字鍵給數字;文字鍵給文字(可變長)
  trainer.py setname <姓> <名> [...]       # 同步 name_1/name_2/name內文
  trainer.py diff <A> <B>
修改前自動備份。重要:改檔前先關遊戲,改完進遊戲讀檔驗收。
鍵(見教程): LV等級 JYZ經驗 S_M/S_M0生命 N_L/N_L0內力 F_Y福緣 S_W聲望
W_X悟性 L_D/L_D0力道 H_T/H_T0護體 S_F身法 Q_Z拳掌 Y_J御劍 A_Q暗器 Y_L醫療
Y_D用毒 J_D解毒 X_Y俠義 Y_Z銀兩 XXD學習點 Menpai門派 Chenhao稱號
lv_/exp_武功 kkk/lll自創 hhh/iii九陰神爪 jjj自創武學名 rrr半瓶醋次數
no_物品 CJ場景 aaa左右互搏(改1後讀檔驗證)
"""
import struct
import sys
import os
import glob
import re
import shutil
import time
import string
import math
import tempfile
import subprocess
from contextlib import contextmanager

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

ROOTS = {1: b'gamezly', 2: b'gamelzy', 3: b'gameylz'}
DEF_BASE = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'ruffle', 'SharedObjects')
MAX_GAME_NUMBER = 1_000_000_000
MAX_SAVE_STRING_BYTES = 65_535
NONNEGATIVE_KEYS = {
    'LV', 'JYZ', 'S_M', 'S_M0', 'N_L', 'N_L0', 'F_Y', 'S_W', 'W_X',
    'L_D', 'L_D0', 'H_T', 'H_T0', 'S_F', 'Q_Z', 'Y_J', 'A_Q', 'Y_L',
    'Y_D', 'J_D', 'Y_Z', 'XXD', 'rrr',
}


def pkg_save():
    from amf import pkg_root
    return os.path.join(pkg_root(), 'save')


def parse_game_number(key, text):
    """Parse a save value without allowing NaN/Infinity/fractions or absurd values."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise ValueError('%s 必須是數字' % key)
    if not math.isfinite(value):
        raise ValueError('%s 不可使用 NaN 或 Infinity' % key)
    if not value.is_integer():
        raise ValueError('%s 必須是整數' % key)
    if abs(value) > MAX_GAME_NUMBER:
        raise ValueError('%s 超出允許範圍 ±%d' % (key, MAX_GAME_NUMBER))
    if key in NONNEGATIVE_KEYS or key.startswith(('lv_', 'exp_')):
        if value < 0:
            raise ValueError('%s 不可小於 0' % key)
    if key == 'LV' and value < 1:
        raise ValueError('LV 不可小於 1')
    return value


def encode_save_string(key, text):
    """Encode an AMF0 short string and reject values that cannot be serialized."""
    value = str(text)
    encoded = value.encode('utf-8')
    if len(encoded) > MAX_SAVE_STRING_BYTES:
        raise ValueError('%s 太長（UTF-8 最多 %d bytes）' % (key, MAX_SAVE_STRING_BYTES))
    return encoded


def ruffle_running():
    """Return True when any Ruffle desktop process is active on Windows."""
    if os.name != 'nt':
        return False
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        p = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq ruffle.exe', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, errors='ignore', creationflags=flags,
            check=False,
        )
    except OSError:
        return False
    return 'ruffle.exe' in p.stdout.lower()


def ensure_game_closed():
    if ruffle_running():
        raise RuntimeError('偵測到 Ruffle 正在執行；請先退出遊戲再修改存檔')


@contextmanager
def edit_guard(path):
    """Serialize modifier writes and reject edits while Ruffle is running."""
    ensure_game_closed()
    lock_path = path + '.edit.lock'
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    lock = open(lock_path, 'a+b')
    try:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError('此存檔正在被另一個修改器處理')
        else:
            import fcntl
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError('此存檔正在被另一個修改器處理')
        yield
    finally:
        try:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        lock.close()


def find_sols():
    return glob.glob(DEF_BASE + '\\localhost\\*\\*\\*\\*', recursive=True)


def jy2_ns_dir():
    """跟 Ruffle 同算法算出 jy2.swf 的命名空間目錄：
    去掉碟符，逐段 URL 編碼（ASCII 原樣，非 ASCII 轉 UTF-8 百分比編碼）。"""
    import urllib.parse
    from amf import pkg_root
    swf = os.path.abspath(os.path.join(pkg_root(), 'resource', 'assets', 'jy2', 'jy2.swf'))
    parts = swf.replace('\\', '/').split('/')
    if parts and parts[0].endswith(':'):
        parts = parts[1:]
    safe = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~'
    enc = [urllib.parse.quote(p, safe=safe) for p in parts[:-1]]
    return os.path.join(pkg_save(), 'localhost', *enc, parts[-1])


def find_slot(slot):
    """先走確定性路徑（跟 Ruffle 一致）；找不到才回退掃描。"""
    want = ROOTS[slot].decode() + '.sol'
    det = os.path.join(jy2_ns_dir(), want)
    if os.path.isfile(det):
        return det
    base = pkg_save()
    cands = []
    if os.path.isdir(base):
        for dp, dn, fn in os.walk(base):
            if want in fn:
                cands.append(os.path.join(dp, want))
    if not cands:
        raise FileNotFoundError('slot%s 無存檔（先進遊戲存檔）：%s' % (slot, det))
    cands.sort(key=os.path.getmtime, reverse=True)
    return cands[0]


def migrate_legacy_slots():
    """Copy saves from an old absolute-path namespace into the current one.

    Ruffle includes the SWF's absolute path in the SharedObject namespace. Moving
    the portable folder therefore changes the lookup path. Keep the old copy and
    seed the new namespace only when its slot is empty.
    """
    ensure_game_closed()
    target_dir = jy2_ns_dir()
    os.makedirs(target_dir, exist_ok=True)
    migrated = []
    base = pkg_save()
    for slot, root in ROOTS.items():
        name = root.decode() + '.sol'
        target = os.path.join(target_dir, name)
        if os.path.isfile(target):
            Sol(target)
            continue
        candidates = []
        if os.path.isdir(base):
            for dp, dn, fn in os.walk(base):
                if name in fn:
                    source = os.path.join(dp, name)
                    if os.path.normcase(os.path.abspath(source)) != os.path.normcase(os.path.abspath(target)):
                        candidates.append(source)
        if not candidates:
            continue
        candidates.sort(key=os.path.getmtime, reverse=True)
        source = candidates[0]
        Sol(source)
        try:
            shutil.copy2(source, target)
            Sol(target)  # fail immediately if the migrated file is unreadable
        except Exception:
            if os.path.exists(target):
                os.unlink(target)
            raise
        migrated.append((slot, source, target))
    return migrated


def resolve(args):
    if args.file:
        return args.file
    if args.slot:
        try:
            return find_slot(args.slot)
        except FileNotFoundError as e:
            sys.exit(str(e))
    best = []
    for slot in (1, 2, 3):
        try:
            best.append(find_slot(slot))
        except FileNotFoundError:
            pass
    if not best:
        sys.exit('包內存檔位無存檔,請先進遊戲存檔')
    best.sort(key=os.path.getmtime, reverse=True)
    return best[0]


def is_key(b):
    return bool(b) and len(b) <= 40 and chr(b[0]) in string.ascii_letters + '_' and \
        all(chr(c) in string.ascii_letters + string.digits + '_.' for c in b)


def try_entry(b, p):
    """在 p 起 0..8 個 0 之後找一筆;回 (key,t,vpos,vlen,val,next_ok)。"""
    for z in range(9):
        q = p + z
        if q + 3 > len(b):
            continue
        klen = struct.unpack('>H', b[q:q + 2])[0]
        if not 1 <= klen <= 40 or q + 2 + klen + 1 > len(b):
            continue
        kb = bytes(b[q + 2:q + 2 + klen])
        if not is_key(kb):
            continue
        t = b[q + 2 + klen]
        vp = q + 2 + klen + 1
        if t == 0x00:
            if vp + 8 > len(b):
                continue
            vlen, v = 8, struct.unpack('>d', b[vp:vp + 8])[0]
        elif t == 0x01:
            if vp + 1 > len(b):
                continue
            vlen, v = 1, bool(b[vp])
        elif t == 0x02:
            if vp + 2 > len(b):
                continue
            sl = struct.unpack('>H', b[vp:vp + 2])[0]
            if vp + 2 + sl > len(b) or sl > 2000:
                continue
            vlen = 2 + sl
            v = bytes(b[vp + 2:vp + 2 + sl]).decode('utf-8', 'replace')
        else:
            continue
        if continues(b, vp + vlen):
            return kb.decode(), t, vp, vlen, v
    return None


def continues(b, p):
    """vp+vlen 之後是否接著另一筆(或正常結尾)。"""
    for z in range(9):
        q = p + z
        if q >= len(b):
            return True
        if q + 3 > len(b):
            continue
        klen = struct.unpack('>H', b[q:q + 2])[0]
        if not 1 <= klen <= 40 or q + 2 + klen + 1 > len(b):
            continue
        if not is_key(bytes(b[q + 2:q + 2 + klen])):
            continue
        if b[q + 2 + klen] in (0, 1, 2):
            return True
    return False


class Sol:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            self.raw = bytearray(f.read())
        self.entries = {}
        self.parse()

    def parse(self):
        b = self.raw
        i = b.find(b'TCSO')
        if i < 0:
            raise ValueError('not a .sol file')
        p = i + 4 + 6
        rlen = struct.unpack('>H', b[p:p + 2])[0]
        p += 2 + rlen + 4
        while p < len(b):
            r = try_entry(b, p)
            if r is None:
                break
            key, t, vp, vlen, v = r
            self.entries[key] = {'type': t, 'vpos': vp, 'vlen': vlen, 'val': v}
            p = vp + vlen
        if not self.entries:
            raise ValueError('parse failed: no keys found')

    def fmt(self, v):
        if isinstance(v, float):
            return str(int(v)) if v.is_integer() else repr(v)
        return repr(v)

    def cmd_list(self, pattern=None):
        for k in self.entries:
            if pattern and pattern not in k:
                continue
            e = self.entries[k]
            print('%-16s %s=%s' % (k, {0: 'N', 1: 'B', 2: 'S'}[e['type']], self.fmt(e['val'])))

    def backup(self):
        bak = '%s.bak.%d' % (self.path, time.time_ns())
        shutil.copy2(self.path, bak)
        return bak

    def save(self):
        expected = {k: (e['type'], e['val']) for k, e in self.entries.items()}
        parent = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(prefix='.%s.' % os.path.basename(self.path), suffix='.tmp', dir=parent)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(self.raw)
                f.flush()
                os.fsync(f.fileno())
            chk = Sol(tmp)
            actual = {k: (e['type'], e['val']) for k, e in chk.entries.items()}
            if actual != expected:
                raise ValueError('write verify failed: fields/types/values changed')
            try:
                shutil.copymode(self.path, tmp)
            except OSError:
                pass
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def set_number(self, key, text):
        e = self.entries[key]
        assert e['type'] == 0x00
        try:
            nv = parse_game_number(key, text)
        except ValueError as exc:
            sys.exit(str(exc))
        struct.pack_into('>d', self.raw, e['vpos'], nv)
        e['val'] = nv
        return self.fmt(nv)

    def set_string(self, key, text):
        e = self.entries[key]
        assert e['type'] == 0x02
        nb = encode_save_string(key, text)
        newv = struct.pack('>H', len(nb)) + nb
        self.raw[e['vpos']:e['vpos'] + e['vlen']] = newv
        self.parse()  # 變長後重建偏移
        return text

    def cmd_set(self, key, text):
        if key not in self.entries:
            sys.exit('無此鍵: %s (用 list 查)' % key)
        e = self.entries[key]
        if e['type'] == 0x00:
            show = self.set_number(key, text)
        elif e['type'] == 0x01:
            if text not in ('0', '1'):
                sys.exit('開關鍵請給 0/1')
            self.raw[e['vpos']] = int(text)
            e['val'] = bool(int(text))
            show = text
        elif e['type'] == 0x02:
            show = self.set_string(key, text)
        bak = self.backup()
        self.save()
        print('OK %s=%s  備份:%s' % (key, show, bak))
        print('進遊戲讀檔驗收。若壞檔,用備份蓋回來即可。')

    def set_named(self, key, text):
        """name_1/name_2：只換 markup 第一段明文，markup 保留(字體才不會掉)。"""
        e = self.entries[key]
        full = bytes(self.raw[e['vpos'] + 2:e['vpos'] + e['vlen']]).decode('utf-8', 'replace')
        run = None
        for mm in re.finditer(r'>([^<>]*)</FONT>', full):
            if mm.group(1).strip():
                run = mm.group(1)
                break
        new_full = full.replace('>' + run + '</FONT>', '>' + text + '</FONT>', 1) if run is not None else text
        self.set_string(key, new_full)

    def set_full_name(self, xing, ming):
        """Synchronize the combined display name for markup and plain-text saves."""
        key = 'name'
        e = self.entries[key]
        full = bytes(self.raw[e['vpos'] + 2:e['vpos'] + e['vlen']]).decode('utf-8', 'replace')
        runs = [mm for mm in re.finditer(r'>([^<>]*)</FONT>', full) if mm.group(1).strip()]
        new_full = full
        if len(runs) >= 2:
            for mm, text in zip(runs[:2], (xing, ming)):
                new_full = new_full.replace('>' + mm.group(1) + '</FONT>',
                                            '>' + text + '</FONT>', 1)
        elif len(runs) == 1:
            new_full = new_full.replace('>' + runs[0].group(1) + '</FONT>',
                                        '>' + xing + ming + '</FONT>', 1)
        else:
            new_full = xing + ming
        self.set_string(key, new_full)

    def cmd_setname(self, xing, ming):
        for k in ('name_1', 'name_2', 'name'):
            if k not in self.entries:
                sys.exit('缺鍵 %s,先用 list 確認' % k)
        self.set_named('name_1', xing)
        self.set_named('name_2', ming)
        self.set_full_name(xing, ming)
        bak = self.backup()
        self.save()
        print('OK 姓=%s 名=%s  備份:%s' % (xing, ming, bak))
        print('進遊戲讀檔驗收。')


@contextmanager
def edit_sol(path):
    """Open a fresh save snapshot while holding the modifier lock."""
    with edit_guard(path):
        yield Sol(path)


def cmd_diff(a, b):
    ra, rb = open(a, 'rb').read(), open(b, 'rb').read()
    n = min(len(ra), len(rb))
    ds = [i for i in range(n) if ra[i] != rb[i]]
    print('len %d/%d diffbytes=%d' % (len(ra), len(rb), len(ds)))
    for i in ds[:50]:
        seg = ra[max(0, i - 50):i]
        ms = list(re.finditer(rb'[A-Za-z_][A-Za-z0-9_.]{0,30}', seg))
        print('off=%d near=%s' % (i, ms[-1].group(0).decode() if ms else '?'))


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description='jy2 存檔修改器')
    c = argparse.ArgumentParser(add_help=False)
    c.add_argument('--slot', type=int, choices=(1, 2, 3))
    c.add_argument('--file')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list', parents=[c]); p.add_argument('pattern', nargs='?')
    p = sub.add_parser('get', parents=[c]); p.add_argument('key')
    p = sub.add_parser('set', parents=[c]); p.add_argument('key'); p.add_argument('value')
    p = sub.add_parser('setname', parents=[c]); p.add_argument('xing'); p.add_argument('ming')
    p = sub.add_parser('diff'); p.add_argument('a'); p.add_argument('b')
    a = ap.parse_args(argv)
    if a.cmd == 'diff':
        return cmd_diff(a.a, a.b)
    path = resolve(a)
    if a.cmd in ('set', 'setname'):
        with edit_guard(path):
            s = Sol(path)
            if a.cmd == 'set':
                s.cmd_set(a.key, a.value)
            else:
                s.cmd_setname(a.xing, a.ming)
        return
    s = Sol(path)
    if a.cmd == 'list':
        print('%s : %d keys' % (os.path.basename(s.path), len(s.entries)))
        s.cmd_list(a.pattern)
    elif a.cmd == 'get':
        if a.key not in s.entries:
            sys.exit('無此鍵')
        print(s.fmt(s.entries[a.key]['val']))


if __name__ == '__main__':
    main(sys.argv[1:])
