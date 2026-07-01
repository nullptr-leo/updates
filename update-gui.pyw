"""GUI for running all update-xxx.py scripts in parallel.

Each row shows a script's live status: querying / downloading (with
percentage) / installing / done / failed, etc. The "Update All" button
launches every update-*.py concurrently and parses their stdout in real
time to update the list.
"""
import glob
import os
import queue
import re
import subprocess
import sys
import threading

import tkinter as tk
from tkinter import ttk

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Status labels
S_WAITING = '等待中'
S_QUERYING = '查询中'
S_PREPARING = '准备中'
S_DOWNLOADING = '下载中'
S_INSTALLING = '安装中'
S_UPTODATE = '已是最新'
S_SKIPPED = '跳过'
S_DONE = '完成'
S_FAILED = '失败'

_TERMINAL = {S_UPTODATE, S_SKIPPED, S_DONE, S_FAILED}
_PCT_RE = re.compile(r'\(([\d.]+)%\)')


def find_scripts():
    """Return sorted [(filename, path)] of update-*.py in the script dir."""
    scripts = []
    for path in glob.glob(os.path.join(SCRIPT_DIR, 'update-*.py')):
        base = os.path.basename(path)
        if base == 'update_gui.py':
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

    def run(self, msg_queue):
        try:
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
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
            'done': done,
        })

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass


class App:
    def __init__(self, root):
        self.root = root
        root.title('Update Scripts')
        root.geometry('660x540')
        root.minsize(520, 320)

        self.msg_queue = queue.Queue()
        self.tasks = {}
        self.running = False
        self.completed = 0
        self.total = 0

        # --- top bar ---
        top = ttk.Frame(root)
        top.pack(fill='x', padx=10, pady=(10, 6))
        self.summary = ttk.Label(top, text='')
        self.summary.pack(side='left')
        self.update_all_btn = ttk.Button(top, text='Update All', command=self.update_all)
        self.update_all_btn.pack(side='right')

        # --- list ---
        body = ttk.Frame(root)
        body.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        columns = ('name', 'status')
        self.tree = ttk.Treeview(body, columns=columns, show='headings', selectmode='browse')
        self.tree.heading('name', text='脚本')
        self.tree.heading('status', text='状态')
        self.tree.column('name', width=200, anchor='w')
        self.tree.column('status', width=280, anchor='center')
        vsb = ttk.Scrollbar(body, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

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
            self.tree.insert('', 'end', values=(pretty_name(base), S_WAITING), tags=('idle',))
        self.total = len(self.scripts)
        self.summary.config(text='共 %d 个脚本' % self.total if self.total else '无脚本')

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

    def _set_row(self, name, status, progress, tag, reason=''):
        if status in (S_FAILED, S_SKIPPED) and reason:
            display = '%s: %s' % (status, reason)
        else:
            display = '%s %s' % (status, progress) if progress else status
        for item in self.tree.get_children(''):
            vals = self.tree.item(item, 'values')
            if vals[0] == name:
                self.tree.item(item, values=(name, display), tags=(tag,))
                if tag == 'running':
                    self.tree.see(item)
                return

    def update_all(self):
        if self.running or not self.scripts:
            return
        # reset all rows
        for item in self.tree.get_children(''):
            cur = self.tree.item(item, 'values')
            self.tree.item(item, values=(cur[0], S_WAITING), tags=('idle',))

        self.running = True
        self.completed = 0
        self.tasks = {}
        self.update_all_btn.config(state='disabled')
        self.summary.config(text='0 / %d' % self.total)

        for base, path in self.scripts:
            name = pretty_name(base)
            task = ScriptTask(name, path)
            self.tasks[name] = task
            self._set_row(name, S_QUERYING, '', 'running')
            threading.Thread(target=task.run, args=(self.msg_queue,), daemon=True).start()

        self.root.after(100, self._process_queue)

    def _process_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                tag = self._tag_for(msg['status'])
                self._set_row(msg['name'], msg['status'], msg.get('progress', ''),
                              tag, msg.get('reason', ''))
                if msg.get('done'):
                    self.completed += 1
        except queue.Empty:
            pass

        self.summary.config(text='%d / %d' % (self.completed, self.total))

        if self.running and self.completed >= self.total:
            self.running = False
            self.update_all_btn.config(state='normal')
            self.summary.config(text='完成 %d / %d' % (self.completed, self.total))

        if self.running:
            self.root.after(100, self._process_queue)

    def _on_close(self):
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
