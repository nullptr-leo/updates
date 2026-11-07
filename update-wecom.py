import os
import re
import tempfile

import updater

def update_app():
    # proxy
    proxy = updater.test_proxy('default')

    # find out the utilities executable path
    wecom_dir = updater.find_install_dir('WXWork')

    # homepage
    homepgage = 'https://work.weixin.qq.com/#indexDownload'

    # download url
    remote_url = 'https://work.weixin.qq.com/wework_admin/commdownload?platform=win&from=wwindex'

    # query the remote version
    print('Querying...')
    try:
        redirected_url = updater.get_redirected_url(remote_url, proxy=proxy)
        remote_version = re.search(r'WeCom_([\d\.]*)\.exe', redirected_url).group(1)
    except Exception:
        updater.fail_and_exit()
    print('Remote version: %s' % remote_version)

    # query the local version
    local_version = updater.get_file_version(os.path.join(wecom_dir, 'WXWork.exe'))
    print('Local version: %s' % local_version)

    # check if update is needed
    if updater.is_latest(remote_version, local_version):
        updater.already_latest()

    # download package files
    print('Preparing...')

    with tempfile.TemporaryDirectory() as temp_dir:
        download_path = os.path.join(temp_dir, os.path.basename(redirected_url))
        updater.download(remote_url, download_path, proxy=proxy)

        # install
        updater.taskkill('WXWork.exe')
        updater.run_installer(download_path)

    updater.finish()

if __name__ == '__main__':
    update_app()
