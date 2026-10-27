import json
import os
import re
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
workbuddy_dir = updater.find_install_dir(r'WorkBuddy')

# query the remote version
print('Querying...')
try:
    remote_url = r'https://www.workbuddy.cn/v2/update?platform=workbuddy-win32-x64-user'
    response = updater.query(remote_url, proxy=proxy)
    remote_info = json.loads(response)
    remote_version = '.'.join(remote_info.get('version').split('.')[0:-1])
    remote_url = remote_info.get('url')
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(workbuddy_dir, 'WorkBuddy.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')

with tempfile.TemporaryDirectory() as temp_dir:
    download_path = os.path.join(temp_dir, remote_version + '.exe')
    updater.download(remote_url, download_path, proxy=proxy)

    # extract and update files
    updater.taskkill('WorkBuddy.exe')
    updater.run_installer(download_path)

updater.finish()
