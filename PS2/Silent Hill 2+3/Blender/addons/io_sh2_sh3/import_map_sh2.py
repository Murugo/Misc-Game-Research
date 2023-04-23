# pylint: disable-import-error

if "bpy" in locals():
  # pylint: disable=used-before-assignment
  import importlib
  if "readutil" in locals():
    importlib.reload(readutil)

import bpy
import math
import mathutils
import os

from .readutil import readutil
from . import vu


class MapImportError(Exception):
  pass


class MapParser:
  def __init__(self):
    self.basename = ''

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    f.skip(4)
    mesh_group_offsets = f.read_nuint32(2)
    matrix_offs = f.read_uint32()

    f.seek(matrix_offs)
    self.global_matrix = mathutils.Matrix([f.read_nfloat32(4) for _ in range(4)]).transposed()

    for i, offs in enumerate(mesh_group_offsets):
      if offs > 0:
        max_mesh_offs = mesh_group_offsets[i + 1] if i < len(mesh_group_offsets) - 1 else f.filesize
        self.parse_mesh_group(f, offs, max_mesh_offs)

  def parse_mesh_group(self, f, offs, max_mesh_offs):
    f.seek(offs + 0x10)
    self.parse_meshes(f, offs + 0x10, max_mesh_offs)
  
  def parse_meshes(self, f, offs, max_mesh_offs):
    index = 0
    while offs > 0 and offs < max_mesh_offs:
      print('Visiting: ', hex(offs))
      f.seek(offs)
      total_size, next_offs = f.read_nuint32(2)
      
      f.seek(offs + 0x60)
      vertex_count = f.read_uint32()
      
      f.seek(offs + 0xD0)

      vtx = []
      tri = []
      vn = []
      uv = []
      vcol = []
      reverse = False
      for i in range(vertex_count):
        # vtx.append([v / 0x8000 * 100.0 for v in f.read_nint16(3)])
        vtx_local = mathutils.Vector(f.read_nint16(3)).to_4d()
        vtx.append((self.global_matrix @ vtx_local).to_3d().to_tuple()[:3])
        # vtx.append(f.read_nint16(3))
        vn_vcol_x = f.read_int16()
        uv_flag = f.read_nint16(2)
        vn_vcol = (vn_vcol_x, *f.read_nint16(2))
        uv.append((uv_flag[0] / 0x8000, 1.0 - uv_flag[1] / 0x8000))
        vn.append(mathutils.Vector([(v & ~0x3F) / -0x8000 for v in vn_vcol]).normalized())
        vcol.append([(v & 0x3F) / 0x20 for v in vn_vcol])
        flag = uv_flag[0] & 0x1
        if not flag:
          if reverse:
            tri.append((i, i - 1, i - 2))
          else:
            tri.append((i - 2, i - 1, i))
        reverse = not reverse

      # Build Blender object at the shape level.
      offs_str = '{0:#010x}'.format(offs)
      objname = f'{self.basename}_'
      objname += f'{index}_{offs_str}'
      mesh_data = bpy.data.meshes.new(f'{objname}_mesh_data')
      mesh_data.from_pydata(vtx, [], tri)
      mesh_data.update()

      if uv:
        mesh_data.uv_layers.new(do_init=False)
        mesh_data.uv_layers[-1].data.foreach_set('uv', [
            vt for pair in [uv[loop.vertex_index] for loop in mesh_data.loops]
            for vt in pair
        ])

      obj = bpy.data.objects.new(objname, mesh_data)
      obj.rotation_euler = (-math.pi / 2, 0, math.pi)
      obj.scale = (0.1, 0.1, 0.1)

      # Normals should be set after creating the mesh object to prevent Blender from recalculating them.
      custom_vn = []
      for face in mesh_data.polygons:
        for vertex_index in face.vertices:
          custom_vn.append(vn[vertex_index])
        face.use_smooth = True
      mesh_data.use_auto_smooth = True
      mesh_data.normals_split_custom_set(custom_vn)

      bpy.context.scene.collection.objects.link(obj)
      obj.select_set(state=True)
      
      index += 1
      offs = next_offs


def load(context, filepath):
  try:
    parser = MapParser()
    parser.parse(filepath)
  except (MapImportError) as err:
    return 'CANCELLED', str(err)
  
  return 'FINISHED', ''
