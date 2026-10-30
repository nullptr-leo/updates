"""Common utilities for software update scripts."""
import os
import sys
import time
import traceback
import subprocess
import zipfile
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
    'C:\\Program Files\\WindowsApps',
    'C:\\Users\\Leo\\AppData\\Local\\Programs',
]

def find_install_dir(folder_name):
    """Find an installed software directory by folder name.

    folder_name may be a single name or a list of candidate names; the first
    one that exists (in any of SEARCH_PATHS) is returned. Exits if none are
    found.
    """
    if isinstance(folder_name, str):
        names = [folder_name]
    else:
        names = list(folder_name)
    for name in names:
        for prog_path in SEARCH_PATHS:
            path = os.path.join(prog_path, name)
            if os.path.exists(path):
                return path
    print('%s not found.' % ', '.join(names))
    sys.exit(1)


def find_winrar():
    """Find the WinRAR executable path."""
    return os.path.join(find_install_dir('WinRAR'), 'WinRAR.exe')


def fail_and_exit():
    """Print failure info, pause (if interactive), and exit."""
    print('Query failed.')
    traceback.print_exc()
    if sys.stdin.isatty() and not os.environ.get('UPDATE_NONINTERACTIVE'):
        os.system('pause')
    sys.exit(2)


def get_file_version_parts(exe_path):
    """Return (HIWORD(ms), LOWORD(ms), HIWORD(ls), LOWORD(ls)) for custom formatting."""
    info = win.GetFileVersionInfo(exe_path, os.sep)
    ms, ls = info['FileVersionMS'], info['FileVersionLS']
    return win.HIWORD(ms), win.LOWORD(ms), win.HIWORD(ls), win.LOWORD(ls)


def get_file_version(exe_path):
    """Get the file version string (a.b.c.d) of an executable."""
    return '%d.%d.%d.%d' % get_file_version_parts(exe_path)


def get_appx_version(package_name):
    """Get the version of a Windows AppX package by its package name.

    package_name is the package name (e.g. 'Microsoft.WindowsTerminal').
    Returns the version string 'major.minor.build.revision'.
    """
    try:
        from winrt.windows.management.deployment import PackageManager
        pm = PackageManager()
        for package in pm.find_packages():
            if package.id.name == package_name:
                v = package.id.version
                return '%d.%d.%d.%d' % (v.major, v.minor, v.build, v.revision)
    except Exception:
        fail_and_exit()
    print(f'{package_name} not found.')
    sys.exit(1)


def test_proxy(proxy):
    """Test if a proxy is working by querying a known URL."""
    if proxy in ('default', 'system'):
        proxy = os.environ.get('UPDATE_PROXY_ADDR')
    if not proxy:
        return None
    if not os.environ.get('UPDATE_PROXY_CONNECTION_TEST'):
        return proxy
    try:
        response = requests.get('https://www.google.com/', proxies={'https': proxy}, timeout=15)
        return proxy if response.status_code == 200 else None
    except Exception:
        return None


def query(url, headers=None, proxy=None):
    """Query a URL and return the response text."""
    try:
        response = requests.get(url, headers=headers, proxies={'https': proxy} if proxy else None, timeout=30, verify=False)
        response.raise_for_status()
        return response.text
    except Exception:
        fail_and_exit()


def get_redirected_url(url, headers=None, proxy=None):
    """Return the final URL after following redirects, without downloading content."""
    proxies = {'https': proxy, 'http': proxy} if proxy else None
    try:
        response = requests.head(url, headers=headers, proxies=proxies, allow_redirects=True, verify=False, timeout=(10, 30))
        if response.status_code < 400:
            return response.url
        # Fallback: some servers reject HEAD, use stream GET and close immediately
        response = requests.get(url, headers=headers, proxies=proxies, stream=True, allow_redirects=True, verify=False, timeout=(10, 30))
        response.close()
        return response.url
    except Exception:
        fail_and_exit()


def download(url, dest_path, proxy=None):
    """Download a file with a progress indicator."""
    with closing(requests.get(url, stream=True, proxies={'https': proxy, 'http': proxy} if proxy else None, timeout=(30, 120), verify=False)) as response:
        response.raise_for_status()
        chunk_size = 65536  # 64KB
        content_size = int(response.headers.get('content-length', 0))
        data_count = 0
        with open(dest_path, 'wb') as f:
            for data in response.iter_content(chunk_size=chunk_size):
                f.write(data)
                data_count += len(data)
                if content_size:
                    progress = (data_count / content_size) * 100
                    print('Download: %.2fMB / %.2fMB (%.2f%%)' % (
                        data_count / 1024 / 1024,
                        content_size / 1024 / 1024, progress), end='\r')
                else:
                    print('Download: %.2fMB' % (data_count / 1024 / 1024), end='\r')


def taskkill(image_name):
    """Kill a running process by image name."""
    subprocess.call(
        ['taskkill', '/F', '/IM', image_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def extract_archive(winrar_exec, archive_path, dest_dir):
    """Extract an archive using WinRAR."""
    subprocess.call([winrar_exec, 'x', '-o+-', '-inul', '-ibck', archive_path, dest_dir],
                    creationflags=subprocess.CREATE_NO_WINDOW)


def list_archive(archive_path):
    """Return the internal entry paths of an archive as a list of strings.

    Paths are normalized to use '/' as the separator so callers can parse the
    structure without caring about the archive format.
    Supported formats: .zip (stdlib), .7z (py7zr), .rar (unrar library, no
    command line). For .rar it reads the entry table via the `unrar` library
    (ctypes, no subprocess); an error is raised if `unrar`/UnRAR64.dll is missing.
    """
    lower = archive_path.lower()
    if lower.endswith('.zip'):
        with zipfile.ZipFile(archive_path) as z:
            return [e.replace('\\', '/') for e in z.namelist()]
    if lower.endswith('.7z'):
        import py7zr
        with py7zr.SevenZipFile(archive_path) as z:
            return [e.replace('\\', '/') for e in z.getnames()]
    if lower.endswith('.rar'):
        # Point the loader at UnRAR64.dll placed next to this script.
        os.environ['UNRAR_LIB_PATH'] = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'UnRAR64.dll')
        from unrar.rarfile import RarFile
        with RarFile(archive_path) as z:
            return [e.replace('\\', '/') for e in z.namelist()]
    raise ValueError('不支持的压缩格式: %s' % archive_path)


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


def remove_desktop_shortcut(name):
    """Delete a desktop shortcut (.lnk) from the current user's Desktop.

    `name` may include or omit the '.lnk' extension. If the shortcut does not
    exist, this is a no-op (no error raised).
    """
    if not name.lower().endswith('.lnk'):
        name += '.lnk'
    desktop_dir = os.path.join(os.path.expanduser('~'), 'Desktop')
    shortcut = os.path.join(desktop_dir, name)
    if os.path.exists(shortcut):
        os.remove(shortcut)


def is_latest(remote_ver, local_ver, lexicographic=False):
    """Return True if the local version is up to date.
    By default versions are compared semantically via packaging.version.parse.
    Pass lexicographic=True to compare them as plain strings instead.
    """
    if lexicographic:
        return remote_ver <= local_ver
    return version.parse(remote_ver) <= version.parse(local_ver)


def already_latest():
    print('Already latest.')
    time.sleep(0.5)
    sys.exit(0)


def finish():
    print('Finished.')
    time.sleep(0.3)
