"""Common utilities for software update scripts."""
import os
import sys
import time
import shutil
import tempfile
import traceback
import subprocess
from contextlib import closing
from distutils.dir_util import copy_tree

import requests
import win32api as win
from packaging import version

requests.packages.urllib3.disable_warnings()

# Directories to search for installed software
SEARCH_PATHS = [
    'C:\\Program Files',
    'C:\\Program Files (x86)',
    'D:\\Program Files',
    'E:\\Program Files',
]


def find_install_dir(folder_name):
    """Find an installed software directory by folder name."""
    for prog_path in SEARCH_PATHS:
        path = os.path.join(prog_path, folder_name)
        if os.path.exists(path):
            return path
    return None


def find_winrar():
    """Find the WinRAR executable path."""
    for prog_path in SEARCH_PATHS:
        path = os.path.join(prog_path, 'WinRAR', 'WinRAR.exe')
        if os.path.exists(path):
            return path
    return None


def fail_and_exit():
    """Print failure info, pause, and exit."""
    print('Query failed.')
    traceback.print_exc()
    os.system('pause')
    sys.exit(1)


def get_file_version(exe_path):
    """Get the file version string (a.b.c.d) of an executable."""
    info = win.GetFileVersionInfo(exe_path, os.sep)
    ms, ls = info['FileVersionMS'], info['FileVersionLS']
    return '%d.%d.%d.%d' % (win.HIWORD(ms), win.LOWORD(ms), win.HIWORD(ls), win.LOWORD(ls))


def get_file_version_parts(exe_path):
    """Return (HIWORD(ms), LOWORD(ms), HIWORD(ls), LOWORD(ls)) for custom formatting."""
    info = win.GetFileVersionInfo(exe_path, os.sep)
    ms, ls = info['FileVersionMS'], info['FileVersionLS']
    return win.HIWORD(ms), win.LOWORD(ms), win.HIWORD(ls), win.LOWORD(ls)


def download(url, dest_path):
    """Download a file with a progress indicator."""
    with closing(requests.get(url, stream=True)) as response:
        chunk_size = 1024
        content_size = int(response.headers['content-length'])
        data_count = 0
        with open(dest_path, 'wb') as f:
            for data in response.iter_content(chunk_size=chunk_size):
                f.write(data)
                data_count += len(data)
                progress = (data_count / content_size) * 100
                print('Download: %.2fMB (%.2f%%)' % (data_count / 1024 / 1024, progress), end='\r')


def taskkill(image_name):
    """Kill a running process by image name."""
    subprocess.call(
        ['taskkill', '/F', '/IM', image_name],
        stdout=open('NUL', 'w'),
        stderr=subprocess.STDOUT,
    )


def extract_archive(winrar_exec, archive_path, dest_dir):
    """Extract an archive using WinRAR."""
    subprocess.call([winrar_exec, 'x', '-o+-', '-inul', archive_path, dest_dir])


def run_installer(installer_path):
    """Run an installer executable."""
    subprocess.call([installer_path])


def is_latest(remote_ver, local_ver):
    """Return True if the local version is up to date (version.parse comparison)."""
    return version.parse(remote_ver) <= version.parse(local_ver)


def is_latest_str(remote_ver, local_ver):
    """String-based up-to-date check."""
    return remote_ver <= local_ver


def already_latest():
    print('Already latest.')
    time.sleep(0.5)
    sys.exit(0)


def finish():
    print('Finished.')
    time.sleep(0.5)
