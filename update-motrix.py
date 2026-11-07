import os
import re
import shutil
import tempfile

import updater

def update_app():
    # proxy
    proxy = updater.test_proxy('default')

    # find out the utilities executable path
    motrix_dir = updater.find_install_dir('Motrix')
    winrar_exec = updater.find_winrar()

    # homepage
    homepage = 'https://github.com/agalwood/Motrix/releases/latest'

    # query the remote version
    print('Querying...')
    try:
        response = updater.query(homepage, proxy=proxy)
        remote_version = re.search(r'Release v([\d\.]*)', response).group(1)
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # query the local version
    local_version = updater.get_file_version(os.path.join(motrix_dir, 'Motrix.exe'))
    print('Local version: %s' % local_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version):
        updater.already_latest()

    # download package files
    print('Preparing...')
    remote_url = f'https://github.com/agalwood/Motrix/releases/download/v{remote_version}/Motrix-{remote_version}-win.zip'

    with tempfile.TemporaryDirectory() as temp_dir:
        download_path = os.path.join(temp_dir, os.path.basename(remote_url))
        updater.download(remote_url, download_path, proxy=proxy)

        # extract and update files
        updater.taskkill('Motrix.exe')
        deflate_dir = os.path.join(temp_dir, 'deflate')
        os.makedirs(deflate_dir)
        updater.extract_archive(winrar_exec, download_path, deflate_dir)
        shutil.copytree(deflate_dir, motrix_dir, dirs_exist_ok=True)

    updater.finish()

if __name__ == '__main__':
    update_app()
