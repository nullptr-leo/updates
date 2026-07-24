import glob
import os
import re
import shutil
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
bcompare_path = updater.find_install_dir('Beyond Compare')

# query the remote version
print('Querying...')
try:
    response = updater.query('https://www.ghxi.com/beyondcompare.html', proxy=proxy)
    remote_version = re.search(r'Beyond Compare v([\d\.]*)', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(bcompare_path, 'BCompare.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# navigate to download the update
print('Preparing...')
updater.taskkill('BCompare.exe')
updater.open_url('https://www.ghxi.com/beyondcompare.html')
updater.open_explorer(bcompare_path)

updater.finish()
