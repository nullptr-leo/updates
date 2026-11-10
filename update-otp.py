import os
import re
import shutil
import tempfile

import updater

def update_app():
    # proxy
    proxy = updater.test_proxy('default')

    # find out the utilities executable path
    otp_dir = updater.find_install_dir('Office Tool')
    winrar_exec = updater.find_winrar()

    # homepage
    homepage = 'https://github.com/YerongAI/Office-Tool/releases/latest'

    # query the local version
    local_version = updater.get_file_version(os.path.join(otp_dir, 'Office Tool Plus.exe'))
    print('Local version: %s' % local_version)

    # query the remote version
    print('Querying...')
    try:
        response = updater.query(homepage, proxy=proxy)
        remote_version = re.search(r'Office Tool Plus v([\d\.]*)', response).group(1)
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version):
        updater.already_latest()

    # download package files
    print('Preparing...')
    remote_url = f'https://github.com/YerongAI/Office-Tool/releases/download/v{remote_version}/Office_Tool_v{remote_version}_x64.zip'

    with tempfile.TemporaryDirectory() as temp_dir:
        download_path = os.path.join(temp_dir, os.path.basename(remote_url))
        updater.download(remote_url, download_path, proxy=proxy)

        # extract and update files
        updater.taskkill('Office Tool Plus.exe')
        deflate_dir = os.path.join(temp_dir, 'deflate')
        os.makedirs(deflate_dir)
        updater.extract_archive(winrar_exec, download_path, deflate_dir)
        deflate_path = os.path.join(deflate_dir, 'Office Tool')
        shutil.copytree(deflate_path, otp_dir, dirs_exist_ok=True)

    updater.finish()

if __name__ == '__main__':
    update_app()
