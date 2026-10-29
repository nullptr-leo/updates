import os
import re
import tempfile

import updater

def update_app():
    # proxy
    proxy = updater.test_proxy('default')

    # find out the utilities executable path
    python_dir = updater.find_install_dir('Python')

    # query the remote version
    print('Querying...')
    try:
        response = updater.query('https://www.python.org/downloads/', proxy=proxy)
        remote_version = re.search(r'python-(.*)-amd64.exe', response, flags=re.M | re.I).group(1)
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # query the local version
    local_version = updater.get_file_version(os.path.join(python_dir, 'python.exe'))
    print('Local version: %s' % local_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version, lexicographic=True):
        updater.already_latest()

    # download package files
    print('Preparing...')
    remote_url = 'https://www.python.org/ftp/python/' + remote_version + '/python-' + remote_version + '-amd64.exe'

    with tempfile.TemporaryDirectory() as temp_dir:
        download_path = os.path.join(temp_dir, remote_version + '.exe')
        updater.download(remote_url, download_path, proxy=proxy)

        # extract and update files
        updater.run_installer(download_path)

    updater.finish()

if __name__ == '__main__':
    update_app()
