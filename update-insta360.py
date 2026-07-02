import os
import re
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
insta360_path = updater.find_install_dir('Insta360 Studio')

# query the remote version
print('Querying...')
try:
    response = updater.query('https://www.insta360.com/cn/download/insta360-x4', proxy=proxy)
    remote_url = re.findall(r'(https://wassets\.insta360\.com/[^"]*\.exe)', response, flags=re.M)[-1]
    remote_version = re.search(r'Insta360_Studio_([\d\.]*)', remote_url, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(insta360_path, 'Insta360 Studio.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.exe')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.taskkill('Insta360 Studio.exe')
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
