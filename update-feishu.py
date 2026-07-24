import json
import os
import re
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
feishu_path = updater.find_install_dir('Feishu')

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
local_version = updater.get_file_version(os.path.join(feishu_path, 'Feishu.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.exe')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.taskkill('Feishu.exe')
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
