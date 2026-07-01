import os
import requests
import shutil
import time
import win32api as win
import subprocess
import tempfile
import traceback
import re

from contextlib import closing
from distutils.dir_util import copy_tree
from packaging import version

requests.packages.urllib3.disable_warnings()

# find out the utilities executable path
drive_list = ['C:\\']
prog_lists = [ 'Program Files', 'Program Files (x86)' ]
for drive in drive_list:
    for prog_path in prog_lists:
        if 'autorun_path' not in locals().keys():
            if os.path.exists(os.path.join(drive, os.path.join(prog_path, 'Autoruns'))):
                autorun_path = os.path.join(drive, os.path.join(prog_path, 'Autoruns'))
        if 'winrar_exec' not in locals().keys():
            if os.path.exists(os.path.join(drive, os.path.join(prog_path, 'WinRAR'))):
                winrar_exec = os.path.join(drive, os.path.join(prog_path, 'WinRAR\\WinRAR.exe'))

print(autorun_path)
print(winrar_exec)

# query the remote version
print('Querying...')

try:
    remote_url = 'https://learn.microsoft.com/zh-cn/sysinternals/downloads/autoruns'
    response = requests.get(remote_url)
    remote_info = re.search(r'Autoruns v([^< ]*)', response.text, flags=re.M|re.I)
    if not remote_info:
        remote_info = re.search(r'Windows v([^< ]*)', response.text, flags=re.M|re.I)
    remote_version = remote_info.group(1)
except:
    print('Query failed.')
    traceback.print_exc()
    os.system('pause')
    exit()

print('Remote version: %s' % remote_version)

# query the local version
local_info = win.GetFileVersionInfo(os.path.join(autorun_path, 'Autoruns64.exe'), os.sep)
(ms, ls) = (local_info['FileVersionMS'],  local_info['FileVersionLS'])
local_version = '%d.%d.%d.%d' % (win.HIWORD(ms), win.LOWORD(ms), win.HIWORD(ls), win.LOWORD(ls))
print('Local version: %s' % local_version)

# check if update is needed
if version.parse(remote_version) <= version.parse(local_version):
    print('Already latest.')
    time.sleep(0.5)
    exit()

# get the package download url
print('Preparing...')

remote_url = 'https://download.sysinternals.com/files/Autoruns.zip'

# download package files
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.zip')
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
subprocess.call(['taskkill', '/F', '/IM', 'Autoruns64.exe'], stdout=open('NUL', 'w'), stderr=subprocess.STDOUT)
subprocess.call([winrar_exec, 'x', '-o+-', '-inul', download_path, temp_dir])
os.remove(download_path)

shutil.copy(os.path.join(temp_dir, 'Autoruns64.exe'), os.path.join(autorun_path, 'Autoruns64.exe'))
shutil.rmtree(temp_dir)

print('Finished.')
time.sleep(0.5)
