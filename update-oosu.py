import os
import re
import shutil
import tempfile

import updater

# find out the utilities executable path
oosu_path = updater.find_install_dir('OOSU')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    response = updater.query('https://www.oo-software.com/en/download/current/ooshutup10')
    remote_version = re.search(r'Build ([\d\.]*)', response, flags=re.M | re.I).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(oosu_path, 'OOSU10.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = 'https://dl5.oo-software.com/files/ooshutup10/OOSU10.exe'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, 'OOSU10.exe')
updater.download(remote_url, download_path)

# extract and update files
updater.taskkill('OOSU10.exe')
shutil.copy(os.path.join(temp_dir, 'OOSU10.exe'), os.path.join(oosu_path, 'OOSU10.exe'))
shutil.rmtree(temp_dir)

updater.finish()
