import json
import os
import re
import shutil
import tempfile

import updater

def update_app():
    # proxy
    proxy = updater.test_proxy('default')

    # find out the utilities executable path
    snowshot_dir = updater.find_install_dir('SnowShot')
    winrar_exec = updater.find_winrar()

    # homepage
    homepage = 'https://github.com/mg-chao/snow-apps/releases/latest'

    # query the local version
    snowshot_path = os.path.join(snowshot_dir, 'bin', 'snow_shot.exe')
    local_version = updater.get_file_version(snowshot_path)
    print('Local version: %s' % local_version)

    # query the remote version
    # the repo releases several apps, so only vX.Y.Z_snow-shot tags count here
    print('Querying...')
    try:
        response = updater.query(homepage, proxy=proxy)
        remote_version = re.search(r'Snow Shot ([\d\.]*)', response, flags=re.M).group(1)
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version):
        updater.already_latest()

    # download package files
    print('Preparing...')
    remote_url = f'https://github.com/mg-chao/snow-apps/releases/download/v{remote_version}_snow-shot/snow-shot-{remote_version}-windows-x64-portable.zip'

    with tempfile.TemporaryDirectory() as temp_dir:
        download_path = os.path.join(temp_dir, os.path.basename(remote_url))
        updater.download(remote_url, download_path, proxy=proxy)

        # extract and update files
        updater.taskkill('snow_shot.exe')
        updater.taskkill('snow-shot-updater.exe')
        updater.extract_archive(winrar_exec, download_path, temp_dir)
        os.remove(download_path)
        shutil.copytree(temp_dir, snowshot_dir, dirs_exist_ok=True)

    updater.finish()


if __name__ == '__main__':
    update_app()
