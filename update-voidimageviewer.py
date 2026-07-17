import os
import re
import shutil
import tempfile

import updater

# find out the utilities executable path
viv_path = updater.find_install_dir('Void Image Viewer')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Accept-Encoding": "gzip, deflate",
}

try:
    response = updater.query('https://www.voidtools.com/zh-cn/downloads', headers=headers)
    remote_version = re.search(r'voidImageViewer\-([\d\.]*)\.x64', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(viv_path, 'voidImageViewer.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = f'https://www.voidtools.com/voidImageViewer-{remote_version}.x64.en-US.zip'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.zip')
updater.download(remote_url, download_path)

# extract and update files
updater.taskkill('voidImageViewer.exe')
updater.extract_archive(winrar_exec, download_path, temp_dir)
os.remove(download_path)
shutil.copytree(temp_dir, viv_path, dirs_exist_ok=True)
shutil.rmtree(temp_dir)

updater.finish()
