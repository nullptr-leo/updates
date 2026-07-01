import os
import re
import tempfile

import requests
import updater

# find out the utilities executable path
git_path = updater.find_install_dir('Git')
winrar_exec = updater.find_winrar()
print(git_path)
print(winrar_exec)

# query the remote version
print('Querying...')
try:
    response = requests.get('https://git-scm.com/install/windows')
    remote_version = re.search(r'Latest version: ([\d\.]*)', response.text, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(git_path, 'git-cmd.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest_str(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = 'https://github.com/git-for-windows/git/releases/download/v' + remote_version + '.windows.1/Git-' + remote_version + '-64-bit.exe'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.exe')
updater.download(remote_url, download_path)

# extract and update files
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
