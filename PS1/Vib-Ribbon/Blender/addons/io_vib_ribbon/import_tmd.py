# pylint: disable-import-error

# NOTE: This is NOT a fully functional TMD importer! Don't try this with other games!
# The importer supports only the small number of draw primitives used in Vib-Ribbon.

if "bpy" in locals():
  # pylint: disable=used-before-assignment
  import importlib
  if "readutil" in locals():
    importlib.reload(readutil)

import bpy
import os

from .readutil import readutil


class TmdImportError(Exception):
  pass


class ObjectEntry:
  def __init__(self, f: readutil.BinaryFileReader):
    self.vert_top = f.read_uint32()
    self.n_vert = f.read_uint32()
    self.normal_top = f.read_uint32()
    self.n_normal = f.read_uint32()
    self.primitive_top = f.read_uint32()
    self.n_primitive = f.read_uint32()
    self.scale = f.read_uint32()  # Unused


class TmdParser:
  def __init__(self):
    self.basename = ''
  
  def parse(self, filepath: str) -> None:
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    f.seek(0x8)
    object_count = f.read_uint32()
    objects = []
    for _ in range(object_count):
      objects.append(ObjectEntry(f))
    
    for i, obj in enumerate(objects):
      f.seek(obj.vert_top + 0xC)
      vtx = [[v / 0x800 for v in f.read_nint16(4)][:3] for _ in range(obj.n_vert)]

      ind = []
      f.seek(obj.primitive_top + 0xC)
      start_offs = f.tell()
      for _ in range(obj.n_primitive):
        olen, ilen, flag, mode = f.read_nuint8(4)
        if mode == 0x40:
          # Straight line
          r, g, b, mode_dup = f.read_nuint8(4)
          pair = f.read_nuint16(2)
          if pair[0] != pair[1]:
            ind.append(pair)
        elif mode == 0x21:
          # Flat triangle, no texture
          r, g, b, mode_dup = f.read_nuint8(4)
          ind.append(f.read_nuint16(3))
          f.skip(0x2)
        else:
          raise TmdImportError(f'Unrecognized primitive mode {hex(mode)} at offset {hex(f.tell() - 1)}')
      
      offs_str = '{0:#010x}'.format(start_offs)
      obj_name = f'{self.basename}_m_{i}_{offs_str}'
      mesh_data = bpy.data.meshes.new(obj_name + '_mesh_data')
      mesh_data.from_pydata(vtx, [], ind)
      mesh_data.update()

      obj = bpy.data.objects.new(obj_name, mesh_data)
      bpy.context.scene.collection.objects.link(obj)
      obj.select_set(state=True)


def load(context, filepath: str) -> 'tuple[str, str]':
  try:
    parser = TmdParser()
    parser.parse(filepath)
  except (TmdImportError) as err:
    return 'CANCELLED', str(err)

  return 'FINISHED', ''
