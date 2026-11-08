import os
import re
import shutil
import tempfile

import updater

def update_app():
    # proxy
    proxy = updater.test_proxy('default')

    # find out the utilities executable path
    innounp_dir = updater.find_install_dir('innounp')
    winrar_exec = updater.find_winrar()

    # homepage
    homepage = 'https://github.com/jrathlev/InnoUnpacker-Windows-GUI/releases/latest'

    # query the remote version
    print('Querying...')
    url = ('https://raw.githubusercontent.com/jrathlev/InnoUnpacker-Windows-GUI/refs/heads/master/innounp-2/docs/innounp-cl.txt')
    try:
        response = updater.query(url, proxy=proxy)
        remote_version = re.search(r'(?m)^[ \t]*v?(\d+\.\d+(?:\.\d+)*)\b', response).group(1)
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # query the local version
    local_version = updater.get_file_version(os.path.join(innounp_dir, 'innounp.exe'))
    print('Local version: %s' % local_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version):
        updater.already_latest()

    # download package files
    print('Preparing...')
    remote_url = 'https://github.com/jrathlev/InnoUnpacker-Windows-GUI/raw/refs/heads/master/innounp-2/bin/innounp-2.zip'

    with tempfile.TemporaryDirectory() as temp_dir:
        download_path = os.path.join(temp_dir, os.path.basename(remote_url))
        updater.download(remote_url, download_path, proxy=proxy)

        # extract and update files
        updater.taskkill('innounp.exe')
        deflate_dir = os.path.join(temp_dir, 'deflate')
        os.makedirs(deflate_dir)
        updater.extract_archive(winrar_exec, download_path, deflate_dir)
        shutil.copytree(deflate_dir, innounp_dir, dirs_exist_ok=True)

    # make innounp.exe available from any command prompt
    if updater.append_env_var('PATH', [innounp_dir]):
        print('Added %s to PATH' % innounp_dir)

    updater.finish()

if __name__ == '__main__':
    update_app()
