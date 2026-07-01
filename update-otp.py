import glob
import os
import re
import shutil
import tempfile

import updater

# find out the utilities executable path
otp_path = updater.find_install_dir('Office Tool')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    response = updater.get_redirected_url('https://otp.landian.vip/redirect/download.php?type=runtime&arch=x64')
    remote_version = re.search(r'v([\d\.]*)', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_path = os.path.join(otp_path, 'Office Tool Plus.exe')
local_version = updater.get_file_version(local_path)
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# navigate to download the update
print('Preparing...')
updater.open_exe(local_path)

updater.finish()
