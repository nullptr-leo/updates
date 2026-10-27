import glob
import os
import re
import shutil
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
otp_dir = updater.find_install_dir('Office Tool')

# query the remote version
print('Querying...')
try:
    response = updater.get_redirected_url('https://otp.landian.vip/redirect/download.php?type=runtime&arch=x64', proxy=proxy)
    remote_version = re.search(r'v([\d\.]*)', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
otp_path = os.path.join(otp_dir, 'Office Tool Plus.exe')
local_version = updater.get_file_version(otp_path)
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# navigate to download the update
print('Preparing...')
updater.open_exe(otp_path)

updater.finish()
