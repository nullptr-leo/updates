"""Common utilities for software update scripts."""
import os
import sys
import time
import traceback
import subprocess
from contextlib import closing

import requests
import win32api as win
import urllib3
from packaging import version

urllib3.disable_warnings()

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
    print(f'{folder_name} not found.')
    sys.exit(1)


def find_winrar():
    """Find the WinRAR executable path."""
    return os.path.join(find_install_dir('WinRAR'), 'WinRAR.exe')


def fail_and_exit():
    """Print failure info, pause, and exit."""
    print('Query failed.')
    traceback.print_exc()
    os.system('pause')
    sys.exit(1)


def get_file_version_parts(exe_path):
    """Return (HIWORD(ms), LOWORD(ms), HIWORD(ls), LOWORD(ls)) for custom formatting."""
    info = win.GetFileVersionInfo(exe_path, os.sep)
    ms, ls = info['FileVersionMS'], info['FileVersionLS']
    return win.HIWORD(ms), win.LOWORD(ms), win.HIWORD(ls), win.LOWORD(ls)


def get_file_version(exe_path):
    """Get the file version string (a.b.c.d) of an executable."""
    return '%d.%d.%d.%d' % get_file_version_parts(exe_path)


def test_proxy(proxy, enable_test=False):
    """Test if a proxy is working by querying a known URL."""
    if not enable_test:
        return proxy
    try:
        response = requests.get('https://www.google.com/', proxies={'https': proxy})
        return proxy if response.status_code == 200 else None
    except Exception:
        return None


def query(url, headers=None, proxy=None):
    """Query a URL and return the response text."""
    try:
        response = requests.get(url, headers=headers, proxies={'https': proxy} if proxy else None)
        return response.text
    except Exception:
        fail_and_exit()


def get_redirected_url(url, headers=None, proxy=None):
    """Return the final URL after following redirects, without downloading content."""
    proxies = {'https': proxy, 'http': proxy} if proxy else None
    try:
        response = requests.head(url, headers=headers, proxies=proxies, allow_redirects=True)
        if response.status_code < 400:
            return response.url
        # Fallback: some servers reject HEAD, use stream GET and close immediately
        response = requests.get(url, headers=headers, proxies=proxies, stream=True, allow_redirects=True)
        response.close()
        return response.url
    except Exception:
        fail_and_exit()


def download(url, dest_path, proxy=None):
    """Download a file with a progress indicator."""
    with closing(requests.get(url, stream=True, proxies={'https': proxy, 'http': proxy} if proxy else None)) as response:
        chunk_size = 65536  # 64KB
        content_size = int(response.headers.get('content-length', 0))
        data_count = 0
        with open(dest_path, 'wb') as f:
            for data in response.iter_content(chunk_size=chunk_size):
                f.write(data)
                data_count += len(data)
                if content_size:
                    progress = (data_count / content_size) * 100
                    print('Download: %.2fMB (%.2f%%)' % (data_count / 1024 / 1024, progress), end='\r')
                else:
                    print('Download: %.2fMB' % (data_count / 1024 / 1024), end='\r')


def taskkill(image_name):
    """Kill a running process by image name."""
    subprocess.call(
        ['taskkill', '/F', '/IM', image_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def extract_archive(winrar_exec, archive_path, dest_dir):
    """Extract an archive using WinRAR."""
    subprocess.call([winrar_exec, 'x', '-o+-', '-inul', archive_path, dest_dir])


def run_installer(installer_path):
    """Run an installer executable."""
    subprocess.call([installer_path])


def open_url(url):
    """Open a URL in the default browser."""
    os.startfile(url)


def open_explorer(path):
    """Open File Explorer and navigate to the given directory."""
    subprocess.Popen(['explorer', path])


def open_exe(exe_path):
    """Open an executable file."""
    os.startfile(exe_path)


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
    time.sleep(0.3)
