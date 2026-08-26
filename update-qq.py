import json
import os
import re
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
qq_path = updater.find_install_dir(r'Tencent\QQNT')

# query the remote version
print('Querying...')
try:
    response = updater.query('https://qq-web.cdn-go.cn/im.qq.com_new/latest/rainbow/pcConfig.json', proxy=proxy)
    remote_info = json.loads(response)['Windows']
    remote_version = remote_info['version']
    remote_url = remote_info['ntDownloadX64Url']
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(qq_path, 'QQ.exe'))
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
updater.taskkill('QQ.exe')
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
