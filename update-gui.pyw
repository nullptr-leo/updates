"""GUI for running all update-xxx.py scripts in parallel.

Each row shows a script's live status: querying / downloading (with
percentage) / installing / done / failed, etc. The "Update All" button
launches every update-*.py concurrently and parses their stdout in real
time to update the list.
"""
import glob
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time

import tkinter as tk
from tkinter import ttk

import win32api
import win32con
import win32gui

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'update-config.json')

# Status labels
S_WAITING = '等待中'
S_QUERYING = '查询中'
S_PREPARING = '准备中'
S_DOWNLOADING = '下载中'
S_INSTALLING = '安装中'
S_UPTODATE = '已是最新'
S_SKIPPED = '未安装'
S_DONE = '完成'
S_FAILED = '失败'

_TERMINAL = {S_UPTODATE, S_SKIPPED, S_DONE, S_FAILED}
_PCT_RE = re.compile(r'\(([\d.]+)%\)')


def load_ignored():
    """Return the set of ignored program names from update-config.json."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        return set(cfg.get('ignored_program', []))
    except (OSError, ValueError):
        return set()


def find_scripts():
    """Return sorted [(filename, path)] of update-*.py in the script dir."""
    ignored = load_ignored()
    scripts = []
    for path in glob.glob(os.path.join(SCRIPT_DIR, 'update-*.py')):
        base = os.path.basename(path)
        if pretty_name(base) in ignored:
            continue
        scripts.append((base, path))
    scripts.sort(key=lambda x: x[0])
    return scripts


def pretty_name(filename):
    name = os.path.splitext(filename)[0]
    if name.startswith('update-'):
        name = name[len('update-'):]
    return name


class ScriptTask:
    """Runs one update script as a subprocess and streams its output."""

    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.process = None
        self.finished_status = None
        self.fail_reason = ''
        self.last_emitted_pct = None
        self.seen_download = False
        self.local_version = ''
        self.remote_version = ''

    def run(self, msg_queue):
        try:
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['UPDATE_NONINTERACTIVE'] = '1'
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            self.process = subprocess.Popen(
                [sys.executable, '-u', self.path],
                cwd=SCRIPT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=creationflags,
            )
            self._read_output(msg_queue)
            code = self.process.wait()
        except Exception as e:
            self.finished_status = S_FAILED
            self.fail_reason = str(e) or repr(e)
            self._emit(msg_queue, S_FAILED, '', reason=self.fail_reason, done=True)
            return

        # exit code 1 means the script chose to skip (e.g. software not
        # installed, query failed); treat it as skipped rather than failed.
        if code == 1:
            self.finished_status = S_SKIPPED
            if not self.fail_reason:
                self.fail_reason = '退出码 1'
        elif self.finished_status is None:
            if code == 0:
                self.finished_status = S_DONE
            else:
                self.finished_status = S_FAILED
                self.fail_reason = '退出码 %d' % code
        self._emit(msg_queue, self.finished_status, '', reason=self.fail_reason, done=True)

    def _read_output(self, msg_queue):
        buf = ''
        while True:
            chunk = self.process.stdout.read1(4096)
            if not chunk:
                break
            buf += chunk.decode('utf-8', errors='replace')
            parts = re.split(r'[\r\n]', buf)
            buf = parts[-1]  # keep incomplete tail
            for seg in parts[:-1]:
                self._handle_segment(seg, msg_queue)
        if buf.strip():
            self._handle_segment(buf, msg_queue)

    def _handle_segment(self, seg, msg_queue):
        seg = seg.strip()
        if not seg:
            return
        m_remote = re.search(r'Remote version:\s*(.*)', seg)
        m_local = re.search(r'Local version:\s*(.*)', seg)
        if m_remote:
            self.remote_version = m_remote.group(1).strip()
            self._emit(msg_queue, S_QUERYING, '')
            return
        if m_local:
            self.local_version = m_local.group(1).strip()
            self._emit(msg_queue, S_QUERYING, '')
            return
        if 'Querying' in seg:
            self._emit(msg_queue, S_QUERYING, '')
        elif 'Already latest' in seg:
            self.finished_status = S_UPTODATE
            self._emit(msg_queue, S_UPTODATE, '')
        elif 'Preparing' in seg:
            self._emit(msg_queue, S_PREPARING, '')
        elif 'Download:' in seg:
            m = _PCT_RE.search(seg)
            if m:
                pct = float(m.group(1))
                self.seen_download = True
                # throttle: only emit when the percent changed by >= 1
                if (self.last_emitted_pct is None
                        or abs(pct - self.last_emitted_pct) >= 1.0
                        or pct >= 99.9):
                    self.last_emitted_pct = pct
                    self._emit(msg_queue, S_DOWNLOADING, '%.1f%%' % pct)
                if pct >= 99.9:
                    self._emit(msg_queue, S_INSTALLING, '')
            else:
                # no content-length: show downloaded size as progress
                self.seen_download = True
                self._emit(msg_queue, S_DOWNLOADING, seg.replace('Download:', '').strip())
        elif 'Finished' in seg:
            self.finished_status = S_DONE
            self._emit(msg_queue, S_DONE, '')
        elif 'Query failed' in seg:
            self.finished_status = S_FAILED
            if not self.fail_reason:
                self.fail_reason = '查询失败'
            self._emit(msg_queue, S_FAILED, '', reason=self.fail_reason)
        elif 'not found' in seg:
            self.finished_status = S_FAILED
            self.fail_reason = seg
            self._emit(msg_queue, S_FAILED, '', reason=self.fail_reason)
        elif self.finished_status == S_FAILED:
            # capture the most specific line from a traceback as the reason
            if (seg and not seg.startswith('Traceback')
                    and not seg.startswith('File ')
                    and not seg.startswith('During handling')):
                self.fail_reason = seg

    def _emit(self, msg_queue, status, progress, reason='', done=False):
        msg_queue.put({
            'name': self.name,
            'status': status,
            'progress': progress,
            'reason': reason,
            'local_version': self.local_version,
            'remote_version': self.remote_version,
            'done': done,
        })

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass


class TrayIcon:
    """Minimal system tray icon built on pywin32."""

    WM_TRAY = win32con.WM_USER + 20
    ID_TRAY = 1

    def __init__(self, icon_path, tooltip, on_restore, on_exit):
        self.icon_path = icon_path
        self.tooltip = tooltip
        self.on_restore = on_restore
        self.on_exit = on_exit
        self.hwnd = None
        self.hicon = None
        self.visible = False
        # keep a stable reference to the wndproc so it is not garbage collected
        self._wnd_proc = self._wnd_proc
        self._register_class()
        self._create_window()
        self._load_icon()

    def _register_class(self):
        self._wc = win32gui.WNDCLASS()
        self._wc.hInstance = win32api.GetModuleHandle(None)
        self._wc.lpszClassName = 'UpdateScriptsTrayWnd'
        self._wc.lpfnWndProc = self._wnd_proc
        self.class_atom = win32gui.RegisterClass(self._wc)

    def _create_window(self):
        self.hwnd = win32gui.CreateWindow(
            self.class_atom, 'UpdateScriptsTray', 0, 0, 0, 0, 0,
            win32con.HWND_MESSAGE, 0, self._wc.hInstance, None)

    def _load_icon(self):
        if self.icon_path and os.path.exists(self.icon_path):
            self.hicon = win32gui.LoadImage(
                None, self.icon_path, win32con.IMAGE_ICON, 0, 0,
                win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
        if not self.hicon:
            self.hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == self.WM_TRAY:
            if lparam == win32con.WM_LBUTTONDBLCLK:
                self.on_restore()
            elif lparam == win32con.WM_RBUTTONUP:
                self._show_menu()
        elif msg == win32con.WM_DESTROY:
            self.remove()
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def show(self):
        if self.visible:
            return
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        nid = (self.hwnd, self.ID_TRAY, flags, self.WM_TRAY, self.hicon, self.tooltip)
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
        self.visible = True

    def remove(self):
        if not self.visible:
            return
        nid = (self.hwnd, self.ID_TRAY, 0, 0, 0, '')
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
        except Exception:
            pass
        self.visible = False

    def _show_menu(self):
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1, '显示窗口')
        win32gui.AppendMenu(menu, win32con.MF_STRING, 2, '退出')
        pos = win32api.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        cmd = win32gui.TrackPopupMenu(
            menu, win32con.TPM_RETURNCMD | win32con.TPM_NONOTIFY,
            pos[0], pos[1], 0, self.hwnd, None)
        win32gui.DestroyMenu(menu)
        if cmd == 1:
            self.on_restore()
        elif cmd == 2:
            self.on_exit()


class App:
    def __init__(self, root):
        self.root = root
        root.title('Update Scripts')

        # Set size and centered position
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        w = 860
        h = 540
        x = (sw - w) // 2
        y = (sh - h) // 2
        root.geometry('%dx%d+%d+%d' % (w, h, x, y))
        root.minsize(680, 320)

        # window icon
        self.ico_path = os.path.join(SCRIPT_DIR, 'update.ico')
        root.iconbitmap(default=self.ico_path)

        self.msg_queue = queue.Queue()
        self.tasks = {}
        self.running = False
        self.completed = 0
        self.total = 0
        self.active_tasks = set()
        self._processing = False
        self.tray = None
        self._auto_timer = None
        self._update_session_active = False

        # --- top bar ---
        top = ttk.Frame(root)
        top.pack(fill='x', padx=10, pady=(10, 6))
        self.summary = ttk.Label(top, text='')
        self.summary.pack(side='left')
        self.update_all_btn = ttk.Button(top, text='Update All', command=self.update_all)
        self.update_all_btn.pack(side='right')
        self.tray_btn = ttk.Button(top, text='最小化到托盘', command=self.minimize_to_tray)
        self.tray_btn.pack(side='right', padx=(0, 8))
        self.auto_var = tk.BooleanVar(value=False)
        self.auto_chk = ttk.Checkbutton(
            top, text='定时更新', variable=self.auto_var, command=self.on_auto_toggle)
        self.auto_chk.pack(side='right', padx=(0, 8))
        self.last_update_lbl = ttk.Label(top, text='上次更新：—')
        self.last_update_lbl.pack(side='right', padx=(0, 8))

        # --- list ---
        body = ttk.Frame(root)
        body.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        columns = ('name', 'local', 'remote', 'status')
        self.tree = ttk.Treeview(body, columns=columns, show='headings', selectmode='browse')
        self.tree.heading('name', text='软件名称')
        self.tree.heading('local', text='本地版本')
        self.tree.heading('remote', text='远程版本')
        self.tree.heading('status', text='状态')
        self.tree.column('name', width=160, anchor='w')
        self.tree.column('local', width=110, anchor='center')
        self.tree.column('remote', width=110, anchor='center')
        self.tree.column('status', width=260, anchor='center')
        vsb = ttk.Scrollbar(body, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

        self.tree.bind('<Double-1>', self._on_double_click)

        # row colors by tag
        self.tree.tag_configure('idle', foreground='#808080')
        self.tree.tag_configure('running', foreground='#1a73e8')
        self.tree.tag_configure('done', foreground='#1e8e3e')
        self.tree.tag_configure('uptodate', foreground='#5f6368')
        self.tree.tag_configure('skipped', foreground='#b26a00')
        self.tree.tag_configure('failed', foreground='#d93025')

        self._populate()
        root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _populate(self):
        self.scripts = find_scripts()
        for base, _ in self.scripts:
            self.tree.insert('', 'end', values=(pretty_name(base), '', '', S_WAITING),
                             tags=('idle',))
        self.total = len(self.scripts)
        self.summary.config(text='共 %d 个软件' % self.total if self.total else '无软件')

    def _tag_for(self, status):
        if status == S_DONE:
            return 'done'
        if status == S_UPTODATE:
            return 'uptodate'
        if status == S_SKIPPED:
            return 'skipped'
        if status == S_FAILED:
            return 'failed'
        if status == S_WAITING:
            return 'idle'
        return 'running'

    def _set_row(self, name, status, progress, tag, reason='',
                 local_version='', remote_version=''):
        if status in (S_FAILED, S_SKIPPED) and reason:
            display = '%s: %s' % (status, reason)
        else:
            display = '%s %s' % (status, progress) if progress else status
        for item in self.tree.get_children(''):
            vals = self.tree.item(item, 'values')
            if vals[0] == name:
                self.tree.item(item, values=(name, local_version, remote_version, display),
                               tags=(tag,))
                if tag == 'running':
                    self.tree.see(item)
                return

    def update_all(self):
        if self.running or not self.scripts:
            return
        self._update_session_active = True
        # reset all rows
        for item in self.tree.get_children(''):
            cur = self.tree.item(item, 'values')
            self.tree.item(item, values=(cur[0], '', '', S_WAITING), tags=('idle',))

        self.running = True
        self.completed = 0
        self.tasks = {}
        self.active_tasks = set()
        self.update_all_btn.config(state='disabled')
        self.summary.config(text='0 / %d' % self.total)

        for base, path in self.scripts:
            name = pretty_name(base)
            task = ScriptTask(name, path)
            self.tasks[name] = task
            self.active_tasks.add(name)
            self._set_row(name, S_QUERYING, '', 'running')
            threading.Thread(target=task.run, args=(self.msg_queue,), daemon=True).start()

        self._ensure_processing()

    def update_one(self, name):
        """Run a single update script for the given program name."""
        if name in self.active_tasks:
            return
        path = None
        for base, p in self.scripts:
            if pretty_name(base) == name:
                path = p
                break
        if not path:
            return
        task = ScriptTask(name, path)
        self.tasks[name] = task
        self.active_tasks.add(name)
        self._update_session_active = True
        self._set_row(name, S_QUERYING, '', 'running')
        self.update_all_btn.config(state='disabled')
        threading.Thread(target=task.run, args=(self.msg_queue,), daemon=True).start()
        self._ensure_processing()

    def _on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        name = self.tree.item(item, 'values')[0]
        self.update_one(name)

    def _record_update_time(self):
        self.last_update_lbl.config(
            text='上次更新：' + time.strftime('%Y-%m-%d %H:%M:%S'))

    def _ensure_processing(self):
        if not self._processing:
            self._processing = True
            self.root.after(100, self._process_queue)

    def _process_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                tag = self._tag_for(msg['status'])
                self._set_row(msg['name'], msg['status'], msg.get('progress', ''),
                              tag, msg.get('reason', ''),
                              msg.get('local_version', ''), msg.get('remote_version', ''))
                if msg.get('done'):
                    self.active_tasks.discard(msg['name'])
                    if self.running:
                        self.completed += 1
        except queue.Empty:
            pass

        if self.active_tasks:
            self.update_all_btn.config(state='disabled')
        else:
            self.update_all_btn.config(state='normal')
            self._processing = False

        if self.running:
            if self.completed >= self.total:
                self.running = False
                self.summary.config(text='完成 %d / %d' % (self.completed, self.total))
            else:
                self.summary.config(text='%d / %d' % (self.completed, self.total))
        elif not self.active_tasks:
            self.summary.config(text='共 %d 个软件' % self.total if self.total else '无软件')

        if self._update_session_active and not self.active_tasks:
            self._update_session_active = False
            self._record_update_time()

        if self.active_tasks:
            self.root.after(100, self._process_queue)

    def minimize_to_tray(self):
        """Hide the window and show a system tray icon instead."""
        if self.tray is None:
            self.tray = TrayIcon(
                self.ico_path, 'Update Scripts',
                on_restore=self.restore_from_tray, on_exit=self.exit_app)
        self.root.withdraw()
        self.tray.show()

    def on_auto_toggle(self):
        """Start or stop the periodic update timer based on the checkbox."""
        if self.auto_var.get():
            self._schedule_auto_update()
        else:
            self._cancel_auto_update()

    def _schedule_auto_update(self):
        self._auto_timer = self.root.after(10 * 60 * 1000, self._auto_update)

    def _cancel_auto_update(self):
        if self._auto_timer is not None:
            self.root.after_cancel(self._auto_timer)
            self._auto_timer = None

    def _auto_update(self):
        # run an update pass only when idle (not already updating)
        if not self.running and self.scripts:
            self.update_all()
        # reschedule the next check
        self._auto_timer = self.root.after(10 * 60 * 1000, self._auto_update)

    def restore_from_tray(self):
        """Bring the window back from the tray."""
        if self.tray:
            self.tray.remove()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def exit_app(self):
        """Quit the application from the tray menu."""
        if self.tray:
            self.tray.remove()
        self._on_close()

    def _on_close(self):
        self._cancel_auto_update()
        for task in self.tasks.values():
            task.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use('clam')
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
