# Extracts files from a Musashi: Samurai Legend (PS2) ISO

import argparse
import os
import math
import sys
import struct

# SLUS_209.83
TLD_OFFSET = 0x6BC1B380
TLD_FILE_COUNT = 0x15
TLD_NAME_TABLE_OFFSET = 0x6BCEE248

OUTPUT_DIR = 'extract-all'

parser = argparse.ArgumentParser(description='''
Script to extract files from an .ISO file for Musashi: Samurai Legend (PS2).
''')

class BinaryFileReader:
  def __init__(self, filepath):
    self.f = open(filepath, 'rb')
    self.filesize = os.path.getsize(filepath)
    self.base_offset = 0

  def seek(self, offs):
    self.f.seek(offs + self.base_offset)

  def tell(self):
    return self.f.tell()

  def set_base_offset(self, offs):
    self.base_offset = offs
  
  def read(self, n):
    return self.f.read(n)

  def read_nuint8(self, n):
    return list(self.f.read(n))

  def read_int16(self):
    return struct.unpack('<h', self.f.read(2))[0]

  def read_nint16(self, n):
    return struct.unpack('<' + 'h' * n, self.f.read(n * 2))

  def read_uint16(self):
    return struct.unpack('<H', self.f.read(2))[0]

  def read_nuint16(self, n):
    return struct.unpack('<' + 'H' * n, self.f.read(n * 2))

  def read_int32(self):
    return struct.unpack('<i', self.f.read(4))[0]

  def read_nint32(self, n):
    return struct.unpack('<' + 'i' * n, self.f.read(n * 4))

  def read_uint32(self):
    return struct.unpack('<I', self.f.read(4))[0]

  def read_nuint32(self, n):
    return struct.unpack('<' + 'I' * n, self.f.read(n * 4))

  def read_float32(self):
    return struct.unpack('<f', self.f.read(4))[0]

  def read_nfloat32(self, n):
    return struct.unpack('<' + 'f' * n, self.f.read(n * 4))

  # Reads max_len bytes and returns the first zero-terminated string.
  def read_string(self, max_len):
    buf = self.f.read(max_len)
    offs = 0
    while offs < len(buf) and buf[offs] != 0:
      offs += 1
    return buf[:offs].decode('ascii')

  def skip(self, length):
    self.f.read(length)
  

class DecompressStream:
  def decompress(self, srcbuf, decompressed_size):
    self.srcind_ = 0
    self.dstind_ = 0
    dstbuf = [0 for _ in range(decompressed_size)]
    for block in range(math.ceil(len(srcbuf) / 0x1000)):
      self.decompress_block_(block, srcbuf, dstbuf)
    return bytes(dstbuf)
  
  def decompress_block_(self, block, srcbuf, dstbuf):
    self.srcind_ = block * 0x1000
    dictbuf = [0 for _ in range(0x100)]
    dictind = 1
    self.b_ = 0
    self.bitsleft_ = 0
    while self.dstind_ < len(dstbuf):
      if self.get_next_bit_(srcbuf):
        b = self.get_bits_(srcbuf, 8)
        dictbuf[dictind] = b
        dictind = (dictind + 1) & 0xFF
        dstbuf[self.dstind_] = b
        self.dstind_ += 1
      else:
        dictoffs = self.get_bits_(srcbuf, 8)
        if dictoffs == 0:
          break
        count = self.get_bits_(srcbuf, 4) + 2
        for _ in range(count):
          b = dictbuf[dictoffs]
          dictbuf[dictind] = b
          dictoffs = (dictoffs + 1) & 0xFF
          dictind = (dictind + 1) & 0xFF
          dstbuf[self.dstind_] = b
          self.dstind_ += 1

  def get_next_bit_(self, srcbuf):
    # Slightly more optimized than get_bits_(srcbuf, 1)
    if self.bitsleft_ == 0:
      self.bitsleft_ = 8
      self.b_ = srcbuf[self.srcind_]
      self.srcind_ += 1
    r = self.b_ & (1 << (self.bitsleft_ - 1))
    self.bitsleft_ -= 1
    return r > 0

  def get_bits_(self, srcbuf, bits):
    # Assume that bits is always <= 8
    r = 0
    if self.bitsleft_ >= bits:
      r = (self.b_ & ((1 << self.bitsleft_) - 1)) >> (self.bitsleft_ - bits)
      self.bitsleft_ -= bits
    else:
      if self.bitsleft_ > 0:
        r = (self.b_ & ((1 << self.bitsleft_) - 1)) << (bits - self.bitsleft_)
      self.b_ = srcbuf[self.srcind_]
      self.srcind_ += 1
      bitsleft = 8 - (bits - self.bitsleft_)
      r |= (self.b_ >> bitsleft)
      self.bitsleft_ = bitsleft
    return r


def err(msg):
  print(f'Error: {msg}')
  sys.exit(1)


parser.add_argument('isopath', help='Input path of .ISO file', nargs=1)
args = parser.parse_args()

if len(args.isopath[0]) == 0:
  parser.print_usage()
  sys.exit(1)
  
if not os.path.exists(args.isopath[0]):
  err("ISO not found: {}".format(args.isopath[0]))

f = BinaryFileReader(args.isopath[0])
basedir = os.path.dirname(args.isopath[0])

f.seek(TLD_NAME_TABLE_OFFSET)
tld_names = [f.read_string(0x8) for _ in range(TLD_FILE_COUNT)]

f.seek(TLD_OFFSET)
tld_files = []
for i in range(TLD_FILE_COUNT):
  # Static name, file sector, last file sector, sector size
  _, _, sector, _, _, _, sector_size, _ = f.read_nuint32(8)
  tld_files.append((sector, sector_size))

extracted_count = 0
skipped_count = 0

for filename, (sector, sector_size) in zip(tld_names, tld_files):
  if filename[0] != 'G':
    # Raw file (movie)
    outdir = os.path.join(basedir, OUTPUT_DIR)
    outpath = os.path.join(outdir, filename)
    if os.path.exists(outpath):
      skipped_count += 1
      continue
    extracted_count += 1
    print(f'Extracting... {filename}')
    if not os.path.isdir(outdir):
      os.makedirs(outdir)
    with open(outpath, 'wb+') as fout:
      f.seek(sector * 0x800)
      fout.write(f.read(sector_size * 0x800))
    continue

  # Data group
  f.seek(sector * 0x800)
  group_entries = []
  while True:
    rsrc_id, g_sector_offs, g_sector_size, cdm_header_sector_size = f.read_nuint32(4)
    if g_sector_size == 0:
      break
    group_entries.append((rsrc_id, g_sector_offs))
  
  for rsrc_id, g_sector_offs in group_entries:
    f.seek((sector + g_sector_offs) * 0x800)

    cd_member_entries = []
    while True:
      cdm_name = f.read_string(0x10)
      if not cdm_name:
        break
      cdm_size_uncompressed = f.read_uint32()
      f.skip(0xC)
      cdm_sector_size, cdm_sector_offs, flags, _ = f.read_nuint32(4)
      cd_member_entries.append((cdm_name, cdm_sector_offs, cdm_sector_size, cdm_size_uncompressed, flags))
    
    for cdm_name, cdm_sector_offs, cdm_sector_size, cdm_size_uncompressed, flags in cd_member_entries:
      diskdir = f'{filename}\\{rsrc_id}'
      outdir = os.path.join(basedir, OUTPUT_DIR, diskdir)
      outpath = os.path.join(outdir, cdm_name)
      if os.path.exists(outpath):
        skipped_count += 1
        continue
      extracted_count += 1
      print(f'Extracting... {diskdir}\\{cdm_name}')
      if not os.path.isdir(outdir):
        os.makedirs(outdir)
      with open(outpath, 'wb+') as fout:
        f.seek((sector + g_sector_offs + cdm_sector_offs) * 0x800)
        buf = f.read(cdm_sector_size * 0x800)
        if flags > 0:
          decompress_stream = DecompressStream()
          fout.write(decompress_stream.decompress(buf, cdm_size_uncompressed))
        else:
          fout.write(buf)

if extracted_count > 0 or skipped_count > 0:
  if skipped_count == 0:
    print(f'Extracted a total of {extracted_count} files.')
  else:
    print(f'Extracted a total of {extracted_count} files and skipped {skipped_count} existing files.')
