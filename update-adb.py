import glob
import os
import re
import shutil
import tempfile

import updater

# proxy
proxy = updater.test_proxy('default')

# find out the utilities executable path
adb_dir = updater.find_install_dir('Adb')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    response = updater.query('https://developer.android.com/tools/releases/platform-tools?hl=zh-cn', proxy=proxy)
    remote_version = re.search(r'h4 data\-text="([\d\.]*)', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = None
with open(os.path.join(adb_dir, 'source.properties'), 'r') as f:
    content = f.read()
    local_version = re.search(r'Pkg\.Revision=([\d\.]*)', content, flags=re.M).group(1)
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip'

with tempfile.TemporaryDirectory() as temp_dir:
    download_path = os.path.join(temp_dir, remote_version + '.zip')
    updater.download(remote_url, download_path, proxy=proxy)

    # extract and update files
    updater.taskkill('adb.exe')
    updater.extract_archive(winrar_exec, download_path, temp_dir)
    os.remove(download_path)
    deflate_path = glob.glob(os.path.join(temp_dir, 'platform-tools'))[0]
    shutil.copytree(deflate_path, adb_dir, dirs_exist_ok=True)

updater.finish()
