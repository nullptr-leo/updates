import glob
import re
import os
import requests
import shutil
import time
import win32api as win
import subprocess
import tempfile
import traceback

from contextlib import closing
from distutils.dir_util import copy_tree
from packaging import version

# update channel
channel = 'shared'
requests.packages.urllib3.disable_warnings()

# find out the utilities executable path
prog_lists = [ 'C:\\Program Files', 'D:\\Program Files', 'E:\\Program Files' ]
for prog_path in prog_lists:
    if 'everything_path' not in locals().keys():
        if os.path.exists(os.path.join(prog_path, 'Everything')):
            everything_path = os.path.join(prog_path, 'Everything')
    if 'winrar_exec' not in locals().keys():
        if os.path.exists(os.path.join(prog_path, 'WinRAR')):
            winrar_exec = os.path.join(prog_path, 'WinRAR\\WinRAR.exe')

print(everything_path)
print(winrar_exec)

# query the server edge version
print('Querying...')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"
}

try:
    response = requests.get('https://www.voidtools.com/forum/viewtopic.php?t=9787', headers=headers)
    remote_info = re.search(r'Everything\-([\d\.]*)', response.text, flags=re.M)
    remote_version = remote_info.group(1)
except:
    print('Query failed.')
    traceback.print_exc()
    os.system('pause')
    exit()

print('Remote version: %s' % remote_version)

# query the local edge version
local_info = win.GetFileVersionInfo(os.path.join(everything_path, 'Everything.exe'), os.sep)
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

# download package files
remote_url = 'https://www.voidtools.com/Everything-' + remote_version + 'b.x64.zip'
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
subprocess.call(['taskkill', '/F', '/IM', 'Everything.exe'], stdout=open('NUL', 'w'), stderr=subprocess.STDOUT)
subprocess.call([winrar_exec, 'x', '-o+-', '-inul', download_path, temp_dir])
os.remove(download_path)

copy_tree(temp_dir, everything_path)
shutil.rmtree(temp_dir)

print('Finished.')
time.sleep(0.5)
