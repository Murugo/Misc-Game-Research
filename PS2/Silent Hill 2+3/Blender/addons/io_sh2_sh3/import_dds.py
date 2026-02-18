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


class DdsImportError(Exception):
  pass


class CameraKeyframe:
  def __init__(self):
    self.pos = None
    self.target_pos = None
    self.unk5 = None
    self.unk6 = None
    self.unk7 = None


class DdsParser:
  def __init__(self, target_object, target_name=''):
    self.basename = ''
    self.target_object = target_object
    self.target_name = target_name
    self.target_camera = target_name == 'Camera'
    self.demo_status = 0
    self.camera_base_keyframe = None
    self.char_base_pos = {}

  def initialize(self, f):
    if f.read_uint32() != 0x736464:  # "dds\0":
      raise DdsImportError('Not a SH2 .dds file')

    f.skip(12)
    self.total_demo_frame = f.read_uint16()
    f.skip(2)  # unk
    point_light_count, spot_light_count, infinite_light_count = f.read_nuint8(
        3)
    self.total_lights = point_light_count + spot_light_count + infinite_light_count
    f.skip(1)
    self.character_count = f.read_uint8()
    self.character_names = [f.read_string(0x10)
                            for _ in range(self.character_count)]

  def get_character_names(self, filepath):
    f = readutil.BinaryFileReader(filepath)
    self.initialize(f)
    if self.target_object.type == 'CAMERA':
      return ['Camera']
    return self.character_names

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)
    self.initialize(f)

    target_character_index = -1
    if not self.target_camera:
      for i, name in enumerate(self.character_names):
        if name == self.target_name:
          target_character_index = i
      if target_character_index < 0:
        raise DdsImportError(f'Target object not found: {self.target_character}')

    character_keyframes = []
    camera_keyframes = []
    for _ in range(self.total_demo_frame):
      self.demo_status = 0
      frame_index = f.read_int16()
      if frame_index < 0:
        break
      while f.tell() < f.filesize:
        ctrl = f.read_int8()
        if ctrl < 0:
          break
        if ctrl == 0:
          self.parse_play_demo_status(f)
        elif ctrl == 1:
          self.parse_play_camera(f, frame_index, camera_keyframes)
        elif ctrl - 2 < self.total_lights:
          self.parse_play_light(f)
        elif ctrl - self.total_lights - 2 < self.character_count:
          character_index = ctrl - self.total_lights - 2
          self.parse_play_character(
              f, frame_index, character_index, character_keyframes if character_index == target_character_index else None)
        else:
          raise DdsImportError(
              f'Unexpected control value {hex(ctrl)} at offset {f.tell() - 1}')

    if self.target_camera:
      self.apply_camera_keyframes(camera_keyframes)
      return

    armature = self.target_object
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode='POSE', toggle=False)

    if not armature.animation_data:
      armature.animation_data_create()
    if not armature.animation_data.action:
      armature.animation_data.action = bpy.data.actions.new(
          f'{self.basename}_DDS')
    action = armature.animation_data.action

    fcurves = [
        action.fcurves.new(f'location', index=0),
        action.fcurves.new(f'location', index=1),
        action.fcurves.new(f'location', index=2)
    ]

    # armature_inverse_matrix = armature.matrix_local.inverted()
    for frame_index, pos in character_keyframes:
      pos_kf = (armature.matrix_local @
                mathutils.Matrix.Translation(pos)).translation
      pos_kf = (pos_kf[0], pos_kf[1], -pos_kf[2])
      for i, fcurve in enumerate(fcurves):
        fcurve.keyframe_points.add(1)
        fcurve.keyframe_points[-1].interpolation = 'LINEAR'
        fcurve.keyframe_points[-1].co = frame_index + 1, -pos_kf[i]

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  def parse_play_demo_status(self, f):
    while f.tell() < f.filesize:
      ctrl = f.read_uint8()
      if ctrl == 0xB:
        return
      if ctrl == 0x10:
        self.demo_status |= 0x3
      elif ctrl == 0x11:
        self.demo_status |= 0x4
      elif ctrl == 0x14:
        self.demo_status |= 0x10
      elif ctrl not in (0x12, 0x13):
        raise DdsImportError(
            f'Unexpected key control value {hex(ctrl)} at offset {f.tell() - 1}')

  def parse_play_camera(self, f, frame_index, inout_camera_keyframes=None):
    kf = CameraKeyframe()
    while f.tell() < f.filesize:
      ctrl = f.read_uint8()
      if ctrl == 0xB:
        break
      if ctrl == 0x3:
        if self.demo_status & 0x2 > 0:
          kf.pos = f.read_nfloat32(3)
          self.camera_base_keyframe = kf
        else:
          kf.pos = [v + self.camera_base_keyframe.pos[i]
                    for i, v in enumerate(f.read_nfloat16(3))]
      elif ctrl == 0x4:
        if self.demo_status & 0x2 > 0:
          kf.target_pos = f.read_nfloat32(3)
          self.camera_base_keyframe = kf
        else:
          kf.target_pos = [v + self.camera_base_keyframe.target_pos[i]
                           for i, v in enumerate(f.read_nfloat16(3))]
      elif ctrl == 0x5:
        kf.unk5 = f.read_nfloat16(3)
      elif ctrl == 0x6:
        kf.unk6 = f.read_float16()
      elif ctrl == 0x7:
        kf.unk7 = f.read_float32()
      else:
        raise DdsImportError(
            f'Unexpected camera control value {hex(ctrl)} at offset {f.tell() - 1}')
    
    if inout_camera_keyframes is not None:
      inout_camera_keyframes.append((frame_index, kf))

  def parse_play_light(self, f):
    # NOTE: As of now the importer does not use dynamic light data.
    while f.tell() < f.filesize:
      ctrl = f.read_uint8()
      if ctrl == 0xB:
        break
      if ctrl == 0x3 or ctrl == 0x4:
        if self.demo_status & 0x2 > 0:
          f.skip(12)
        else:
          f.skip(6)
      elif ctrl == 0x5 or ctrl == 0x8:
        f.skip(6)
      elif ctrl == 0x9 or ctrl == 0xA:
        f.skip(4)
      elif ctrl not in (0x1, 0x2):
        raise DdsImportError(
            f'Unexpected light control value {hex(ctrl)} at offset {f.tell() - 1}')

  def parse_play_character(self, f, frame_index, character_index, inout_character_keyframes=None):
    while f.tell() < f.filesize:
      ctrl = f.read_uint8()
      if ctrl == 0xB:
        break
      if ctrl == 0x3 or ctrl == 0x4:
        if self.demo_status & 0x2 > 0:
          pos = f.read_nfloat32(3)
          self.char_base_pos[character_index] = pos
        else:
          pos = [v + self.char_base_pos[character_index][i]
                 for i, v in enumerate(f.read_nfloat16(3))]
        if inout_character_keyframes is not None:
          inout_character_keyframes.append((frame_index, pos))
      elif ctrl not in (0x1, 0x2):
        raise DdsImportError(
            f'Unexpected character control value {hex(ctrl)} at offset {f.tell() - 1}')
    pass

  def apply_camera_keyframes(self, camera_keyframes):
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    
    camera_obj = self.target_object
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
    
    camera['Unk5_0'] = 0.0
    camera['Unk5_1'] = 0.0
    camera['Unk5_2'] = 0.0
    camera['Unk6'] = 0.0
    camera['Unk7'] = 0.0
    
    if not camera.animation_data:
      camera.animation_data_create()
    if not camera_obj.animation_data:
      camera_obj.animation_data_create()
    if not camera_parent_obj.animation_data:
      camera_parent_obj.animation_data_create()
    if not camera_target_obj.animation_data:
      camera_target_obj.animation_data_create()
    camera.animation_data.action = camera_data_action = bpy.data.actions.new(f'{self.basename}_DDS')
    camera_obj.animation_data.action = camera_action = bpy.data.actions.new(f'{self.basename}_DDS')
    camera_parent_obj.animation_data.action = camera_parent_action = bpy.data.actions.new(f'{self.basename}_DDS')
    camera_target_obj.animation_data.action = camera_target_action = bpy.data.actions.new(f'{self.basename}_DDS')

    pos_fcurves = [
        camera_parent_action.fcurves.new(f'location', index=0),
        camera_parent_action.fcurves.new(f'location', index=1),
        camera_parent_action.fcurves.new(f'location', index=2)
    ]
    target_pos_fcurves = [
      camera_target_action.fcurves.new(f'location', index=0),
      camera_target_action.fcurves.new(f'location', index=1),
      camera_target_action.fcurves.new(f'location', index=2)
    ]
    misc_fcurves = [
      camera_data_action.fcurves.new(f'["Unk5_0"]'),
      camera_data_action.fcurves.new(f'["Unk5_1"]'),
      camera_data_action.fcurves.new(f'["Unk5_2"]'),
      camera_data_action.fcurves.new(f'["Unk6"]'),
      camera_data_action.fcurves.new(f'["Unk7"]')
    ]

    m_scale = mathutils.Matrix()
    for i in range(3):
      m_scale[i][i] = 0.1
    m_rot = mathutils.Euler((-math.pi / 2, 0, math.pi)).to_matrix().to_4x4()
    m = m_scale @ m_rot

    # TODO: Proper handling for hold keyframes
    for frame_index, kf in camera_keyframes:
      if kf.pos:
        pos = m @ mathutils.Vector(kf.pos).to_4d()
        for i, fcurve in enumerate(pos_fcurves):
          fcurve.keyframe_points.add(1)
          fcurve.keyframe_points[-1].interpolation = 'CONSTANT'
          fcurve.keyframe_points[-1].co = frame_index + 1, -pos[i] if i < 2 else pos[i]
      
      if kf.target_pos:
        target_pos = m @ mathutils.Vector(kf.target_pos).to_4d()
        for i, fcurve in enumerate(target_pos_fcurves):
          fcurve.keyframe_points.add(1)
          fcurve.keyframe_points[-1].interpolation = 'CONSTANT'
          fcurve.keyframe_points[-1].co = frame_index + 1, -target_pos[i] if i < 2 else target_pos[i]
      
      if kf.unk5:
        for i, fcurve in enumerate(misc_fcurves[:3]):
          fcurve.keyframe_points.add(1)
          fcurve.keyframe_points[-1].interpolation = 'CONSTANT'
          fcurve.keyframe_points[-1].co = frame_index + 1, kf.unk5[i]
      
      if kf.unk6:
        misc_fcurves[3].keyframe_points.add(1)
        misc_fcurves[3].keyframe_points[-1].interpolation = 'CONSTANT'
        misc_fcurves[3].keyframe_points[-1].co = frame_index + 1, kf.unk6

      if kf.unk7:
        misc_fcurves[4].keyframe_points.add(1)
        misc_fcurves[4].keyframe_points[-1].interpolation = 'CONSTANT'
        misc_fcurves[4].keyframe_points[-1].co = frame_index + 1, kf.unk7


def get_selected_object():
  sel_object = None

  for obj in bpy.context.selected_objects:
    if sel_object:
      return None, 'More than one object selected. Please select only the target object before importing the DDS.'
    sel_object = obj

  if not sel_object:
    for obj in bpy.context.scene.objects:
      if obj.type != 'ARMATURE':
        continue
      if sel_object:
        return None, 'More than one object found. Please select an object before importing the DDS.'
      sel_object = obj

  if not sel_object:
    return None, 'No armatures found in the scene. If you are importing a camera track, please select the camera first.'
  return sel_object, ''


def get_object_list(context, filepath):
  target_object, error_reason = get_selected_object()

  if error_reason:
    return [], error_reason

  parser = DdsParser(target_object)
  return parser.get_character_names(filepath), ''


def load(context, filepath, target_name):
  target_object, error_reason = get_selected_object()

  if error_reason:
    return 'CANCELLED', error_reason

  parser = DdsParser(target_object, target_name)
  parser.parse(filepath)

  return 'FINISHED', ''
