import glob
import os
import re
import shutil
import tempfile

import updater

# proxy
proxy = updater.test_proxy('default')

# find out the utilities executable path
snowair_path = updater.find_install_dir('SnowAir')

# query the remote version
print('Querying...')
try:
    response = updater.query('https://github.com/CM-idea/SnowAir/releases/latest', proxy=proxy)
    remote_version = re.search(r'SnowAir Lite v([\d\.]*)', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_path = glob.glob(os.path.join(snowair_path, 'SnowAir-Lite-*.exe'))[0]
local_version = updater.get_file_version(local_path)
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = f"https://github.com/CM-idea/SnowAir/releases/download/v{remote_version}-lite/SnowAir-Lite.exe"

with tempfile.TemporaryDirectory() as temp_dir:
    download_path = os.path.join(temp_dir, "SnowAir-Lite.exe")
    updater.download(remote_url, download_path, proxy=proxy)

    # extract and update files
    updater.taskkill("SnowAir-Lite.exe")
    shutil.copy(download_path, os.path.join(snowair_path, "SnowAir-Lite.exe"))

updater.finish()
