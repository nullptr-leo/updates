import json
import os
import re
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
qianwen_dir = ['QianwenApp', 'Qianwen\\QianwenApp']
qianwen_path = updater.find_install_dir(qianwen_dir)

# query the remote version
print('Querying...')
try:
    response = updater.query('https://download.qianwen.com/pcdownload/qianwenpc?ch=pcqwen@homepage_official&platform=pc', proxy=proxy)
    remote_url = json.loads(response)['data']['url']
    remote_version = re.search(r'QianwenPC_V([\d\.]+)', remote_url).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(qianwen_path, 'qianwen.exe'))
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
updater.taskkill('qianwen.exe')
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
