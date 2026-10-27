import json
import os
import re
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
feishu_dir = updater.find_install_dir('Feishu')

# query the remote version
print('Querying...')
try:
    response = updater.query('https://www.feishu.cn/api/package_info?platform=16', proxy=proxy)
    remote_version = re.search(r'Windows@V([\d\.]+)', response).group(1)
    remote_url = json.loads(response)['data']['download_link']
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(feishu_dir, 'Feishu.exe'))
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
    updater.taskkill('Feishu.exe')
    updater.run_installer(download_path)

# remove the stale desktop shortcut named 飞书
desktop_dir = os.path.join(os.path.expanduser('~'), 'Desktop')
feishu_shortcut = os.path.join(desktop_dir, '飞书.lnk')
if os.path.exists(feishu_shortcut):
    os.remove(feishu_shortcut)

updater.finish()
