import glob
import os
import re
import shutil
import tempfile

import updater

def update_app():
    # proxy
    proxy = None

    # find out the utilities executable path
    vscode_dir = updater.find_install_dir('Microsoft VS Code')

    # query the remote version
    print('Querying...')
    try:
        response = updater.get_redirected_url('https://code.visualstudio.com/sha/download?build=stable&os=win32-x64', proxy=proxy)
        remote_version = re.search(r'x64-([\d\.]*)\.', response, flags=re.M).group(1)
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # query the local version
    vscode_path = os.path.join(vscode_dir, 'Code.exe')
    local_version = updater.get_file_version(vscode_path)
    print('Local version: %s' % local_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version):
        updater.already_latest()

    # navigate to download the update
    print('Preparing...')
    updater.taskkill('Code.exe')
    updater.open_exe(vscode_path)

    updater.finish()

if __name__ == '__main__':
    update_app()
