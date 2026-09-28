import sys
import glob
import os
import datetime

sys.stdout.reconfigure(encoding='utf-8')

today = datetime.datetime.now().strftime('%Y%m%d')
print('Checking for signal files for ' + today + '...')

files = glob.glob('output/signals_' + today + '*.csv')
if files:
    print('Found ' + str(len(files)) + ' signal files:')
    for f in files:
        size = os.path.getsize(f) / 1024
        print('  - ' + os.path.basename(f) + ' (' + str(size) + ' KB)')
else:
    print('No signal files found for ' + today)
