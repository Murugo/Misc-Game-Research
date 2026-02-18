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


class KgImportError(Exception):
  pass


class KgParser:
  def __init__(self, armature=None, split_by_geometry=False, world_scale=None):
    self.armature = armature
    self.split_by_geometry = split_by_geometry
    self.world_scale_xyz = (world_scale, world_scale, world_scale)
    self.basename = ''
    self.vtx = []
    self.tri = []
    self.reverse = False

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    f.skip(4)
    object_count = f.read_uint16()
    f.skip(0xA)
    for _ in range(object_count):
      self.parse_object(f)
  
  def parse_object(self, f):
    base_offs = f.tell()
    f.skip(0x4)
    object_index = f.read_uint16()
    geometry_count = f.read_uint16()
    f.skip(0x10)
    object_bounding_sphere = f.read_nint16(4)  # X, Y, Z, R
    if self.armature:
      if object_index > len(self.armature.data.bones):
        raise KgImportError(f'Object index out of range at {hex(f.tell() - 0x1C)}: {object_index}')
      transform = self.armature.data.bones[f'Bone_{object_index}'].matrix_local
      f.skip(0x40)
    else:
      transform = mathutils.Matrix([f.read_nfloat32(4) for _ in range(4)]).transposed()

    def add_vertex(xyzw, is_prim_start):
      i = len(self.vtx)
      vtx_local = mathutils.Vector(xyzw[:3]).to_4d()
      vtx_vec = (transform @ vtx_local).to_3d()
      self.vtx.append(vtx_vec.to_tuple()[:3])
      if not is_prim_start:
        if self.reverse:
          self.tri.append((i - 2, i - 1, i))
        else:
          self.tri.append((i, i - 1, i - 2))
      self.reverse = not self.reverse

    self.vtx = []
    self.tri = []
    self.vtx_norm_tmp = []
    for geometry_index in range(geometry_count):
      
      self.reverse = False
      vertex_count, prim, _, qwd = f.read_nuint16(4)
      bounding_sphere = f.read_nint16(4)  # X, Y, Z, R
      next_offs = f.tell() + (qwd - 1) * 0x10

      # Primitive handling
      if prim in (1, 2, 3, 4, 7, 10):
        normal = [v / 0x1000 for v in f.read_nint16(4)]
        # f.skip(0x8)  # Face normal
        for _ in range(vertex_count):
          add_vertex(f.read_nint16(4), True)
        # Add n-gon indices manually
        indices = range(len(self.vtx) - vertex_count, len(self.vtx))
        if prim == 4:
          indices = reversed(indices)
        self.tri.append(list(indices))

        # TMP: Visualize the single normal
        normal_vec = transform.inverted().transposed() @ mathutils.Vector(normal[:3] + [0.0,])
        vertex_center = mathutils.Vector((0.0, 0.0, 0.0, 0.0))
        for v in self.vtx[-vertex_count:]:
          vertex_center += mathutils.Vector(v + (1.0,))
        vertex_center /= vertex_count
        self.vtx_norm_tmp.append(vertex_center.to_tuple()[:3])
        self.vtx_norm_tmp.append((vertex_center + normal_vec * 3.0).to_tuple()[:3])

      elif prim in (5, 6, 8, 9):
        self.reverse = prim in (6, 9)
        add_vertex(f.read_nint16(4), True)
        add_vertex(f.read_nint16(4), True)
        for _ in range(vertex_count - 2):
          normal = [v / 0x1000 for v in f.read_nint16(4)]
          # f.skip(0x8)  # Face normal
          add_vertex(f.read_nint16(4), False)

          # TMP: Visualize the normals
          normal_vec = transform.inverted().transposed() @ mathutils.Vector(normal[:3] + [0.0,])
          vertex_center = (
            mathutils.Vector(self.vtx[-3] + (1.0,)) +
            mathutils.Vector(self.vtx[-2] + (1.0,)) +
            mathutils.Vector(self.vtx[-1] + (1.0,))
          ) / 3.0
          self.vtx_norm_tmp.append(vertex_center.to_tuple()[:3])
          self.vtx_norm_tmp.append((vertex_center + normal_vec * 3.0).to_tuple()[:3])

      else:
        print(f'WARN: Unhandled primitive {prim} at offset {hex(f.tell() - 0xE)}')
      f.seek(next_offs)

      # TMP: Visualize the normals
      # for i in range(len(self.vtx_norm_tmp) // 2):
      #   self.vtx.extend((self.vtx_norm_tmp[i*2:i*2+2]))
      #   self.tri.append((len(self.vtx) - 2, len(self.vtx) - 1))

      if self.split_by_geometry:
        objname = f'{self.basename}_kg_{object_index:02d}_{geometry_index:02d}_{prim}_{base_offs:#010x}'
        self.create_blender_object(object_index, self.vtx, self.tri, prim, objname)

        self.vtx = []
        self.tri = []
        self.vtx_norm_tmp = []
      
      # TMP: Visualize geometry bounding sphere
      # if bounding_sphere[3] > 0:
      #   bb_loc = (transform @ mathutils.Vector(bounding_sphere[:3] + (1.0,))).to_3d()
      #   bb_rad_vec = (transform @ mathutils.Vector((bounding_sphere[3], 0.0, 0.0, 0.0)))
      #   bb_name = f'{self.basename}_{object_index:02d}_{geometry_index:02d}_BOUNDS_{base_offs:#010x}'
      #   bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=8, location=bb_loc, radius=bb_rad_vec.length)
      #   bpy.context.object.name = bb_name
      #   bpy.context.object.parent = self.armature
      #   bpy.context.object.display_type = 'WIRE'
    
    if not self.split_by_geometry:
      objname = f'{self.basename}_kg_{object_index:02d}'
      self.create_blender_object(object_index, self.vtx, self.tri, prim, objname)
    
    # TMP: Visualize object bounding sphere
    if object_bounding_sphere[3] > 0:
      world_transform = mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X')
      world_transform = mathutils.Matrix.Rotation(math.radians(180), 4, 'Z') @ world_transform
      world_transform = mathutils.Matrix.Scale(0.1, 4) @ world_transform
      bb_loc = (world_transform @ transform @ mathutils.Vector(object_bounding_sphere[:3] + (1.0,))).to_3d()
      bb_rad_vec = (world_transform @ transform @ mathutils.Vector((object_bounding_sphere[3], 0.0, 0.0, 0.0)))
      bb_name = f'{self.basename}_{object_index:02d}_BOUNDS'
      bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=8, location=bb_loc, radius=bb_rad_vec.length)
      bpy.context.object.name = bb_name
      bpy.context.object.parent = self.armature
      bpy.context.object.display_type = 'WIRE'
        
  def create_blender_object(self, object_index, vtx, tri, prim, name):
    mesh_data = bpy.data.meshes.new(f'{name}_mesh_data')
    mesh_data.from_pydata(vtx, [], tri)
    mesh_data.update()

    obj = bpy.data.objects.new(name, mesh_data)
    if not self.armature:
      obj.rotation_euler = (-math.pi / 2, 0, math.pi)  # -Y Up
      if self.world_scale_xyz:
        obj.scale = self.world_scale_xyz
    obj['prim'] = prim
    
    vertex_group = obj.vertex_groups.new(name=f'Bone_{object_index}')
    for i, _ in enumerate(vtx):
      vertex_group.add([i], 1.0, 'ADD')

    bpy.context.scene.collection.objects.link(obj)
    obj.select_set(state=True)

    if self.armature:
      obj.parent = self.armature
      modifier = obj.modifiers.new(type='ARMATURE', name='Armature')
      modifier.object = self.armature


def loadKg1(context, filepath, split_by_geometry):
  armature = None
  for obj in bpy.context.selected_objects:
    if obj.type != 'ARMATURE':
      continue
    if armature:
      return 'CANCELLED', 'More than one armature selected. Please select only the target armature before importing the ANM.'
    armature = obj

  if not armature:
    for obj in bpy.context.scene.objects:
      if obj.type != 'ARMATURE':
        continue
      if armature:
        return 'CANCELLED', 'More than one armature found. Please select an armature before importing the ANM.'
      armature = obj

  if not armature:
    return 'CANCELLED', 'No armatures found in the scene.'
  
  try:
    parser = KgParser(armature, split_by_geometry)
    parser.parse(filepath, )
  except (KgImportError) as err:
    return 'CANCELLED', str(err)

  return 'FINISHED', ''


def loadKg2(context, filepath, split_by_geometry, world_scale):
  try:
    parser = KgParser(armature=None, split_by_geometry=split_by_geometry, world_scale=world_scale)
    parser.parse(filepath)
  except (KgImportError) as err:
    return 'CANCELLED', str(err)

  return 'FINISHED', ''
