import os
import re
import shutil
import tempfile

import updater

def update_app():
    # proxy
    proxy = None

    # find out the utilities executable path
    procexp_dir = updater.find_install_dir('Process Explorer')
    winrar_exec = updater.find_winrar()

    # homepage
    homepage = 'https://learn.microsoft.com/en-us/sysinternals/downloads/process-explorer'

    # query the local version
    procexp_path = os.path.join(procexp_dir, 'procexp64.exe')
    local_version = updater.get_file_version(procexp_path)
    print('Local version: %s' % local_version)

    # query the remote version
    print('Querying...')
    try:
        response = updater.query(homepage, proxy=proxy)
        remote_info = re.search(r'Process Explorer v([\d.]+)', response, flags=re.M | re.I)
        if not remote_info:
            remote_info = re.search(r'<h1[^>]*>[^<]*v([\d.]+)\s*</h1>', response, flags=re.M | re.I)
        remote_version = remote_info.group(1)
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version):
        updater.already_latest()

    # download package files
    print('Preparing...')
    remote_url = 'https://download.sysinternals.com/files/ProcessExplorer.zip'

    with tempfile.TemporaryDirectory() as temp_dir:
        download_path = os.path.join(temp_dir, remote_version + '.zip')
        updater.download(remote_url, download_path, proxy=proxy)

        # extract and update files
        updater.taskkill('procexp64.exe')
        updater.extract_archive(winrar_exec, download_path, temp_dir)
        os.remove(download_path)
        shutil.copy(os.path.join(temp_dir, 'procexp64.exe'), procexp_path)

    updater.finish()

if __name__ == '__main__':
    update_app()
