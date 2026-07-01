import glob
import os
import re
import shutil
import subprocess
import tempfile
from distutils.dir_util import copy_tree

import requests
import updater

# proxy
proxy = updater.test_proxy('socks5h://127.0.0.1:7890')

# find out the utilities executable path
ffmpeg_path = updater.find_install_dir('ffmpeg')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    response = updater.query('https://github.com/BtbN/FFmpeg-Builds/releases/latest', proxy=proxy)
    remote_info = re.search(r'Auto-Build (\(*)(\d*)-(\d*)-(\d*)', response, flags=re.M)
    remote_version = remote_info.group(2) + remote_info.group(3) + remote_info.group(4)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
ffmpeg_pipe = subprocess.Popen(['ffmpeg', '-version'], stdout=subprocess.PIPE)
ffmpeg_pipe.wait()
local_info = ffmpeg_pipe.stdout.readlines()[0].decode('utf8')
local_version = re.search(r'version N-[^-]*-[^-]*-([^ ]*)', local_info, flags=re.M).group(1)
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.zip')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.taskkill('ffmpeg.exe')
updater.extract_archive(winrar_exec, download_path, temp_dir)
os.remove(download_path)
deflate_path = glob.glob(os.path.join(temp_dir, 'ffmpeg-*'))[0]
copy_tree(deflate_path, ffmpeg_path)
shutil.rmtree(temp_dir)

updater.finish()
