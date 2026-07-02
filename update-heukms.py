import glob
import os
import re
import shutil
import tempfile

import updater

# proxy
proxy = updater.test_proxy('default')

# find out the utilities executable path
heu_path = updater.find_install_dir('HEU KMS Activator')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    response = updater.query('https://github.com/zbezj/HEU_KMS_Activator/releases/latest', proxy=proxy)
    remote_version = re.search(r'HEU_KMS_Activator_v([\d\.]*)', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_path = glob.glob(os.path.join(heu_path, 'HEU_KMS_Activator*'))[0]
local_version = updater.get_file_version(local_path)
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = f'https://github.com/zbezj/HEU_KMS_Activator/releases/download/{remote_version}/HEU_KMS_Activator_v{remote_version}.rar'
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.rar')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.extract_archive(winrar_exec, download_path, temp_dir)
os.remove(download_path)
deflate_path = glob.glob(os.path.join(temp_dir, 'HEU_KMS_Activator*'))[0]
shutil.copy(deflate_path, heu_path)
shutil.rmtree(temp_dir)
os.remove(local_path)

updater.finish()
