import glob
import json
import os
import requests
import shutil
import time
import datetime
import win32api as win
import subprocess
import tempfile
import traceback
import re
import socket

from contextlib import closing
from distutils.dir_util import copy_tree
from packaging import version

# update channel
requests.packages.urllib3.disable_warnings()

# find out the utilities executable path
prog_lists = [ 'C:\\Program Files', 'D:\\Program Files', 'E:\\Program Files' ]
for prog_path in prog_lists:
    if 'vlc_path' not in locals().keys():
        if os.path.exists(os.path.join(prog_path, 'VLC')):
            vlc_path = os.path.join(prog_path, 'VLC')
    if 'winrar_exec' not in locals().keys():
        if os.path.exists(os.path.join(prog_path, 'WinRAR')):
            winrar_exec = os.path.join(prog_path, 'WinRAR\\WinRAR.exe')

print(vlc_path)
print(winrar_exec)

# query the server edge version
print('Querying...')

try:
    remote_url = 'https://artifacts.videolan.org/vlc-3.0/nightly-win64/'
    response = requests.get(remote_url)
    remote_info = re.search(r'(\d{8}-\d{4})', response.text, flags=re.M|re.I)
    remote_date = remote_info.group(1)
    remote_url += remote_date + '/'
    response = requests.get(remote_url)
    remote_info = re.search(r'([^"]*\.7z)', response.text, flags=re.M|re.I)
    remote_info = remote_info.group(1)
    remote_url += remote_info
    remote_version = remote_info.split('-')[1]
    remote_date = remote_date.split('-')[0]
except:
    print('Query failed.')
    traceback.print_exc()
    os.system('pause')
    exit()

print('Remote version: %s (%s)' % (remote_version, remote_date))

# query the local edge version
vlc_dir = vlc_path
vlc_path = os.path.join(vlc_path, 'vlc.exe')
local_info = win.GetFileVersionInfo(vlc_path, os.sep)
local_date = time.strftime('%Y%m%d', time.localtime(os.path.getmtime(vlc_path)))
(ms, ls) = (local_info['FileVersionMS'],  local_info['FileVersionLS'])
local_version = '%d.%d.%d.%d' % (win.HIWORD(ms), win.LOWORD(ms), win.HIWORD(ls), win.LOWORD(ls))
print('Local version: %s (%s)' % (local_version, local_date))

# check if update is needed
if version.parse(remote_version) <= version.parse(local_version) and remote_date <= local_date:
    print('Already latest.')
    time.sleep(0.5)
    exit()

# get the package download url
print('Preparing...')

# download package files
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.exe')
with closing(requests.get(remote_url, stream=True)) as response:
    chunk_size = 1024
    content_size = int(response.headers['content-length'])
    data_count = 0
    with open(download_path, 'wb') as dload_file:
        for data in response.iter_content(chunk_size=chunk_size):
            dload_file.write(data)
            data_count = data_count + len(data)
            progress = (data_count / content_size) * 100
            line = 'Download: %.2fMB (%.2f%%)' % (data_count / 1024 / 1024, progress)
            print(line, end='\r')

# extract and update files
subprocess.call(['taskkill', '/F', '/IM', 'vlc.exe'], stdout=open('NUL', 'w'), stderr=subprocess.STDOUT)
subprocess.call([winrar_exec, 'x', '-o+-', '-inul', download_path, temp_dir])
os.remove(download_path)

deflate_path = glob.glob(os.path.join(temp_dir, 'vlc-*'))[0]
shutil.rmtree(vlc_dir)
copy_tree(deflate_path, vlc_dir)
shutil.rmtree(temp_dir)

print('Finished.')
time.sleep(0.5)
