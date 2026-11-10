import os
import re
import tempfile

import updater

def update_app():
    # proxy
    proxy = updater.test_proxy('default')

    # find out the utilities executable path
    foxmail_dir = updater.find_install_dir('Foxmail')

    # homepage
    homepage = 'https://www.foxmail.com/'

    # query the local version
    local_version = updater.get_file_version(os.path.join(foxmail_dir, 'Foxmail.exe'))
    print('Local version: %s' % local_version)

    # query the remote version
    print('Querying...')
    try:
        redirected_url = updater.get_redirected_url(f'{homepage}/win/download', proxy=proxy)
        remote_version = re.search(r'FoxmailSetup_([\d\.]*)\.exe', redirected_url).group(1)
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version):
        updater.already_latest()

    # download package files
    print('Preparing...')

    with tempfile.TemporaryDirectory() as temp_dir:
        download_path = os.path.join(temp_dir, 'FoxmailSetup_' + remote_version + '.exe')
        updater.download(f'{homepage}/win/download', download_path, proxy=proxy)

        # install
        updater.taskkill('Foxmail.exe')
        updater.run_installer(download_path)

    # remove the stale desktop shortcut named Foxmail
    updater.remove_desktop_shortcut('Foxmail')

    updater.finish()

if __name__ == '__main__':
    update_app()
