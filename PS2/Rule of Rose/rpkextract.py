# Extracts files from a Rule of Rose (PS2) RPK archive.

import argparse
import os
import sys
import struct

parser = argparse.ArgumentParser(description='''
Script to extract files from a Rule of Rose (PS2) RPK archive.
''')

def err(msg):
  print("Error: {}".format(msg))
  sys.exit(1)

def getuint16(b, offs = 0):
  return struct.unpack('<H', b[offs:offs+2])[0]

def getuint32(b, offs = 0):
  return struct.unpack('<I', b[offs:offs+4])[0]

parser.add_argument('rpkpath', help='Input path of .RPK or .BIN file', nargs=1)
parser.add_argument('-s', '--suffix', help='Suffix to add to each file', default='')
args = parser.parse_args()

if len(args.rpkpath[0]) == 0:
  parser.print_usage()
  sys.exit(1)
  
if not os.path.exists(args.rpkpath[0]):
  err("RPK path not found: {}".format(args.pacpath[0]))

rpkpath = sys.argv[1] if sys.argv[1][0] != '-' else args.pacpath[0]  # Drag-and-drop hack
basename = os.path.splitext(os.path.basename(rpkpath))[0]

outdir = os.path.join(os.path.dirname(rpkpath), basename)
if os.path.isfile(outdir):
    outdir += '_out'
if not os.path.exists(outdir):
    os.makedirs(outdir)

f = open(rpkpath, 'rb')
header = f.read(0x20)
if header[:4] != b'RTPK':
    err("Not an RTPK archive!")
totalsize = getuint32(header, 0x4)
numfiles = getuint16(header, 0xE)
nametable_size = getuint32(header, 0x10)
if numfiles == 0:
    err('No files in the RPK!')

file_sizes = []
file_offsets = []

if header[0xA] & 0x3 == 0x2:
    for _ in range(numfiles):
        file_offsets.append(getuint32(f.read(4)))
    for i in range(1, numfiles):
        file_sizes.append(file_offsets[i] - file_offsets[i - 1])
    file_sizes.append(totalsize- file_offsets[numfiles - 1])
elif header[0xA] & 0x3 == 0x3:
    for _ in range(numfiles):
        file_sizes.append(getuint32(f.read(4)))
    for _ in range(numfiles):
        file_offsets.append(getuint32(f.read(4)))
else:
    err('Unknown RPK format {}'.format(hex(header[0xA])))

if (header[0xA] & 0x10) > 0:
    # Unknown index table (0, 1, 2, 3...)?
    f.read(numfiles * 0x2)
file_names = []
if nametable_size > 0:
    nametable = f.read(nametable_size)
    start = 0
    for i in range(len(nametable)):
        if nametable[i] == 0:
            file_names.append(nametable[start:i].decode(encoding='ascii'))
            start = i + 1
else:
    file_names = ['unnamed_{}.bin'.format(i) for i in range(numfiles)]

for i in range(numfiles):
    print('Extracting: {} ({} bytes)'.format(file_names[i], file_sizes[i]))
    f.seek(file_offsets[i])
    filename = file_names[i] + args.suffix
    if filename[:3] == '../':
        filename = filename[3:]
    elif filename[:2] == './':
        filename = filename[2:]
    outpath = os.path.join(outdir, filename)
    if not os.path.exists(os.path.dirname(outpath)):
        os.makedirs(os.path.dirname(outpath))
    with open(os.path.join(outdir, filename), 'wb+') as fout:
        fout.write(f.read(file_sizes[i]))

print('Done.')
