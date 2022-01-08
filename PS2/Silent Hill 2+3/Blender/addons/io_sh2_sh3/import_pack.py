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


class PackImportError(Exception):
  pass


class PackParser:
  def __init__(self, armature, target_model_id=-1):
    self.basename = ''
    self.armature = armature

    self.target_model_id = target_model_id
    # TODO: Check before removing fallback logic.
    # if self.target_model_id < 0:
    #   bone_count = len(self.armature.data.bones)
    #   if bone_count == 73:
    #     self.target_model_id = 0x100  # chhaa (Heather)
    #   elif bone_count == 109:
    #     self.target_model_id = 0x102  # chcaa (Claudia)
    #   elif bone_count == 70:
    #     self.target_model_id = 0x103  # chvaa (Vincent)
    #   elif bone_count == 92:
    #     self.target_model_id = 0x101  # 104? chdaa (Douglas)

  def get_model_list(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    if f.read_uint32() != 0x12345678 or f.read_uint32() != 0x1:
      raise PackImportError('Not a SH3 .pack file')

    file_count = f.read_uint32()
    f.skip(4)
    file_headers = [f.read_nuint32(4) for _ in range(file_count)]
    for file_offs, file_type, file_size, _ in file_headers:
      if file_type == 0x2:
        return self.get_model_ids_from_track_file(f, file_offs)

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    if f.read_uint32() != 0x12345678 or f.read_uint32() != 0x1:
      raise PackImportError('Not a SH3 .pack file')

    file_count = f.read_uint32()
    f.skip(4)
    file_headers = [f.read_nuint32(4) for _ in range(file_count)]
    for file_offs, file_type, file_size, _ in file_headers:
      if file_type == 0x1:
        self.parse_morph_control_file(f, file_offs)
      elif file_type == 0x2:
        self.parse_motion_track_file(f, file_offs)

  def parse_morph_control_file(self, f, offs):
    f.seek(offs)
    model_id = f.read_uint32()
    if model_id != self.target_model_id:
      return
    f.skip(4)  # Zero?

    frame_set_count = f.read_uint32()
    frame_set_headers = [f.read_nuint32(4) for _ in range(frame_set_count)]
    morph_frames = dict()
    for start_frame, end_frame, data_size, data_offs in frame_set_headers:
      if data_size == 0:
        continue
      data_offs += offs
      f.seek(data_offs)
      if f.read_uint32() != 0x29843918:
        raise PackImportError(
            f'Unexpected morph data magic at offset {f.tell() - 4}')
      f.skip(4)  # Version?
      morph_count = f.read_uint32()
      total_frame_count = f.read_uint32()
      morph_offs_table = f.read_nuint32(morph_count)
      for morph_index, morph_offs in enumerate(morph_offs_table):
        if morph_index not in morph_frames:
          morph_frames[morph_index] = []
        f.seek(morph_offs + data_offs)
        frame_count = f.read_uint16()
        if frame_count == 0:
          continue
        for _ in range(frame_count):
          time, value = f.read_nuint16(2)
          morph_frames[morph_index].append(
              (time + start_frame, value / 4096.0))

    objects_with_shape_keys = [
        c for c in self.armature.children if c.data.shape_keys is not None]
    if not objects_with_shape_keys:
      print('WARNING: Morph target animation not applied due to missing Blender shape keys')

    for obj in objects_with_shape_keys:
      if not obj.data.shape_keys.animation_data:
        obj.data.shape_keys.animation_data_create()
    shape_key_action = objects_with_shape_keys[0].data.shape_keys.animation_data.action = bpy.data.actions.new(
        f'{self.basename}_ShapeKeys_PACK')
    for obj in objects_with_shape_keys[1:]:
      obj.data.shape_keys.animation_data.action = shape_key_action

    for morph_index, frames in morph_frames.items():
      fcurve = shape_key_action.fcurves.new(
          f'key_blocks["ShapeKey_{morph_index}"].value')
      fcurve.keyframe_points.add(len(frames))
      for i, (time, value) in enumerate(frames):
        fcurve.keyframe_points[i].interpolation = 'LINEAR'
        fcurve.keyframe_points[i].co = time + 1, value

  def get_model_ids_from_track_file(self, f, offs):
    f.seek(offs)
    track_count = f.read_uint32()

    model_ids = set()
    for _ in range(track_count):
      track_type, index_and_id, _, _, _ = f.read_nuint32(5)
      if track_type != 0x1:
        continue
      model_id = (index_and_id >> 16) & 0xFFFF
      model_ids.add(model_id)

    return sorted(list(model_ids))

  def parse_motion_track_file(self, f, offs):
    f.seek(offs)
    track_count = f.read_uint32()

    tracks = []
    max_frame_count = 0
    for _ in range(track_count):
      track_type, index_and_id, frame_width, frame_count, _ = f.read_nuint32(5)
      tracks.append((track_type, index_and_id & 0xFFFF,
                    (index_and_id >> 16) & 0xFFFF, frame_width, frame_count))
      max_frame_count = max(max_frame_count, frame_count)

     # TODO: Separate parsing and Blender related code into two functions
    bpy.context.view_layer.objects.active = self.armature
    bpy.ops.object.mode_set(mode='POSE', toggle=False)

    for pose_bone in self.armature.pose.bones:
      pose_bone.rotation_mode = 'XYZ'

    if not self.armature.animation_data:
      self.armature.animation_data_create()
    action = self.armature.animation_data.action = bpy.data.actions.new(
        f'{self.basename}_PACK')

    # TODO: Cache inverted bones to speed up import.
    # global_bone_matrices = dict()
    # inverse_global_bone_matrices = dict()
    # for bone in self.armature.data.bones:
    #   # if bone.parent:
    #   #   m = global_bone_matrices[bone.parent.name] @ bone.matrix_local
    #   # else:
    #   #   m = bone.matrix_local.copy()
    #   m = bone.matrix_local.copy()
    #   global_bone_matrices[bone.name] = m
    #   inverse_global_bone_matrices[bone.name] = m.inverted()

    all_bone_fcurves = dict()

    for frame_index in range(max_frame_count):
      pose_matrices = dict()

      for track_type, track_index, track_id, frame_width, frame_count in tracks:
        if frame_index >= frame_count:
          continue
        if track_id != self.target_model_id:
          f.skip(frame_width)
          continue
        euler_xyz = f.read_nfloat32(3)
        pos_xyz = f.read_nfloat32(3)

        if track_index == 0:
          continue  # TODO: This may be the object's origin?
        bone_index = track_index - 1
        bone_name = f'Bone_{bone_index}'
        bone = self.armature.data.bones[bone_name]

        rotation_euler = mathutils.Euler(euler_xyz)
        rotation_matrix = rotation_euler.to_matrix().to_4x4()
        translation_matrix = mathutils.Matrix.Translation(pos_xyz)
        pose_matrices[bone_name] = translation_matrix @ rotation_matrix
        if bone.parent:
          m_kf = (
              pose_matrices[bone.parent.name] @
              bone.parent.matrix_local.inverted() @ bone.matrix_local
          ).inverted() @ translation_matrix @ rotation_matrix
        else:
          m_kf = bone.matrix_local.inverted() @ translation_matrix @ rotation_matrix
        euler_kf_xyz = m_kf.to_euler()
        pos_kf_xyz = (m_kf[0][3], m_kf[1][3], m_kf[2][3])

        if frame_index == 0:
          fcurves = [
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].rotation_euler', index=0),
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].rotation_euler', index=1),
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].rotation_euler', index=2),
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].location', index=0),
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].location', index=1),
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].location', index=2)
          ]
          all_bone_fcurves[bone_name] = fcurves

        for j, fcurve in enumerate(all_bone_fcurves[bone_name]):
          fcurve.keyframe_points.add(1)
          fcurve.keyframe_points[-1].interpolation = 'LINEAR'
          if j < 3:
            fcurve.keyframe_points[-1].co = frame_index + 1, euler_kf_xyz[j]
          else:
            fcurve.keyframe_points[-1].co = frame_index + 1, pos_kf_xyz[j - 3]

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)


def get_selected_armature():
  armature = None

  for obj in bpy.context.selected_objects:
    if obj.type != 'ARMATURE':
      continue
    if armature:
      return None, 'More than one armature selected. Please select only the target armature before importing the PACK.'
    armature = obj

  if not armature:
    for obj in bpy.context.scene.objects:
      if obj.type != 'ARMATURE':
        continue
      if armature:
        return None, 'More than one armature found. Please select an armature before importing the PACK.'
      armature = obj

  if not armature:
    return None, 'No armatures found in the scene.'
  return armature, ''


def get_model_list(context, filepath):
  armature, error_reason = get_selected_armature()

  if error_reason:
    return [], error_reason

  parser = PackParser(armature)
  return parser.get_model_list(filepath), ''


def load(context, filepath, target_model_id=-1):
  armature, error_reason = get_selected_armature()

  if error_reason:
    return 'CANCELLED', error_reason

  parser = PackParser(armature, target_model_id)
  parser.parse(filepath)

  return 'FINISHED', ''
