import json
import os
import re
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
kiro_dir = updater.find_install_dir('Kiro')

# query the remote version
print('Querying...')
try:
    response = updater.query('https://kiro.dev/downloads', proxy=proxy)
    remote_version = re.search(r'>IDE ([\d\.]+)', response).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(kiro_dir, 'Kiro.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = f'https://prod.download.desktop.kiro.dev/releases/stable/win32-x64/signed/{remote_version}/kiro-ide-{remote_version}-stable-win32-x64.exe'

with tempfile.TemporaryDirectory() as temp_dir:
    download_path = os.path.join(temp_dir, remote_version + '.exe')
    updater.download(remote_url, download_path, proxy=proxy)

    # extract and update files
    updater.taskkill('Kiro.exe')
    updater.run_installer(download_path)

updater.finish()
