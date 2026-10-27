import glob
import os
import re
import shutil
import tempfile

import updater

# proxy
proxy = updater.test_proxy('default')

# find out the utilities executable path
fluentcleaner_dir = updater.find_install_dir('Fluent Cleaner')
winrar_exec = updater.find_winrar()

# query the remote version
print('Querying...')
try:
    response = updater.query('https://github.com/builtbybel/FluentCleaner/releases/latest', proxy=proxy)
    remote_version = re.search(r'FluentCleaner ([\d\.]*)', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(fluentcleaner_dir, 'FCleaner.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# download package files
print('Preparing...')
remote_url = f"https://github.com/builtbybel/FluentCleaner/releases/download/{remote_version}/FluentCleaner-win-x64.zip"
temp_dir = tempfile.mkdtemp()
download_path = os.path.join(temp_dir, remote_version + '.zip')
updater.download(remote_url, download_path, proxy=proxy)

# extract and update files
updater.taskkill('FCleaner.exe')
updater.extract_archive(winrar_exec, download_path, temp_dir)
os.remove(download_path)
deflate_path = glob.glob(os.path.join(temp_dir, 'FluentCleaner-win-x64'))[0]
shutil.copytree(deflate_path, fluentcleaner_dir, dirs_exist_ok=True)
shutil.rmtree(temp_dir)

updater.finish()
