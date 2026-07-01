import glob
import os
import re
import shutil
import time
import tempfile

import updater

# proxy
proxy = updater.test_proxy('socks5h://127.0.0.1:7890')

# find out the utilities executable path
vlc_dir = updater.find_install_dir('VLC')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    remote_url = 'https://artifacts.videolan.org/vlc-3.0/nightly-win64/'
    response = updater.query(remote_url, proxy=proxy)
    remote_date = re.search(r'(\d{8}-\d{4})', response, flags=re.M | re.I).group(1)
    remote_url += remote_date + '/'
    response = updater.query(remote_url, proxy=proxy)
    remote_info = re.search(r'([^"]*\.7z)', response, flags=re.M | re.I).group(1)
    remote_url += remote_info
    remote_version = remote_info.split('-')[1]
    remote_date = remote_date.split('-')[0]
except Exception:
    updater.fail_and_exit()
print('Remote version: %s (%s)' % (remote_version, remote_date))

# query the local version
vlc_path = os.path.join(vlc_dir, 'vlc.exe')
local_version = updater.get_file_version(vlc_path)
local_date = time.strftime('%Y%m%d', time.localtime(os.path.getmtime(vlc_path)))
print('Local version: %s (%s)' % (local_version, local_date))

# check if update is needed
if updater.is_latest(remote_version, local_version) and remote_date <= local_date:
    updater.already_latest()

# download package files
print('Preparing...')
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.7z')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.taskkill('vlc.exe')
updater.extract_archive(winrar_exec, download_path, temp_dir)
os.remove(download_path)
deflate_path = glob.glob(os.path.join(temp_dir, 'vlc-*'))[0]
shutil.rmtree(vlc_dir)
shutil.copytree(deflate_path, vlc_dir, dirs_exist_ok=True)
shutil.rmtree(temp_dir)

updater.finish()
