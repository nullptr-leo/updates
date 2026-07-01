import glob
import os
import re
import shutil
import time
import tempfile

import updater

# proxy
proxy = updater.test_proxy('socks5h://127.0.0.1:7890')

# find out the utilities executable path
snipaste_dir = updater.find_install_dir('Snipaste')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    response = updater.get_redirected_url('https://dl.snipaste.com/win-x64-cn')
    remote_version = re.search(r'Snipaste-([\d\.]*)', response, flags=re.M | re.I).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
snipaste_path = os.path.join(snipaste_dir, 'Snipaste.exe')
local_version = updater.get_file_version(snipaste_path)
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest_str(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = 'https://dl.snipaste.com/win-x64-cn'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.zip')
updater.download(remote_url, download_path)

# extract and update files
updater.taskkill('Snipaste.exe')
updater.extract_archive(winrar_exec, download_path, temp_dir)
os.remove(download_path)
shutil.copytree(temp_dir, snipaste_dir, dirs_exist_ok=True)
shutil.rmtree(temp_dir)

updater.finish()
