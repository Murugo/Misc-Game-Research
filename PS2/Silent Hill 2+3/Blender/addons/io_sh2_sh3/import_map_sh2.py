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
  def __init__(self):
    self.mat_default = self.get_material('mat_default')
    self.mat_dict = {
      0: self.get_material('vukind_0_basic_fc_new2_s1p2'),
      2: self.get_material('vukind_2_Vu1_Spot_Blinn', (1.0, 0.0, 1.0, 1.0)),
      4: self.get_material('vukind_4_Vu1_S1P2phong', (1.0, 0.0, 0.0, 1.0)),
      8: self.get_material('vukind_8_Vu1_Constant', (0.0, 1.0, 0.0, 1.0)),
      9: self.get_material('Vu1_Spot_VCasLambert', (0.3, 0.3, 1.0, 1.0))
    }

  def get_material(self, name, color = (1.0, 1.0, 1.0, 1.0)):
    if name in bpy.data.materials:
      return bpy.data.materials[name]
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Specular'].default_value = 0
    bsdf.inputs['Base Color'].default_value = color
    return mat

class ObjectIdentifier:
  def __init__(self, group=''):
    self.group = group
    self.mesh_index = -1
    self.unkmesh_index = -1
    self.submesh_index = -1
    self.meshpart_index = -1
    self.vukind = 0
    self.offs = 0

  def __repr__(self):
    return f'{self.group}_M{self.mesh_index:02d}_U{self.unkmesh_index:02d}_S{self.submesh_index:02d}_P{self.meshpart_index:02d}_{self.offs:#010x}'


class MapParser:
  def __init__(self):
    self.basename = ''
    self.mat_manager = MaterialManager()

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
        max_offs = mesh_group_offsets[i + 1] if i < len(mesh_group_offsets) - 1 else f.filesize
        oid = ObjectIdentifier('T' if i == 0 else 'O')
        self.parse_mesh_group(f, offs, oid, max_offs)

  def parse_mesh_group(self, f, offs, oid, max_offs):
    self.parse_meshes(f, offs + 0x10, oid, max_offs)
  
  def parse_meshes(self, f, offs, oid, max_offs):
    oid.mesh_index = 0
    while offs > 0 and offs < max_offs:
      f.seek(offs + 0x4)
      next_offs = f.read_uint32()
      self.parse_unkmeshes(f, offs + 0x30, oid, next_offs if next_offs > 0 else max_offs)
      oid.mesh_index += 1
      offs = next_offs

  def parse_unkmeshes(self, f, offs, oid, max_offs):
    oid.unkmesh_index = 0
    while offs > 0 and offs < max_offs:
      f.seek(offs + 0x4)
      next_offs = f.read_uint32()
      self.parse_submeshes(f, offs + 0x10, oid)
      oid.unkmesh_index += 1
      offs = next_offs
  
  def parse_submeshes(self, f, offs, oid):
    oid.submesh_index = 0
    while offs > 0:
      f.seek(offs + 0x14)
      oid.vukind = f.read_uint8()
      f.skip(0x7)
      next_offs = f.read_uint32()
      self.parse_meshparts(f, offs + 0x20, oid)
      oid.submesh_index += 1
      offs = next_offs

  def parse_meshparts(self, f, offs, oid):
    oid.meshpart_index = 0
    while offs > 0:
      oid.offs = offs
      f.seek(offs)
      vertex_count = f.read_uint16()
      f.skip(0x6)
      next_offs = f.read_uint32()
      
      f.seek(offs + 0x70)

      vtx = []
      vtx_vec = []
      tri = []
      vn = []
      uv = []
      vcol = []
      reverse = False
      for i in range(vertex_count):
        # vtx.append([v / 0x8000 * 100.0 for v in f.read_nint16(3)])
        vtx_local = mathutils.Vector(f.read_nint16(3)).to_4d()
        vtx_vec.append((self.global_matrix @ vtx_local).to_3d())
        vtx.append(vtx_vec[-1].to_tuple()[:3])
        # vtx.append(f.read_nint16(3))
        vn_vcol_x = f.read_int16()
        uv_flag = f.read_nint16(2)
        vn_vcol = (vn_vcol_x, *f.read_nint16(2))
        uv.append((uv_flag[0] / 0x8000, 1.0 - uv_flag[1] / 0x8000))
        vn.append(mathutils.Vector([(v & ~0x3F) / -0x8000 for v in vn_vcol]).normalized())
        vcol.append([(v & 0x3F) / 0x20 for v in vn_vcol])
        flag = uv_flag[0] & 0x1
        if not flag:
          if (vtx_vec[-1] - vtx_vec[-2]).length > 1e-6 and (vtx_vec[-2] - vtx_vec[-3]).length > 1e-6:
            if reverse:
              tri.append((i, i - 1, i - 2))
            else:
              tri.append((i - 2, i - 1, i))
        reverse = not reverse

      # Build Blender object at the shape level.
      objname = f'{self.basename}_{oid}'
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

      if oid.vukind in self.mat_manager.mat_dict:
        obj.data.materials.append(self.mat_manager.mat_dict[oid.vukind])
      else:
        print(f'Found unknown vukind {oid.vukind}')
        obj.data.materials.append(self.mat_manager.mat_default)

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
      
      oid.meshpart_index += 1
      offs = next_offs


def load(context, filepath):
  try:
    parser = MapParser()
    parser.parse(filepath)
  except (MapImportError) as err:
    return 'CANCELLED', str(err)
  
  return 'FINISHED', ''
