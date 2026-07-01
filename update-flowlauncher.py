import glob
import os
import re
import shutil
import tempfile
from distutils.dir_util import copy_tree

import requests
import updater

# find out the utilities executable path
flowlauncher_path = updater.find_install_dir('FlowLauncher')
winrar_exec = updater.find_winrar()
print(flowlauncher_path)
print(winrar_exec)

# query the remote version
print('Querying...')
try:
    response = requests.get('https://github.com/Flow-Launcher/Flow.Launcher/releases/latest')
    remote_version = re.search(r'Release v([\d\.]*)', response.text, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(flowlauncher_path, 'Flow.Launcher.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = 'https://github.com/Flow-Launcher/Flow.Launcher/releases/download/v' + remote_version + '/Flow-Launcher-Portable.zip'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.zip')
updater.download(remote_url, download_path)

# extract and update files
updater.taskkill('Flow.Launcher.exe')
updater.extract_archive(winrar_exec, download_path, temp_dir)
os.remove(download_path)
deflate_path = glob.glob(os.path.join(temp_dir, 'FlowLauncher'))[0]
copy_tree(deflate_path, flowlauncher_path)
shutil.rmtree(temp_dir)

updater.finish()
