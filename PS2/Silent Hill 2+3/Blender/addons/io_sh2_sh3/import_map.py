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


class MaterialManager:
  def __init__(self, basename):
    self.default_material = material = bpy.data.materials.new(
      name=f'{basename}_default'
    )
    material.use_nodes = True

    bsdf = material.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Specular'].default_value = 0


class MeshGroupInfo:
  def __init__(self, index):
    self.index = index


class MeshInfo:
  def __init__(self, index, flag, mesh_group_info):
    self.index = index
    self.flag = flag
    self.mesh_group_info = mesh_group_info


class SubmeshInfo:
  def __init__(self, index, mesh_info):
    self.index = index
    self.mesh_info = mesh_info


class MapParser:
  def __init__(self):
    self.basename = ''

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    self.mat_manager = MaterialManager(self.basename)

    f.seek(0xC)
    unk_offs = f.read_uint32()
    f.seek(0x1C)
    mesh_group_offsets = f.read_nuint32(3)

    f.seek(unk_offs + 0x20)
    self.global_matrix = mathutils.Matrix([f.read_nfloat32(4) for _ in range(4)]).transposed()

    for offs in sorted(mesh_group_offsets):
      if offs > 0:
        self.parse_mesh_groups(f, offs)
        break

  def parse_mesh_groups(self, f, offs):
    index = 0
    while offs > 0:
      f.seek(offs)
      next_offs, data_start_offs, total_size, _= f.read_nuint32(4)
      # image_source, _, image_index, mesh_count = f.read_nuint16(4)
      mesh_group_info = MeshGroupInfo(index)
      self.parse_meshes(f, offs + data_start_offs, mesh_group_info)
      index += 1
      offs = next_offs

  def parse_meshes(self, f, offs, mesh_group_info):
    index = 0
    while offs > 0:
      f.seek(offs)
      next_offs, data_start_offs, total_size, _ = f.read_nuint32(4)
      clut_index, _, _, flag = f.read_nuint16(4)
      mesh_info = MeshInfo(index, flag, mesh_group_info)
      self.parse_submeshes(f, offs + data_start_offs, mesh_info)
      index += 1
      offs = next_offs

  def parse_submeshes(self, f, offs, mesh_info):
    index = 0
    while offs > 0:
      f.seek(offs)
      next_offs, data_start_offs, total_size, _ = f.read_nuint32(4)
      submesh_info = SubmeshInfo(index, mesh_info)
      self.parse_shapes(f, offs + data_start_offs, submesh_info)
      index += 1
      offs = next_offs

  def parse_shapes(self, f, offs, submesh_info):
    index = 0
    while offs > 0:
      f.seek(offs)
      next_offs, data_start_offs, total_size, _ = f.read_nuint32(4)
      vertex_count, transform_index, _, _ = f.read_nuint32(4)
      
      f.seek(offs + data_start_offs)

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
      objname += f'{submesh_info.mesh_info.mesh_group_info.index}_'
      objname += f'{submesh_info.mesh_info.index}_'
      objname += f'{submesh_info.index}_'
      objname += f'{index}_{offs_str}_f{submesh_info.mesh_info.flag}'
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
      obj.data.materials.append(self.mat_manager.default_material)

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
