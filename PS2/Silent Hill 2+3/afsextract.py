# Extracts files from a Silent Hill 3 (PS2) AFS archive.

import argparse
import os
import sys
import struct

parser = argparse

parser = argparse.ArgumentParser(description='''
Script to extract files from a Silent Hill 3 (PS2) .AFS archive.
''')


def err(msg):
  print("Error: {}".format(msg))
  sys.exit(1)


def getint32(b, offs=0):
  return struct.unpack('<i', b[offs:offs+4])[0]


def getuint32(b, offs=0):
  return struct.unpack('<I', b[offs:offs+4])[0]


def getstring(b, offs=0, maxsize=0x100):
  startoffs = offs
  maxoffs = startoffs + maxsize
  while offs < len(b) and offs < maxoffs and b[offs] != 0:
    offs += 1
  return b[startoffs:offs].decode('ascii')


parser.add_argument('afspath', help='Input path of .AFS file', nargs=1)
args = parser.parse_args()

if len(args.afspath[0]) == 0:
  parser.print_usage()
  sys.exit(1)
if not os.path.exists(args.afspath[0]):
  err("AFS path not found: {}".format(args.afspath[0]))
# Drag-and-drop hack
afspath = sys.argv[1] if sys.argv[1][0] != '-' else args.afspath[0]
basename = os.path.splitext(os.path.basename(afspath))[0]

outdir = os.path.join(os.path.dirname(afspath), f'{basename}_afs')
if os.path.isfile(outdir):
  outdir += '_out'
if not os.path.exists(outdir):
  os.makedirs(outdir)

with open(afspath, 'rb') as f:
  buf = f.read()

num_files = getuint32(buf, 0x4)

files = []
for i in range(num_files):
  offs = getuint32(buf, 0x8 + i * 0x8)
  size = getuint32(buf, 0xC + i * 0x8)
  files.append((offs, size))

filename_table_offs = getuint32(buf, 0x7FFF8)
filenames = []
for i in range(num_files):
  filename = getstring(buf, filename_table_offs + i * 0x30, 0x20)
  filenames.append(filename)

for (offs, size), filename in zip(files, filenames):
  print(f'Extracting: {filename} ...')
  outpath = os.path.join(outdir, filename)
  if not os.path.exists(os.path.dirname(outpath)):
    os.makedirs(os.path.dirname(outpath))
  with open(outpath, 'wb+') as f:
    f.write(buf[offs:offs + size])
