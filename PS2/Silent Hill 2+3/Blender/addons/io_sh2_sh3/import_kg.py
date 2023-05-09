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
  def __init__(self, armature=None):
    self.armature = armature
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
    f.skip(0x18)
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

    for geometry_index in range(geometry_count):
      self.vtx = []
      self.tri = []
      self.reverse = False
      vertex_count, prim, _, qwd = f.read_nuint16(4)
      f.skip(0x8)  # Bounds
      next_offs = f.tell() + (qwd - 1) * 0x10
      if prim in (1, 2, 3, 4, 7, 10):
        # self.reverse = False
        f.skip(0x8)  # Face normal
        for _ in range(vertex_count):
          add_vertex(f.read_nint16(4), True)
        # Add n-gon indices manually
        indices = range(len(self.vtx) - vertex_count, len(self.vtx))
        if prim == 1:
          indices = reversed(indices)
        self.tri.append(list(indices))
      elif prim in (5, 6, 8, 9):
        self.reverse = prim == 5
        add_vertex(f.read_nint16(4), True)
        add_vertex(f.read_nint16(4), True)
        for _ in range(vertex_count - 2):
          f.skip(0x8)  # Face normal
          add_vertex(f.read_nint16(4), False)
      else:
        print(f'WARN: Unhandled primitive {prim} at offset {hex(f.tell() - 0xE)}')
      f.seek(next_offs)

      objname = f'{self.basename}_{object_index:02d}_{geometry_index:02d}_{prim}_{base_offs:#010x}'
      mesh_data = bpy.data.meshes.new(f'{objname}_mesh_data')
      mesh_data.from_pydata(self.vtx, [], self.tri)
      mesh_data.update()

      obj = bpy.data.objects.new(objname, mesh_data)
      if not self.armature:
        obj.rotation_euler = (-math.pi / 2, 0, math.pi)
        obj.scale = (0.1, 0.1, 0.1)
      
      vertex_group = obj.vertex_groups.new(name=f'Bone_{object_index}')
      for i in range(len(self.vtx)):
        vertex_group.add([i], 1.0, 'ADD')

      bpy.context.scene.collection.objects.link(obj)
      obj.select_set(state=True)

      if self.armature:
        obj.parent = self.armature
        modifier = obj.modifiers.new(type='ARMATURE', name='Armature')
        modifier.object = self.armature


def loadKg1(context, filepath):
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
    parser = KgParser(armature)
    parser.parse(filepath)
  except (KgImportError) as err:
    return 'CANCELLED', str(err)

  return 'FINISHED', ''


def loadKg2(context, filepath):
  try:
    parser = KgParser()
    parser.parse(filepath)
  except (KgImportError) as err:
    return 'CANCELLED', str(err)

  return 'FINISHED', ''
