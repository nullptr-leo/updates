import glob
import os
import re
import shutil
import tempfile

import traceback
import updater

def update_app():
    # proxy
    proxy = None

    # find out the utilities executable path
    bcompare_dir = updater.find_install_dir('Beyond Compare')

    # query the remote version
    print('Querying...')
    try:
        response = updater.query('https://www.ghxi.com/beyondcompare.html', proxy=proxy)
        remote_version = re.search(r'Beyond Compare v([\d\.]*)', response, flags=re.M).group(1)
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # query the local version
    local_version = updater.get_file_version(os.path.join(bcompare_dir, 'BCompare.exe'))
    print('Local version: %s' % local_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version):
        updater.already_latest()

    # navigate to download the update
    print('Preparing...')
    updater.taskkill('BCompare.exe')
    updater.open_url('https://www.ghxi.com/beyondcompare.html')
    updater.open_explorer(bcompare_dir)

    updater.finish()

def match_archive(entries):
    for name in entries:
        n = name.replace('\\', '/')
        if n == 'Beyond_Compare' or n.startswith('Beyond_Compare/'):
            return True
    return False

def install_archive(archive_path, entries):
    bcompare_dir = updater.find_install_dir('Beyond Compare')
    winrar_exec = updater.find_winrar()

    with tempfile.TemporaryDirectory() as temp_dir:
        # extraction failure -> stop here, leave the existing install untouched
        updater.taskkill('BCompare.exe')
        updater.extract_archive(winrar_exec, archive_path, temp_dir)
        deflate_path = glob.glob(os.path.join(temp_dir, 'Beyond_Compare\\BCompare'))[0]

        # strip the three config XMLs so they are not copied into the install
        for cfg in ('BCPreferences.xml', 'BCSettings.xml', 'BCState.xml'):
            os.remove(os.path.join(deflate_path, cfg))

        # copy the remaining files in (dirs_exist_ok keeps existing config)
        shutil.copytree(deflate_path, bcompare_dir, dirs_exist_ok=True)


if __name__ == '__main__':
    update_app()
