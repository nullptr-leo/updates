import os
import re
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
ticktick_path = updater.find_install_dir('TickTick')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    response = updater.get_redirected_url('https://dida365.com/static/getApp/download?type=win64', proxy=proxy)
    remote_version = '.'.join(re.search(r'x64_([\d]*)', response, flags=re.M).group(1))
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(ticktick_path, 'TickTick.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = 'https://dida365.com/static/getApp/download?type=win64'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.exe')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.taskkill('TickTick.exe')
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
