import os
import re
import tempfile

import updater

# proxy
proxy = updater.test_proxy('default')

# find out the utilities executable path
listary_path = updater.find_install_dir('Listary')

# query the remote version
print('Querying...')
try:
    response = updater.query('https://www.listary.net/v7', proxy=proxy)
    remote_version = re.search(r'v([\d\.]+) Beta', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(listary_path, 'Listary.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = f'https://dl.listary.net/v7/Listary.exe'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.exe')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.taskkill('Listary.exe')
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
