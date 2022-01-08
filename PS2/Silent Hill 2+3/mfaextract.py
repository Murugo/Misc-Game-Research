# Extracts files from a Silent Hill 3 (PS2) MFA archive.

import argparse
import os
import sys
import struct

parser = argparse

parser = argparse.ArgumentParser(description='''
Script to extract files from a Silent Hill 3 (PS2) .MFA archive.
''')


def err(msg):
  print("Error: {}".format(msg))
  sys.exit(1)


def getint32(b, offs=0):
  return struct.unpack('<i', b[offs:offs+4])[0]


def getuint32(b, offs=0):
  return struct.unpack('<I', b[offs:offs+4])[0]


parser.add_argument('mfapath', help='Input path of .MFA or .MFA file', nargs=1)
args = parser.parse_args()

if len(args.mfapath[0]) == 0:
  parser.print_usage()
  sys.exit(1)
if not os.path.exists(args.mfapath[0]):
  err("MFA path not found: {}".format(args.mfapath[0]))
# Drag-and-drop hack
mfapath = sys.argv[1] if sys.argv[1][0] != '-' else args.mfapath[0]
basename = os.path.splitext(os.path.basename(mfapath))[0]

outdir = os.path.join(os.path.dirname(mfapath), basename)
if os.path.isfile(outdir):
  outdir += '_out'
if not os.path.exists(outdir):
  os.makedirs(outdir)

with open(mfapath, 'rb') as f:
  buf = f.read()

# First block in the MFA archive starts with a Python script used in Team Silent's toolchain?
offs = 0xB8 if buf[0x60] == 0x4E else 0xD8

block_index = -1
block_offs = 0
while offs < len(buf):
  block_index += 1
  num_files = getint32(buf, offs)
  if num_files < 0:
    err('Unexpected start of block, expected file count at {}'.format(hex(offs)))
  total_bytesize = getuint32(buf, offs + 0x4)

  print('\n{} files found in block at offset {}'.format(num_files, hex(block_offs)))

  for i in range(num_files):
    name_offs = getuint32(buf, offs + i * 0x10 + 0x8) + block_offs
    data_offs = getuint32(buf, offs + i * 0x10 + 0xC) + block_offs + 0x800
    # flags = getuint32(buf, offs + i * 0x10 + 0x10)
    data_size = getuint32(buf, offs + i * 0x10 + 0x14)

    name_end_offs = name_offs
    while buf[name_end_offs] != 0:
      name_end_offs += 1
    filename = buf[name_offs:name_end_offs].decode(
        encoding='ascii', errors='replace').strip()
    if len(filename) == 0:
      filename = "_unnamed_{}_{}.bin".format(i, block_index)

    print('Extracting: {} ...'.format(filename))
    outpath = os.path.join(outdir, filename)
    if not os.path.exists(os.path.dirname(outpath)):
      os.makedirs(os.path.dirname(outpath))
    with open(outpath, 'wb+') as f:
      f.write(buf[data_offs:data_offs + data_size])

  block_offs += total_bytesize + 0x800
  offs = block_offs + 0x8
