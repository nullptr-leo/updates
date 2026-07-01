import os
import re
import tempfile

import requests
import updater

# find out the utilities executable path
python_path = updater.find_install_dir('Python')
winrar_exec = updater.find_winrar()
print(python_path)
print(winrar_exec)

# query the remote version
print('Querying...')
try:
    response = requests.get('https://www.python.org/downloads/')
    remote_version = re.search(r'python-(.*)-amd64.exe', response.text, flags=re.M | re.I).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(python_path, 'python.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest_str(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = 'https://www.python.org/ftp/python/' + remote_version + '/python-' + remote_version + '-amd64.exe'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.exe')
updater.download(remote_url, download_path)

# extract and update files
updater.taskkill('python.exe')
updater.run_installer(download_path)
os.remove(download_path)

updater.finish()
