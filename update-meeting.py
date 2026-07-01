import os
import re
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
meeting_path = updater.find_install_dir(r'Tencent\WeMeet')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    remote_url = r'https://meeting.tencent.com/web-service/query-download-info?q=%5B%7B%22package-type%22%3A%22app%22%2C%22channel%22%3A%220300000000%22%2C%22platform%22%3A%22windows%22%2C%22arch%22%3A%22x86_64%22%7D%5D&nonce=6HxmShiJM2AAfZ2e'
    response = updater.query(remote_url, proxy=proxy)
    remote_version = re.search(r'_([\d\.]*)_x86_64', response, flags=re.M).group(1)
    remote_url = re.search(r'(https://.*\.exe)', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(meeting_path, 'wemeetapp.exe'))
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
updater.taskkill('wemeetapp.exe')
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
