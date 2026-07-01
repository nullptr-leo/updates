import glob
import json
import os
import requests
import shutil
import time
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
    if 'git_path' not in locals().keys():
        if os.path.exists(os.path.join(prog_path, 'Git')):
            git_path = os.path.join(prog_path, 'Git')
    if 'winrar_exec' not in locals().keys():
        if os.path.exists(os.path.join(prog_path, 'WinRAR')):
            winrar_exec = os.path.join(prog_path, 'WinRAR\\WinRAR.exe')

print(git_path)
print(winrar_exec)

# query the server edge version
print('Querying...')

try:
    response = requests.get('https://git-scm.com/install/windows')
    remote_info = re.search(r'Latest version: ([\d\.]*)', response.text, flags=re.M)
    remote_version = remote_info.group(1)
except:
    print('Query failed.')
    traceback.print_exc()
    os.system('pause')
    exit()

print('Remote version: %s' % remote_version)

# query the local edge version
local_info = win.GetFileVersionInfo(os.path.join(git_path, 'git-cmd.exe'), os.sep)
(ms, ls) = (local_info['FileVersionMS'],  local_info['FileVersionLS'])
local_version = '%d.%d.%d.%d' % (win.HIWORD(ms), win.LOWORD(ms), win.HIWORD(ls), win.LOWORD(ls))
print('Local version: %s' % local_version)

# check if update is needed
if remote_version <= local_version:
    print('Already latest.')
    time.sleep(0.5)
    exit()

# get the package download url
print('Preparing...')

remote_url = 'https://github.com/git-for-windows/git/releases/download/v' + remote_version + '.windows.1/Git-' + remote_version + '-64-bit.exe'

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
subprocess.call([download_path])
os.remove(download_path)

print('Finished.')
time.sleep(0.5)
