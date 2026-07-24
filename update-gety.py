import os
import re
import tempfile

import updater

# proxy
proxy = updater.test_proxy('default')

# find out the utilities executable path
gety_path = updater.find_install_dir('Gety')

# query the remote version
print('Querying...')
try:
    response = updater.query('https://gety.ai/zh/download/', proxy=proxy)
    remote_version = re.search(r'v([\d\.]+)', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(gety_path, 'Gety.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = f'https://dl.gety.ai/Gety-x64-{remote_version}-beta.exe'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.exe')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.taskkill('Gety.exe')
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
