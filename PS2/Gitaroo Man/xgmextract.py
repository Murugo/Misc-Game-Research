''' Extracts files from a Gitaroo Man XGM archive. '''

import sys
import struct
import os

if len(sys.argv) != 2:
  print('Usage: python xgmextract.py <XGM File>')
  sys.exit(0)
  
with open(sys.argv[1], 'rb') as f:
  def readstr(len):
    string = f.read(len)
    return string.rstrip(b'\0')
    
  def readint():
    return struct.unpack('<I', f.read(4))[0]
    
  def skip(len):
    f.seek(len, 1)

  texcount = readint()
  modelcount = readint()
  filecount = texcount + modelcount
  print(f'\nNumber of files: {filecount}')
    
  dirname = f'{sys.argv[1]}.out'
  if not os.path.exists(dirname):
    os.makedirs(dirname)
    
  for i in range(filecount):
    filepath = readstr(0x100)
    if not filepath:
      break
    
    filename = readstr(0x10).decode('ascii')
    print(f'Extracting: {filename}')
    skip(0x4)
    filesize = readint()
    
    if '.IMX' in filename:
      skip(0x18)
    else:
      animcount = readint()
      skip(animcount * 0x20 + 4)

    with open(os.path.join(dirname, filename), 'wb+') as fout:
      fout.write(f.read(filesize))
