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


class PackExportError(Exception):
  pass


class PackPatcher:
  def __init__(self, object, target_type=-1, target_id=-1):
    self.basename = ''
    self.object = object

    self.target_type = target_type
    self.target_id = target_id
  
  def patch(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReadWriter(filepath)

    if f.read_uint32() != 0x12345678 or f.read_uint32() != 0x1:
      raise PackExportError('Not a SH3 .pack file')

    file_count = f.read_uint32()
    f.skip(4)
    file_headers = [f.read_nuint32(4) for _ in range(file_count)]
    for file_offs, file_type, file_size, _ in file_headers:
      if file_type != 0x2:
        continue
      if self.target_type == 0x1:
        self.patch_motion_track_file(f, file_offs)
      elif self.target_type == 0x3:
        self.patch_motion_track_file_for_camera(f, file_offs)
  
  def patch_motion_track_file(self, f, offs):
    f.seek(offs)
    track_count = f.read_uint32()

    tracks = []
    max_frame_count = 0
    for _ in range(track_count):
      track_type, index_and_id, frame_width, frame_count, _ = f.read_nuint32(5)
      tracks.append((track_type, index_and_id & 0xFFFF,
                    (index_and_id >> 16) & 0xFFFF, frame_width, frame_count))
      max_frame_count = max(max_frame_count, frame_count)
    
    bpy.context.view_layer.objects.active = self.object
    bpy.ops.object.mode_set(mode='POSE', toggle=False)
    wm = bpy.context.window_manager
    wm.progress_begin(0, max_frame_count)

    scene = bpy.context.scene
    frame_save = scene.frame_current
    pose_bones = self.object.pose.bones

    for frame_index in range(max_frame_count):
      wm.progress_update(frame_index)
      scene.frame_set(frame_index + 1)
      last_euler = [None for _ in range(len(pose_bones))]
      for track_type, track_index, track_id, frame_width, frame_count in tracks:
        if frame_index >= frame_count:
          continue
        if track_type != self.target_type or track_id != self.target_id:
          f.skip(frame_width)
          continue
        if track_index == 0:
          f.skip(frame_width)
          continue  # TODO: This may be the object's origin?
        bone_index = track_index - 1
        pose_bone = pose_bones[f'Bone_{bone_index}']
        mat = pose_bone.matrix
        pos, quat, _ = mat.decompose()
        # TODO: Any way to apply the scale of the object?
        pos = [v * 10.0 for v in pos]
        if last_euler[bone_index]:
          euler = quat.to_euler(euler_compat=last_euler[bone_index])
        else:
          euler = quat.to_euler()
        last_euler[bone_index] = euler
        f.write_nfloat32((*list(euler), *pos))

    wm.progress_end()
    scene.frame_set(frame_save)
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  def patch_motion_track_file_for_camera(self, f, offs):
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

    scene = bpy.context.scene
    camera_obj = self.object
    camera = camera_obj.data
    if 'CameraParent' not in scene.objects:
      raise PackExportError('Object "CameraParent" not found!')
    camera_parent_obj = scene.objects['CameraParent']
    if 'CameraTarget' not in scene.objects:
      raise PackExportError('Object "CameraTarget" not found!')
    camera_target_obj = scene.objects['CameraTarget']

    f.seek(offs)
    track_count = f.read_uint32()

    # TODO: Share code to construct this matrix. We take the inverse for export.
    m_scale = mathutils.Matrix()
    for i in range(3):
      m_scale[i][i] = 5
    # m_rot = mathutils.Euler((-math.pi / 2, 0, math.pi)).to_matrix().to_4x4()
    m_rot = mathutils.Euler((math.pi / 2, 0, math.pi)).to_matrix().to_4x4()
    m = (m_scale @ m_rot).inverted()

    tracks = []
    max_frame_count = 0
    for _ in range(track_count):
      track_type, index_and_id, frame_width, frame_count, _ = f.read_nuint32(5)
      tracks.append((track_type, index_and_id & 0xFFFF,
                    (index_and_id >> 16) & 0xFFFF, frame_width, frame_count))
      max_frame_count = max(max_frame_count, frame_count)
    
    bpy.context.view_layer.objects.active = self.object
    wm = bpy.context.window_manager
    wm.progress_begin(0, max_frame_count)
    frame_save = scene.frame_current

    for frame_index in range(max_frame_count):
      wm.progress_update(frame_index)
      scene.frame_set(frame_index + 1)
      for track_type, track_index, track_id, frame_width, frame_count in tracks:
        if frame_index >= frame_count:
          continue
        if track_type != self.target_type or track_id != self.target_id:
          f.skip(frame_width)
          continue
        
        camera_pos = (m @ camera_parent_obj.matrix_local).to_translation().to_3d()
        target_pos = (m @ camera_target_obj.matrix_local).to_translation().to_3d()
        tilt = math.degrees(camera_obj.rotation_euler[2])
        fov = math.degrees(2 * math.atan(camera.sensor_width * 0.3 / camera.lens))

        f.write_nfloat32((*list(camera_pos), *list(target_pos), tilt, fov))

    wm.progress_end()
    scene.frame_set(frame_save)
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

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


def patch(context, filepath, target_type=-1, target_id=-1):
  object, error_reason = get_selected_object()

  if error_reason:
    return 'CANCELLED', error_reason

  patcher = PackPatcher(object, target_type, target_id)
  patcher.patch(filepath)

  return 'FINISHED', ''
