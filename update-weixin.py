import glob
import os
import re
import shutil
import tempfile

import html
import updater

# proxy
proxy = None

# find out the utilities executable path
weixin_path = updater.find_install_dir(r'Tencent\Weixin')

# remove old version directories
version_paths = []
for _name in os.listdir(weixin_path):
    _full = os.path.join(weixin_path, _name)
    if not os.path.isdir(_full):
        continue
    _m = re.match(r'^(\d+(?:\.\d+)*)$', _name)
    if _m:
        try:
            version_paths.append((updater.version.parse(_name), _full))
        except Exception:
            pass
if len(version_paths) >= 2:
    version_paths.sort(key=lambda t: t[0])
    for _, _full in version_paths[:-1]:
        print('Removing old version directory: %s' % _full)
        shutil.rmtree(_full, ignore_errors=True)

# query the remote version
print('Querying...')
try:
    remote_info = None
    for pageid in range(1, 3):
        response = updater.query(f'https://www.52pojie.cn/forum.php?mod=forumdisplay&fid=16&typeid=231&filter=typeid&typeid=231&page={pageid}', proxy=proxy)
        remote_info = re.search(r'(forum\.php[^"]*)[^>]*>微信Windows版 v([\d\.]*)', response, flags=re.M)
        if remote_info:
            remote_version = remote_info.group(2)
            remote_url = remote_info.group(1)
            break
    if not remote_info:
        raise Exception('Remote version not found')
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(weixin_path, 'Weixin.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# navigate to download the update
print('Preparing...')
updater.taskkill('Weixin.exe')
updater.open_url('https://www.52pojie.cn/' + html.unescape(remote_url))
updater.open_explorer(weixin_path)

updater.finish()
