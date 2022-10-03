'''Utilities for parsing binary files.'''

import os
import struct


class BinaryFileReader:
  '''Binary file reader with methods for parsing primitives from bytes.'''
  def __init__(self, filepath: str):
    self.f = open(filepath, 'rb')
    self.filesize = os.path.getsize(filepath)
    self.base_offset = 0

  def seek(self, offs):
    self.f.seek(offs + self.base_offset)
    return self

  def tell(self):
    return self.f.tell()

  def set_base_offset(self, offs):
    self.base_offset = offs
    return self

  def read(self, size):
    return self.f.read(size)

  def read_int8(self):
    return struct.unpack('b', self.f.read(1))[0]

  def read_nint8(self, n):
    return struct.unpack('b' * n, self.f.read(n))

  def read_uint8(self):
    return ord(self.f.read(1))

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

  def read_uint64(self):
    return struct.unpack('<Q', self.f.read(8))[0]

  def read_nuint64(self, n):
    return struct.unpack('<' + 'Q' * n, self.f.read(n * 8))

  def read_float16(self):
    return struct.unpack('<e', self.f.read(2))[0]

  def read_nfloat16(self, n):
    return struct.unpack('<' + 'e' * n, self.f.read(n * 2))

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
    return self


class BinaryFileReadWriter(BinaryFileReader):
  '''Binary file writer with methods to write primitives.'''
  def __init__(self, filepath):
    super().__init__(filepath)

  def write_float32(self, val):
    self.f.write(struct.pack('<f', val))

  def write_nfloat32(self, vals):
    self.f.write(struct.pack('<' + 'f' * len(vals), *vals))
