import glob
import os
import re
import shutil
import tempfile

import updater

# proxy
proxy = None

# find out the utilities executable path
pdfshaper_path = updater.find_install_dir('PDFShaper')

# query the remote version
print('Querying...')
try:
    response = updater.query('https://www.ghxi.com/pdfshaper.html', proxy=proxy)
    remote_version = re.search(r'PDF Shaper v([\d\.]*)', response, flags=re.M).group(1)
except Exception:
    updater.fail_and_exit()
print('Remote version: %s' % remote_version)

# query the local version
local_version = updater.get_file_version(os.path.join(pdfshaper_path, 'PDFShaper.exe'))
print('Local version: %s' % local_version)

# check if update is needed
if updater.is_latest(remote_version, local_version):
    updater.already_latest()

# navigate to download the update
print('Preparing...')
updater.taskkill('PDFShaper.exe')
updater.open_url('https://www.ghxi.com/pdfshaper.html')
updater.open_explorer(pdfshaper_path)

updater.finish()
