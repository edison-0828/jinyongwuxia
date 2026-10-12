#!/usr/bin/env python3
"""金庸群侠传 2 存档管理器：清晰、安全、只写入真正改动的字段。"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import trainer as T  # noqa: E402
from amf import pkg_root  # noqa: E402

BASIC_FIELDS = [
    ('name_1', '姓'), ('name_2', '名'), ('jjj', '自创武学名'),
    ('Menpai', '门派'), ('Chenhao', '称号'),
]
ATTRIBUTE_GROUPS = [
    ('进度与资源', [('LV', '等级'), ('JYZ', '经验'), ('XXD', '学习点'),
                 ('Y_Z', '银两'), ('S_W', '声望'), ('X_Y', '侠义')]),
    ('生命与内力', [('S_M', '生命 S_M'), ('S_M0', '生命 S_M0'),
                  ('N_L', '内力 N_L'), ('N_L0', '内力 N_L0')]),
    ('基础属性', [('F_Y', '福缘'), ('W_X', '悟性'), ('L_D', '力道'),
                ('L_D0', '力道(当前)'), ('H_T', '护体'),
                ('H_T0', '护体(当前)'), ('S_F', '身法')]),
    ('战斗技艺', [('Q_Z', '拳掌'), ('Y_J', '御剑'), ('A_Q', '暗器'),
                ('Y_L', '医疗'), ('Y_D', '用毒'), ('J_D', '解毒')]),
]
SKILLS = [
    ('taijiquan', '太极拳'), ('qishang', '七伤拳'), ('xingyi', '形意拳'),
    ('anran', '黯然销魂掌'), ('tianshan', '天山六阳掌'), ('tiezhang', '铁掌'),
    ('liumai', '六脉神剑'), ('nianhua', '拈花指'), ('taijijian', '太极剑'),
    ('wuyue', '五岳剑法'), ('xuantie', '玄铁剑法'), ('jiuyang', '九阳神功'),
    ('beiming', '北冥神功'), ('hanbing', '寒冰真气'), ('kongming', '空明拳'),
    ('luohan', '罗汉拳'), ('xianglong', '降龙十八掌'), ('mianzhang', '绵掌'),
    ('hunyuan', '混元掌'), ('yiyang', '一阳指'), ('tanzhi', '弹指神通'),
    ('canhe', '参合指'), ('jinshe', '金蛇剑法'), ('dugu', '独孤九剑'),
    ('pixie', '辟邪剑法'), ('taixuan', '太玄经神功'), ('longxiang', '龙象般若功'),
    ('jinzhong', '吐纳术'), ('jichujian', '基础剑法'), ('jichuquan', '基础拳法'),
    ('kkk', '自创武功'), ('hhh', '九阴神爪'),
]
SKILL_NAMES = dict(SKILLS)


def inner_text(markup):
    import re
    runs = [value for value in re.findall(r'>([^<>]*)</FONT>', markup) if value.strip()]
    return runs[0] if runs else markup


def number_text(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return '' if value is None else str(value)


def skill_keys(skill_id):
    if skill_id == 'kkk':
        return 'kkk', 'lll'
    if skill_id == 'hhh':
        return 'hhh', 'iii'
    return 'lv_' + skill_id, 'exp_' + skill_id


class App:
    def __init__(self, root):
        self.root = root
        self.path = None
        self.loading = False
        self.loaded = {}
        self.skill_source = {}
        self.skill_pending = {}
        self.vars = {}
        root.title('金庸群侠传 2 · 存档管理器')
        root.geometry('940x680')
        root.minsize(840, 620)
        self._configure_style()
        self._build_header()
        self._build_tabs()
        self._build_footer()
        self.refresh()

    def _configure_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('TNotebook.Tab', padding=(18, 9))
        style.configure('TLabelframe.Label', font=('Microsoft YaHei UI', 10, 'bold'))
        style.configure('Accent.TButton', font=('Microsoft YaHei UI', 10, 'bold'))
        style.configure('Treeview', rowheight=28)
        style.configure('Treeview.Heading', font=('Microsoft YaHei UI', 10, 'bold'))

    def _build_header(self):
        header = tk.Frame(self.root, bg='#172033', height=88)
        header.pack(fill='x')
        header.pack_propagate(False)
        title_box = tk.Frame(header, bg='#172033')
        title_box.pack(side='left', padx=22, pady=14)
        tk.Label(title_box, text='金庸群侠传 2', bg='#172033', fg='white',
                 font=('Microsoft YaHei UI', 19, 'bold')).pack(anchor='w')
        tk.Label(title_box, text='存档管理器 · 自动备份 · 原子写入', bg='#172033', fg='#aebbd0',
                 font=('Microsoft YaHei UI', 9)).pack(anchor='w')
        controls = tk.Frame(header, bg='#172033')
        controls.pack(side='right', padx=20)
        tk.Label(controls, text='存档槽', bg='#172033', fg='#dbe5f5').pack(side='left', padx=(0, 7))
        self.slot = tk.IntVar(value=1)
        slot_box = ttk.Combobox(controls, textvariable=self.slot, values=(1, 2, 3),
                                width=4, state='readonly')
        slot_box.pack(side='left')
        slot_box.bind('<<ComboboxSelected>>', lambda _event: self.refresh())
        ttk.Button(controls, text='重新读取', command=self.refresh).pack(side='left', padx=8)
        ttk.Button(controls, text='启动游戏', command=self.launch_game).pack(side='left')

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=16, pady=(14, 8))
        self._build_character_tab()
        self._build_attributes_tab()
        self._build_skills_tab()
        self._build_advanced_tab()

    def _new_var(self, key):
        var = tk.StringVar()
        var.trace_add('write', lambda *_args: self.mark_dirty())
        self.vars[key] = var
        return var

    def _build_character_tab(self):
        tab = ttk.Frame(self.notebook, padding=18)
        self.notebook.add(tab, text='角色')
        ttk.Label(tab, text='姓名会同时更新姓、名和游戏显示用完整姓名。',
                  foreground='#53627a').pack(anchor='w', pady=(0, 14))
        form = ttk.LabelFrame(tab, text='身份信息', padding=16)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        for row, (key, label) in enumerate(BASIC_FIELDS):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='e', padx=(0, 12), pady=7)
            ttk.Entry(form, textvariable=self._new_var(key), width=38).grid(
                row=row, column=1, sticky='ew', pady=7)
            ttk.Label(form, text=key, foreground='#8792a6').grid(row=row, column=2, sticky='w', padx=10)
        note = ttk.LabelFrame(tab, text='安全说明', padding=16)
        note.pack(fill='x', pady=16)
        ttk.Label(note, text='保存时只修改变化过的字段，并在原存档旁创建唯一备份。\n'
                             '游戏运行期间禁止写档，避免 Ruffle 退出时覆盖你的修改。',
                  justify='left').pack(anchor='w')

    def _build_attributes_tab(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='属性')
        for index, (title, fields) in enumerate(ATTRIBUTE_GROUPS):
            group = ttk.LabelFrame(tab, text=title, padding=10)
            group.grid(row=index // 2, column=index % 2, sticky='nsew', padx=6, pady=6)
            tab.columnconfigure(index % 2, weight=1)
            tab.rowconfigure(index // 2, weight=1)
            group.columnconfigure(1, weight=1)
            group.columnconfigure(3, weight=1)
            for position, (key, label) in enumerate(fields):
                row, pair = divmod(position, 2)
                column = pair * 2
                ttk.Label(group, text=label).grid(
                    row=row, column=column, sticky='e', padx=(0 if column == 0 else 12, 6), pady=4)
                ttk.Entry(group, textvariable=self._new_var(key), width=10).grid(
                    row=row, column=column + 1, sticky='ew', pady=4)

    def _build_skills_tab(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='武功')
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.skill_tree = ttk.Treeview(tab, columns=('name', 'level', 'exp', 'state'), show='headings')
        for key, title in (('name', '武功'), ('level', '等级'), ('exp', '经验'), ('state', '状态')):
            self.skill_tree.heading(key, text=title)
        self.skill_tree.column('name', width=250, anchor='w')
        self.skill_tree.column('level', width=100, anchor='center')
        self.skill_tree.column('exp', width=140, anchor='center')
        self.skill_tree.column('state', width=100, anchor='center')
        self.skill_tree.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(tab, orient='vertical', command=self.skill_tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.skill_tree.configure(yscrollcommand=scrollbar.set)
        self.skill_tree.bind('<Double-1>', lambda _event: self.edit_selected_skill())
        actions = ttk.Frame(tab)
        actions.grid(row=1, column=0, sticky='ew', pady=(10, 0))
        ttk.Label(actions, text='双击武功可编辑；修改会先进入待保存状态。',
                  foreground='#53627a').pack(side='left')
        ttk.Button(actions, text='撤销所选修改', command=self.reset_selected_skill).pack(side='right')
        ttk.Button(actions, text='编辑所选武功', command=self.edit_selected_skill).pack(side='right', padx=8)

    def _build_advanced_tab(self):
        tab = ttk.Frame(self.notebook, padding=18)
        self.notebook.add(tab, text='进阶')
        group = ttk.LabelFrame(tab, text='特殊字段', padding=16)
        group.pack(fill='x')
        self.rrr = self._new_var('rrr')
        ttk.Label(group, text='半瓶神仙醋次数').grid(row=0, column=0, sticky='e', padx=(0, 12), pady=8)
        ttk.Entry(group, textvariable=self.rrr, width=16).grid(row=0, column=1, sticky='w')
        ttk.Label(group, text='rrr', foreground='#8792a6').grid(row=0, column=2, sticky='w', padx=10)
        self.aaa = tk.BooleanVar()
        self.aaa.trace_add('write', lambda *_args: self.mark_dirty())
        ttk.Checkbutton(group, text='左右互搏开关', variable=self.aaa).grid(
            row=1, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Label(group, text='aaa（字段作用仍需游戏内验证）', foreground='#9a5b23').grid(
            row=1, column=2, sticky='w', padx=10)

    def _build_footer(self):
        footer = ttk.Frame(self.root, padding=(16, 8, 16, 14))
        footer.pack(fill='x')
        self.status = tk.StringVar(value='正在读取存档…')
        tk.Label(footer, textvariable=self.status, anchor='w', fg='#43516a',
                 font=('Microsoft YaHei UI', 9)).pack(side='left', fill='x', expand=True)
        ttk.Button(footer, text='放弃修改', command=self.refresh).pack(side='right', padx=(8, 0))
        self.save_button = ttk.Button(footer, text='保存全部修改', style='Accent.TButton',
                                      command=self.save_all)
        self.save_button.pack(side='right')

    def mark_dirty(self):
        if not self.loading and self.path:
            self.status.set('有尚未保存的修改')

    def save_path(self):
        return T.find_slot(self.slot.get())

    def _clear(self):
        for var in self.vars.values():
            var.set('')
        self.aaa.set(False)
        self.skill_source.clear()
        self.skill_pending.clear()
        for item in self.skill_tree.get_children():
            self.skill_tree.delete(item)

    def refresh(self):
        self.loading = True
        try:
            self._clear()
            try:
                self.path = self.save_path()
                sol = T.Sol(self.path)
            except Exception:
                self.path = None
                self.loaded = {}
                self.save_button.state(['disabled'])
                self.status.set('存档槽 %d 尚无存档。点击“启动游戏”创建存档。' % self.slot.get())
                return
            entries = sol.entries
            for key, var in self.vars.items():
                if key not in entries:
                    continue
                value = entries[key]['val']
                if key in ('name_1', 'name_2') and isinstance(value, str):
                    value = inner_text(value)
                var.set(number_text(value))
            if 'aaa' in entries:
                self.aaa.set(bool(entries['aaa']['val']))
            self.loaded = self._form_snapshot()
            self._load_skills(entries)
            self.save_button.state(['!disabled'])
            level = number_text(entries.get('LV', {}).get('val', '?'))
            school = entries.get('Menpai', {}).get('val', '')
            self.status.set('已读取槽 %d · LV %s · %s · %s' % (
                self.slot.get(), level, school, self._short_path(self.path)))
        finally:
            self.loading = False

    def _load_skills(self, entries):
        for skill_id, _name in SKILLS:
            level_key, exp_key = skill_keys(skill_id)
            if level_key not in entries and exp_key not in entries:
                continue
            self.skill_source[skill_id] = {
                'level_key': level_key, 'exp_key': exp_key,
                'has_level': level_key in entries, 'has_exp': exp_key in entries,
                'level': number_text(entries.get(level_key, {}).get('val')) if level_key in entries else '—',
                'exp': number_text(entries.get(exp_key, {}).get('val')) if exp_key in entries else '—',
            }
        self._render_skills()

    def _render_skills(self):
        selected = self.skill_tree.selection()
        selected_id = selected[0] if selected else None
        for item in self.skill_tree.get_children():
            self.skill_tree.delete(item)
        for skill_id, name in SKILLS:
            if skill_id not in self.skill_source:
                continue
            value = self.skill_pending.get(skill_id, self.skill_source[skill_id])
            state = '待保存' if skill_id in self.skill_pending else ''
            self.skill_tree.insert('', 'end', iid=skill_id,
                                   values=(name, value['level'], value['exp'], state))
        if selected_id and self.skill_tree.exists(selected_id):
            self.skill_tree.selection_set(selected_id)

    def edit_selected_skill(self):
        selected = self.skill_tree.selection()
        if not selected:
            messagebox.showinfo('编辑武功', '请先选择一项武功。', parent=self.root)
            return
        skill_id = selected[0]
        source = self.skill_source[skill_id]
        current = self.skill_pending.get(skill_id, source)
        dialog = tk.Toplevel(self.root)
        dialog.title('编辑 · %s' % SKILL_NAMES[skill_id])
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill='both', expand=True)
        level = tk.StringVar(value=current['level'])
        exp = tk.StringVar(value=current['exp'])
        ttk.Label(body, text=SKILL_NAMES[skill_id], font=('Microsoft YaHei UI', 13, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 14))
        ttk.Label(body, text='等级').grid(row=1, column=0, sticky='e', padx=(0, 10), pady=6)
        level_entry = ttk.Entry(body, textvariable=level, width=18)
        level_entry.grid(row=1, column=1, pady=6)
        ttk.Label(body, text='经验').grid(row=2, column=0, sticky='e', padx=(0, 10), pady=6)
        exp_entry = ttk.Entry(body, textvariable=exp, width=18)
        exp_entry.grid(row=2, column=1, pady=6)
        if not source['has_level']:
            level_entry.state(['disabled'])
        if not source['has_exp']:
            exp_entry.state(['disabled'])

        def accept():
            try:
                if source['has_level']:
                    if level.get().strip() == '':
                        raise ValueError('等级不可留空')
                    T.parse_game_number(source['level_key'], level.get())
                if source['has_exp']:
                    if exp.get().strip() == '':
                        raise ValueError('经验不可留空')
                    T.parse_game_number(source['exp_key'], exp.get())
            except Exception as exc:
                messagebox.showerror('数值无效', str(exc), parent=dialog)
                return
            self.skill_pending[skill_id] = {
                **source, 'level': level.get().strip(), 'exp': exp.get().strip(),
            }
            self._render_skills()
            self.mark_dirty()
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=2, sticky='e', pady=(14, 0))
        ttk.Button(buttons, text='取消', command=dialog.destroy).pack(side='right')
        ttk.Button(buttons, text='加入待保存', command=accept).pack(side='right', padx=8)
        dialog.bind('<Return>', lambda _event: accept())

    def reset_selected_skill(self):
        selected = self.skill_tree.selection()
        if selected and selected[0] in self.skill_pending:
            del self.skill_pending[selected[0]]
            self._render_skills()
            self.mark_dirty()

    def _form_snapshot(self):
        values = {key: var.get() for key, var in self.vars.items()}
        values['aaa'] = '1' if self.aaa.get() else '0'
        return values

    def _changed_form(self):
        current = self._form_snapshot()
        return {key: value for key, value in current.items() if value != self.loaded.get(key, '')}

    def save_all(self):
        if not self.path:
            messagebox.showinfo('尚无存档', '请先启动游戏并建立存档。', parent=self.root)
            return
        changed = self._changed_form()
        if not changed and not self.skill_pending:
            self.status.set('没有需要保存的修改')
            return
        try:
            with T.edit_sol(self.path) as sol:
                count = self._apply_form_changes(sol, changed)
                count += self._apply_skill_changes(sol)
                if count == 0:
                    self.status.set('没有可写入的字段')
                    return
                backup = sol.backup()
                sol.save()
        except (Exception, SystemExit) as exc:
            messagebox.showerror('保存失败', str(exc), parent=self.root)
            return
        self.refresh()
        self.status.set('已保存 %d 项修改 · 备份 %s' % (count, os.path.basename(backup)))

    def _apply_form_changes(self, sol, changed):
        count = 0
        if 'name_1' in changed or 'name_2' in changed:
            for key in ('name_1', 'name_2', 'name'):
                if key not in sol.entries or sol.entries[key]['type'] != 0x02:
                    raise ValueError('存档缺少姓名字段 %s' % key)
            xing, ming = self.vars['name_1'].get().strip(), self.vars['name_2'].get().strip()
            if not xing or not ming:
                raise ValueError('姓和名不可留空')
            sol.set_named('name_1', xing)
            sol.set_named('name_2', ming)
            sol.set_full_name(xing, ming)
            count += 3
        for key, _label in BASIC_FIELDS[2:]:
            if key in changed and key in sol.entries:
                if sol.entries[key]['type'] != 0x02:
                    raise ValueError('%s 不是文字字段' % key)
                sol.set_string(key, changed[key])
                count += 1
        numeric_keys = {key for _group, fields in ATTRIBUTE_GROUPS for key, _label in fields}
        numeric_keys.update(('rrr', 'aaa'))
        for key in numeric_keys:
            if key not in changed or key not in sol.entries:
                continue
            if sol.entries[key]['type'] != 0x00:
                raise ValueError('%s 不是数值字段' % key)
            value = changed[key].strip()
            if value == '':
                raise ValueError('%s 不可留空' % key)
            T.parse_game_number(key, value)
            sol.set_number(key, value)
            count += 1
        return count

    def _apply_skill_changes(self, sol):
        count = 0
        for values in self.skill_pending.values():
            for key, value_name in ((values['level_key'], 'level'), (values['exp_key'], 'exp')):
                if key not in sol.entries or values[value_name] == '—':
                    continue
                value = values[value_name]
                T.parse_game_number(key, value)
                sol.set_number(key, value)
                count += 1
        return count

    def launch_game(self):
        try:
            if T.ruffle_running():
                raise RuntimeError('游戏已经在运行，请先关闭现有窗口')
            package = pkg_root()
            launcher = os.path.join(package, '金庸群俠傳2.exe')
            if not os.path.isfile(launcher):
                raise FileNotFoundError('找不到游戏启动器：%s' % launcher)
            subprocess.Popen([launcher], cwd=package)
            self.status.set('游戏启动器已打开')
        except Exception as exc:
            messagebox.showerror('启动失败', str(exc), parent=self.root)

    @staticmethod
    def _short_path(path):
        parts = path.split(os.path.sep)
        return '…' + os.path.join(*parts[-4:]) if len(parts) >= 4 else path


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
