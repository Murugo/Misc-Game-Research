''' Converts Gitaroo Man .IMX textures to .PNG '''

import sys
import struct
import os
import png

class BinaryFileReader:
  def __init__(self, filename):
    self.f = open(filename, 'rb')
    
  def getbyte(self):
    return struct.unpack('<B', self.f.read(1))[0]
     
  def getshort(self):
    return struct.unpack('<H', self.f.read(2))[0]
     
  def getint(self):
    return struct.unpack('<I', self.f.read(4))[0]
     
  def getfloat(self):
    return struct.unpack('<f', self.f.read(4))[0]
    
  def getsignedshort(self):
    return struct.unpack('<h', self.f.read(2))[0]
   
  def read(self, n):
    return self.f.read(n)
   
  def seek(self, n):
    self.f.seek(n)
  
  def skip(self, n):
    self.f.seek(n, 1)
    
  def close(self):
    self.f.close()

if len(sys.argv) < 2:
  print('Usage: python imgextract.py <IMX File>')
  
for filename in sys.argv[1:]:
  
  f = BinaryFileReader(filename)

  f.skip(20)
  width = f.getint()
  height = f.getint()
  type_a = f.getint()
  type_b = f.getint()

  type = -1
  if type_a == 0 and type_b == 0:
    type = 0  # 4-bit indexed RGBA 8888
  elif type_a == 1 and type_b == 1:
    type = 1  # 8-bit indexed RGBA 8888
  elif type_a == 3 and type_b == 2:
    type = 2  # 24-bit RGB 888
  elif type_a == 4 and type_b == 2:
    type = 3  # 32-bit RGBA 8888
  if type < 0:
    print('Unknown image format type:', type)
    sys.exit(0)

  clut = []
  if type < 2:
    clutsize = f.getint()
    for i in range(clutsize // 4):
      r = f.getbyte()
      g = f.getbyte()
      b = f.getbyte()
      a = f.getbyte() * 2
      if a > 255:
        a = 255
      clut.append([r, g, b, a])
    f.skip(4)
    
  image = []
  imagesize = f.getint()
  first = True
  for y in range(height):
    row = []
    
    if type == 0:
      for x in range(width // 2):
        # 4-bit indexed RGBA 8888
        index = f.getbyte()
        
        row.extend(clut[index & 0x0F])
        row.extend(clut[(index >> 4) & 0x0F])
    else:
      for x in range(width):
        if type == 1:
          # 8-bit indexed RGBA 8888
          index = f.getbyte()
          row.extend(clut[index])
          
        elif type == 2:
          # 24-bit RGB 888
          r = f.getbyte()
          g = f.getbyte()
          b = f.getbyte()
          row.extend([r, g, b, 255])
          
        elif type == 3:
          # 32-bit RGBA 8888
          r = f.getbyte()
          g = f.getbyte()
          b = f.getbyte()
          a = f.getbyte() * 2
          if a > 255:
            a = 255
          row.extend([r, g, b, a])
        
    image.append(row)

  outfilename = f'{filename}.png'
  with open(outfilename, 'wb+') as f:
    writer = png.Writer(width=width, height=height, greyscale=False, alpha=True)
    writer.write_packed(f, image)
