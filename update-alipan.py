import os
import re
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
listary_path = updater.find_install_dir('aDrive')

# query the remote version
print('Querying...')
try:
    response = updater.query('https://www.alipan.com/', proxy=proxy)
    remote_version = re.search(r'app_windows_download_link:.*aDrive\-([\d\.]+)\.exe', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(listary_path, 'aDrive.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = f'https://cdn.aliyundrive.net/downloads/apps/desktop/aDrive-{remote_version}.exe'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.exe')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.taskkill('aDrive.exe')
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
