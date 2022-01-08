import struct


class VuParseError(Exception):
  pass


_DEF_WORD = b'\0\0\0\0'


class VifParser:
  def __init__(self):
    self.vumem = [[_DEF_WORD for _ in range(4)]
                  for _ in range(0x400)]  # VU1 memory is 16KB
    self.vif_r = [_DEF_WORD for _ in range(4)]
    self.vif_c = [struct.pack('<f', 1.0) for _ in range(4)]
    self.cl = 1
    self.wl = 1
    self.mask = [0 for _ in range(16)]

  def parse(self, buf):
    offs = 0
    while offs < len(buf):
      imm, qwd, cmd = struct.unpack('<HBB', buf[offs:offs+4])
      cmd &= 0x7F
      offs += 4
      if cmd == 0b00000000:  # NOP
        continue
      elif cmd == 0b00000001:  # STCYCLE
        self.cl = imm & 0xFF
        self.wl = (imm >> 8) & 0xFF
      elif cmd == 0b00110000:  # STROW
        self.vif_r = self._getnpacked32(buf, offs, 4)
        offs += 0x10
      elif cmd == 0b00110001:  # STCOL
        self.vif_c = self._getnpacked32(buf, offs, 4)
        offs += 0x10
      elif cmd == 0b00100000:  # STMASK
        m = self._getpacked32(buf, offs)
        self.mask = [((m >> (i << 1)) & 0x3) for i in range(16)]
        offs += 4
      elif cmd >> 5 == 0b11:  # UNPACK
        addr = imm & 0x3FF
        vnvl = cmd & 0xF
        usn = (imm & 0x400) > 0
        m = (cmd & 0x10) > 0
        j = 0
        if vnvl == 0b0000:  # S-32
          width = 4
          for i in range(qwd):
            val = _DEF_WORD
            if self.cl >= self.wl or (i % self.wl) < self.cl:
              val = self._getpacked32(buf, width * j + offs)
              j += 1
            addroffs = self.cl * (i // self.wl) + (i %
                                                   self.wl) if self.cl >= self.wl else 0
            self.vumem[addr + addroffs] = [
                self._maybe_mask_value(val, 0, i, m),
                self._maybe_mask_value(val, 1, i, m),
                self._maybe_mask_value(val, 2, i, m),
                self._maybe_mask_value(val, 3, i, m),
            ]
        elif vnvl == 0b0100:  # V2-32
          width = 8
          for i in range(qwd):
            val = [_DEF_WORD, _DEF_WORD]
            if self.cl >= self.wl or (i % self.wl) < self.cl:
              val = self._getnpacked32(buf, width * j + offs, 2)
              j += 1
            addroffs = self.cl * (i // self.wl) + (i %
                                                   self.wl) if self.cl >= self.wl else 0
            self.vumem[addr + addroffs] = [
                self._maybe_mask_value(val[0], 0, i, m),
                self._maybe_mask_value(val[1], 1, i, m),
                self._maybe_mask_value(_DEF_WORD, 2, i, m),
                self._maybe_mask_value(_DEF_WORD, 3, i, m),
            ]
        elif vnvl == 0b0101:  # V2-16
          width = 4
          for i in range(qwd):
            val = [_DEF_WORD, _DEF_WORD]
            if self.cl >= self.wl or (i % self.wl) < self.cl:
              if usn:
                val = self._getnpackedu16(buf, width * j + offs, 2)
              else:
                val = self._getnpacked16(buf, width * j + offs, 2)
              j += 1
            addroffs = self.cl * (i // self.wl) + (i %
                                                   self.wl) if self.cl >= self.wl else 0
            self.vumem[addr + addroffs] = [
                self._maybe_mask_value(val[0], 0, i, m),
                self._maybe_mask_value(val[1], 1, i, m),
                self._maybe_mask_value(_DEF_WORD, 2, i, m),
                self._maybe_mask_value(_DEF_WORD, 3, i, m),
            ]
        elif vnvl == 0b1000:  # V3-32
          width = 12
          for i in range(qwd):
            val = [_DEF_WORD, _DEF_WORD, _DEF_WORD]
            if self.cl >= self.wl or (i % self.wl) < self.cl:
              val = self._getnpacked32(buf, width * j + offs, 3)
              j += 1
            addroffs = self.cl * (i // self.wl) + (i %
                                                   self.wl) if self.cl >= self.wl else 0
            self.vumem[addr + addroffs] = [
                self._maybe_mask_value(val[0], 0, i, m),
                self._maybe_mask_value(val[1], 1, i, m),
                self._maybe_mask_value(val[2], 2, i, m),
                self._maybe_mask_value(_DEF_WORD, 3, i, m),
            ]
        elif vnvl == 0b1001:  # V3-16
          width = 6
          for i in range(qwd):
            val = [_DEF_WORD, _DEF_WORD, _DEF_WORD]
            if self.cl >= self.wl or (i % self.wl) < self.cl:
              if usn:
                val = self._getnpackedu16(buf, width * j + offs, 3)
              else:
                val = self._getnpacked16(buf, width * j + offs, 3)
              j += 1
            addroffs = self.cl * (i // self.wl) + (i %
                                                   self.wl) if self.cl >= self.wl else 0
            self.vumem[addr + addroffs] = [
                self._maybe_mask_value(val[0], 0, i, m),
                self._maybe_mask_value(val[1], 1, i, m),
                self._maybe_mask_value(val[2], 2, i, m),
                self._maybe_mask_value(_DEF_WORD, 3, i, m),
            ]
        elif vnvl == 0b1100:  # V4-32
          width = 16
          for i in range(qwd):
            val = [_DEF_WORD, _DEF_WORD, _DEF_WORD, _DEF_WORD]
            if self.cl >= self.wl or (i % self.wl) < self.cl:
              val = self._getnpacked32(buf, width * j + offs, 4)
              j += 1
            addroffs = self.cl * (i // self.wl) + (i %
                                                   self.wl) if self.cl >= self.wl else 0
            self.vumem[addr + addroffs] = [
                self._maybe_mask_value(val[0], 0, i, m),
                self._maybe_mask_value(val[1], 1, i, m),
                self._maybe_mask_value(val[2], 2, i, m),
                self._maybe_mask_value(val[3], 3, i, m),
            ]
        elif vnvl == 0b1101:  # V4-16
          width = 8
          for i in range(qwd):
            val = [_DEF_WORD, _DEF_WORD, _DEF_WORD, _DEF_WORD]
            if self.cl >= self.wl or (i % self.wl) < self.cl:
              if usn:
                val = self._getnpackedu16(buf, width * j + offs, 4)
              else:
                val = self._getnpacked16(buf, width * j + offs, 4)
              j += 1
            addroffs = self.cl * (i // self.wl) + (i %
                                                   self.wl) if self.cl >= self.wl else 0
            self.vumem[addr + addroffs] = [
                self._maybe_mask_value(val[0], 0, i, m),
                self._maybe_mask_value(val[1], 1, i, m),
                self._maybe_mask_value(val[2], 2, i, m),
                self._maybe_mask_value(val[3], 3, i, m),
            ]
        else:
          raise VuParseError(
              f'Unsupported unpack vnvl {hex(vnvl)} at offset {hex(offs)}')
        offs += j * width
        if (offs % 4) > 0:
          offs += 4 - (offs % 4)
      else:
        raise VuParseError(
            f'Unrecognized vifcmd {hex(cmd)} at offset {hex(offs)}')

  def read_uint32(self, addr, elem):
    return struct.unpack('<I', self.vumem[addr][elem])[0]

  def read_int32_xyzw(self, addr):
    return [struct.unpack('<i', self.vumem[addr][i])[0] for i in range(4)]

  def read_uint32_xyzw(self, addr):
    return [struct.unpack('<I', self.vumem[addr][i])[0] for i in range(4)]

  def read_float32_xyzw(self, addr):
    return [struct.unpack('<f', self.vumem[addr][i])[0] for i in range(4)]

  def _getpacked32(self, b, offs):
    return b[offs:offs+4]

  def _getnpacked32(self, b, offs, n):
    return [b[offs+i*4:offs+i*4+4] for i in range(n)]

  def _getnpacked16(self, b, offs, n):
    values = struct.unpack('<' + 'h' * n, b[offs:offs+n*2])
    return [struct.pack('<i', v) for v in values]

  def _getnpackedu16(self, b, offs, n):
    values = struct.unpack('<' + 'H' * n, b[offs:offs+n*2])
    return [struct.pack('<i', v) for v in values]

  def _maybe_mask_value(self, val, index, cycle, use_mask):
    if not use_mask or self.mask[index] == 0b00:
      return val
    if self.mask[index + min(cycle, 3) * 4] == 0b01:
      return self.vif_r[index]
    if self.mask[index + min(cycle, 3) * 4] == 0b10:
      return self.vif_c[min(3, cycle)]
    return _DEF_WORD
