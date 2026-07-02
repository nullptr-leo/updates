import os
import re
import tempfile

import updater

# proxy
proxy = updater.test_proxy('default')

# query the remote version
print('Querying...')
try:
    response = updater.query('https://github.com/microsoft/terminal/releases/latest', proxy=proxy)
    remote_version = re.search(r'Windows Terminal v([\d\.]*)', response, flags=re.M | re.I).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_appx_version('Microsoft.WindowsTerminal')
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = f'https://github.com/microsoft/terminal/releases/download/v{remote_version}/Microsoft.WindowsTerminal_{remote_version}_8wekyb3d8bbwe.msixbundle'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.msixbundle')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.taskkill('WindowsTerminal.exe')
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
