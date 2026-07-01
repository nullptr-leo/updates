import glob
import os
import re
import shutil
import tempfile

import updater

# proxy
proxy = updater.test_proxy('socks5h://127.0.0.1:7890')

# find out the utilities executable path
trafficmonitor_path = updater.find_install_dir('Traffic Monitor')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    response = updater.query('https://github.com/zhongyang219/TrafficMonitor/releases/latest', proxy=proxy)
    remote_version = re.search(r'V([\d\.]*)', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
parts = updater.get_file_version_parts(os.path.join(trafficmonitor_path, 'TrafficMonitor.exe'))
local_version = '%d.%d%d.%d' % parts
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = 'https://github.com/zhongyang219/TrafficMonitor/releases/download/V' + remote_version + '/TrafficMonitor_V' + remote_version + '_x64.zip'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.zip')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.taskkill('TrafficMonitor.exe')
updater.extract_archive(winrar_exec, download_path, temp_dir)
os.remove(download_path)
deflate_path = glob.glob(os.path.join(temp_dir, 'TrafficMonitor'))[0]
shutil.copytree(deflate_path, trafficmonitor_path, dirs_exist_ok=True)
shutil.rmtree(temp_dir)

updater.finish()
