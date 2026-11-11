import json
import os
import tempfile

import updater

def update_app():
    # proxy
    proxy = updater.test_proxy('default')

    # find out the utilities executable path
    wps_dir = updater.find_install_dir(['WPS Office', r'Kingsoft\WPS Office'])

    # homepage
    homepage = 'https://www.wps.cn'

    # query the local version
    local_version = updater.get_file_version(os.path.join(wps_dir, 'ksolaunch.exe'))
    print('Local version: %s' % local_version)

    # query the remote version
    print('Querying...')
    try:
        response = updater.query(f'{homepage}/platformUrlsv2', proxy=proxy)
        products = json.loads(response)['productList']
        # the 64-bit package is the x64 URL (listed as 'WPS Office for beta')
        win64 = next(p for p in products if p['productOs'] == 1 and 'x64' in p['productButtonUrl'])
        remote_version = win64['productVcode']
        remote_url = win64['productButtonUrl']
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version):
        updater.already_latest()

    # download package files
    print('Preparing...')

    with tempfile.TemporaryDirectory() as temp_dir:
        download_path = os.path.join(temp_dir, os.path.basename(remote_url))
        updater.download(remote_url, download_path, proxy=proxy)

        # install
        updater.taskkill('ksolaunch.exe')
        updater.run_installer(download_path)

    updater.finish()

if __name__ == '__main__':
    update_app()
