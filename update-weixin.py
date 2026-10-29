import glob
import os
import re
import shutil
import tempfile

import html
import traceback
import updater

def remove_old_version_dirs(install_dir):
    """Remove all but the newest numeric version subdirectories in install_dir.

    A 'version directory' is a folder whose name is a version string like
    '3.9.10'. When more than one exists, keep only the highest and delete the
    rest, so stale versions don't pile up.
    """
    version_paths = []
    for name in os.listdir(install_dir):
        full = os.path.join(install_dir, name)
        if not os.path.isdir(full):
            continue
        if re.match(r'^(\d+(?:\.\d+)*)$', name):
            try:
                version_paths.append((updater.version.parse(name), full))
            except Exception:
                pass
    if len(version_paths) >= 2:
        version_paths.sort(key=lambda t: t[0])
        for _, full in version_paths[:-1]:
            print('Removing old version directory: %s' % full)
            shutil.rmtree(full, ignore_errors=True)

def update_app():
    # proxy
    proxy = None

    # find out the utilities executable path
    weixin_dir = updater.find_install_dir(r'Tencent\Weixin')

    # remove old version directories
    remove_old_version_dirs(weixin_dir)

    # query the remote version
    print('Querying...')
    try:
        remote_info = None
        for pageid in range(1, 3):
            response = updater.query(f'https://www.52pojie.cn/forum.php?mod=forumdisplay&fid=16&typeid=231&filter=typeid&typeid=231&page={pageid}', proxy=proxy)
            remote_info = re.search(r'(forum\.php[^"]*)[^>]*>微信Windows版 v+([\d\.]*)', response, flags=re.M)
            if remote_info:
                remote_version = remote_info.group(2)
                remote_url = remote_info.group(1)
                break
        if not remote_info:
            raise Exception('Remote version not found')
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # query the local version
    local_version = updater.get_file_version(os.path.join(weixin_dir, 'Weixin.exe'))
    print('Local version: %s' % local_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version):
        updater.already_latest()

    # navigate to download the update
    print('Preparing...')
    updater.taskkill('Weixin.exe')
    updater.open_url('https://www.52pojie.cn/' + html.unescape(remote_url))
    # updater.open_explorer(weixin_dir)

    updater.finish()

def match_archive(entries):
    for name in entries:
        n = name.replace('\\', '/')
        if n == 'Weixin' or n.startswith('Weixin/'):
            return True
    return False

def install_archive(archive_path, entries):
    # locate paths (convert the updater's sys.exit into a catchable error)
    weixin_dir = updater.find_install_dir(r'Tencent\Weixin')
    winrar_exec = updater.find_winrar()

    with tempfile.TemporaryDirectory() as temp_dir:
        # extraction failure -> stop here, leave the existing install untouched
        updater.taskkill('Weixin.exe')
        updater.extract_archive(winrar_exec, archive_path, temp_dir)
        deflate_path = glob.glob(os.path.join(temp_dir, 'Weixin'))[0]
        shutil.copytree(deflate_path, weixin_dir, dirs_exist_ok=True)

        # remove old version directories
        remove_old_version_dirs(weixin_dir)

if __name__ == '__main__':
    update_app()
