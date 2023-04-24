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
  def __init__(self, object, target_type=-1, target_id=-1):
    self.basename = ''
    self.object = object

    self.target_type = target_type
    self.target_id = target_id

  def get_target_list(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    if f.read_uint32() != 0x12345678 or f.read_uint32() != 0x1:
      raise PackImportError('Not a SH3 .pack file')

    file_count = f.read_uint32()
    f.skip(4)
    file_headers = [f.read_nuint32(4) for _ in range(file_count)]
    for file_offs, file_type, file_size, _ in file_headers:
      if file_type == 0x2:
        return self.get_targets_from_track_file(f, file_offs)

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    if f.read_uint32() != 0x12345678 or f.read_uint32() != 0x1:
      raise PackImportError('Not a SH3 .pack file')

    file_count = f.read_uint32()
    f.skip(4)
    file_headers = [f.read_nuint32(4) for _ in range(file_count)]
    for file_offs, file_type, file_size, _ in file_headers:
      if file_type == 0x1 and self.target_type == 0x1:
        self.parse_morph_control_file(f, file_offs)
      elif file_type == 0x2:
        if self.target_type == 0x1:
          self.parse_motion_track_file(f, file_offs)
        elif self.target_type == 0x3:
          self.parse_motion_track_file_for_camera(f, file_offs)

  def parse_morph_control_file(self, f, offs):
    self.armature = self.object

    f.seek(offs)
    model_id = f.read_uint32()
    if model_id != self.target_id:
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
          morph_frames[morph_index].append((start_frame, 0.0, True))
          continue
        for _ in range(frame_count):
          time, value = f.read_nuint16(2)
          morph_frames[morph_index].append(
              (time + start_frame, value / 4096.0, False))

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
      for i, (time, value, is_constant) in enumerate(frames):
        fcurve.keyframe_points[i].interpolation = 'CONSTANT' if is_constant else 'LINEAR'
        fcurve.keyframe_points[i].co = time + 1, value

  def get_targets_from_track_file(self, f, offs):
    f.seek(offs)
    track_count = f.read_uint32()

    targets = set()
    for _ in range(track_count):
      track_type, index_and_id, _, _, _ = f.read_nuint32(5)
      if (track_type == 0x1 and self.object.type == 'ARMATURE') or (track_type == 0x3 and self.object.type == 'CAMERA'):
        track_id = (index_and_id >> 16) & 0xFFFF
        targets.add((track_type, track_id))

    return sorted(list(targets))

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
    wm = bpy.context.window_manager
    wm.progress_begin(0, max_frame_count)

    for pose_bone in self.armature.pose.bones:
      pose_bone.rotation_mode = 'XYZ'

    if not self.armature.animation_data:
      self.armature.animation_data_create()
    action = self.armature.animation_data.action = bpy.data.actions.new(
        f'{self.basename}_PACK_Char_{hex(self.target_id)}')

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
      wm.progress_update(frame_index)
      pose_matrices = dict()

      for track_type, track_index, track_id, frame_width, frame_count in tracks:
        if frame_index >= frame_count:
          continue
        if track_type != self.target_type or track_id != self.target_id:
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

    wm.progress_end()
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  def parse_motion_track_file_for_camera(self, f, offs):
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    
    camera_obj = self.object
    camera = camera_obj.data
    if 'CameraParent' in bpy.context.scene.objects:
      camera_parent_obj = bpy.context.scene.objects['CameraParent']
    else:
      camera_parent_obj = bpy.data.objects.new('CameraParent', None)
      camera_parent_obj.empty_display_type = 'PLAIN_AXES'
      camera_obj.parent = camera_parent_obj
      bpy.context.scene.collection.objects.link(camera_parent_obj)
    camera_obj.location = (0, 0, 0)
    camera_obj.rotation_euler = mathutils.Euler((0, 0, 0))
    if 'CameraTarget' in bpy.context.scene.objects:
      camera_target_obj = bpy.context.scene.objects['CameraTarget']
    else:
      camera_target_obj = bpy.data.objects.new('CameraTarget', None)
      camera_target_obj.empty_display_type = 'PLAIN_AXES'
      bpy.context.scene.collection.objects.link(camera_target_obj)

      track_to_constraint = camera_parent_obj.constraints.new(type='TRACK_TO')
      track_to_constraint.target = camera_target_obj
      track_to_constraint.track_axis = 'TRACK_NEGATIVE_Z'
      track_to_constraint.up_axis = 'UP_Y'
    
    camera['Unk0x18'] = 0.0
    
    if not camera.animation_data:
      camera.animation_data_create()
    if not camera_obj.animation_data:
      camera_obj.animation_data_create()
    if not camera_parent_obj.animation_data:
      camera_parent_obj.animation_data_create()
    if not camera_target_obj.animation_data:
      camera_target_obj.animation_data_create()
    camera.animation_data.action = camera_data_action = bpy.data.actions.new(f'{self.basename}_PACK')
    camera_obj.animation_data.action = camera_action = bpy.data.actions.new(f'{self.basename}_PACK')
    camera_parent_obj.animation_data.action = camera_parent_action = bpy.data.actions.new(f'{self.basename}_PACK')
    camera_target_obj.animation_data.action = camera_target_action = bpy.data.actions.new(f'{self.basename}_PACK')

    f.seek(offs)
    track_count = f.read_uint32()

    # TODO: This transformation should be reversed for export.
    m_scale = mathutils.Matrix()
    for i in range(3):
      m_scale[i][i] = 5
    # m_rot = mathutils.Euler((-math.pi / 2, 0, math.pi)).to_matrix().to_4x4()
    m_rot = mathutils.Euler((math.pi / 2, 0, math.pi)).to_matrix().to_4x4()
    m = m_scale @ m_rot

    tracks = []
    max_frame_count = 0
    for _ in range(track_count):
      track_type, index_and_id, frame_width, frame_count, _ = f.read_nuint32(5)
      tracks.append((track_type, index_and_id & 0xFFFF,
                    (index_and_id >> 16) & 0xFFFF, frame_width, frame_count))
      max_frame_count = max(max_frame_count, frame_count)
    
    fcurves = []
    for frame_index in range(max_frame_count):
      for track_type, track_index, track_id, frame_width, frame_count in tracks:
        if frame_index >= frame_count:
          continue
        if track_type != self.target_type or track_id != self.target_id:
          f.skip(frame_width)
          continue
        camera_xyz = mathutils.Vector(f.read_nfloat32(3)).to_4d()
        target_xyz = mathutils.Vector(f.read_nfloat32(3)).to_4d()
        tilt, fov = f.read_nfloat32(2)

        # Assumes that the default sensor width in camera settings is 36 mm.
        focal_length = camera.sensor_width * 0.3 / math.tan(math.radians(fov / 2.0))

        kf_camera_xyz = m @ camera_xyz
        kf_target_xyz = m @ target_xyz

        if frame_index == 0:
          fcurves = [
            camera_parent_action.fcurves.new(f'location', index=0),
            camera_parent_action.fcurves.new(f'location', index=1),
            camera_parent_action.fcurves.new(f'location', index=2),
            camera_target_action.fcurves.new(f'location', index=0),
            camera_target_action.fcurves.new(f'location', index=1),
            camera_target_action.fcurves.new(f'location', index=2),
            camera_action.fcurves.new(f'rotation_euler', index=2),
            camera_data_action.fcurves.new(f'lens')
          ]
        
        for i, fcurve in enumerate(fcurves):
          fcurve.keyframe_points.add(1)
          fcurve.keyframe_points[-1].interpolation = 'LINEAR'
          if i < 3:
            fcurve.keyframe_points[-1].co = frame_index + 1, kf_camera_xyz[i]
          elif i < 6:
            fcurve.keyframe_points[-1].co = frame_index + 1, kf_target_xyz[i - 3]
          elif i == 6:
            fcurve.keyframe_points[-1].co = frame_index + 1, math.radians(tilt)
          else:
            fcurve.keyframe_points[-1].co = frame_index + 1, focal_length


def get_selected_object():
  object = None

  for obj in bpy.context.selected_objects:
    if object:
      return None, 'More than one object selected. Please select only the target object before importing the PACK.'
    object = obj

  # If no objects are selected, look for an armature to apply the animation.
  if not object:
    for obj in bpy.context.scene.objects:
      if obj.type != 'ARMATURE':
        continue
      if object:
        return None, 'More than one object found. Please select an object before importing the PACK.'
      object = obj

  if not object:
    return None, 'No armatures found in the scene. If you are importing a camera track, please select the camera first.'
  return object, ''


def get_target_list(context, filepath):
  object, error_reason = get_selected_object()

  if error_reason:
    return [], error_reason

  parser = PackParser(object)
  return parser.get_target_list(filepath), ''


def load(context, filepath, target_type=-1, target_id=-1):
  object, error_reason = get_selected_object()

  if error_reason:
    return 'CANCELLED', error_reason

  parser = PackParser(object, target_type, target_id)
  parser.parse(filepath)

  return 'FINISHED', ''
