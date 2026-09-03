import json
import os

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
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(qq_path, 'QQ.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# navigate to download the update
# The official CDN rejects direct downloads (HTTP 403), so open the official
# download page instead of fetching the installer ourselves.
print('Preparing...')
updater.taskkill('QQ.exe')
updater.open_url('https://im.qq.com/pcqq/')

updater.finish()
