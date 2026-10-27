import os
import re
import shutil
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
autorun_dir = updater.find_install_dir('Autoruns')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    response = updater.query('https://learn.microsoft.com/zh-cn/sysinternals/downloads/autoruns', proxy=proxy)
    remote_info = re.search(r'Autoruns v([^< ]*)', response, flags=re.M | re.I)
    if not remote_info:
        remote_info = re.search(r'Windows v([^< ]*)', response, flags=re.M | re.I)
    remote_version = remote_info.group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
autorun_path = os.path.join(autorun_dir, 'Autoruns64.exe')
local_version = updater.get_file_version(autorun_path)
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = 'https://download.sysinternals.com/files/Autoruns.zip'

with tempfile.TemporaryDirectory() as temp_dir:
    download_path = os.path.join(temp_dir, remote_version + '.zip')
    updater.download(remote_url, download_path, proxy=proxy)

    # extract and update files
    updater.taskkill('Autoruns64.exe')
    updater.extract_archive(winrar_exec, download_path, temp_dir)
    os.remove(download_path)
    shutil.copy(os.path.join(temp_dir, 'Autoruns64.exe'), autorun_path)

updater.finish()
