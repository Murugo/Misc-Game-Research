# pylint: disable-import-error

if "bpy" in locals():
  # pylint: disable=used-before-assignment
  import importlib
  if "readutil" in locals():
    importlib.reload(readutil)

import bpy
import mathutils
import os

from .readutil import readutil


class DdsImportError(Exception):
  pass


class DdsParser:
  def __init__(self, armature, target_character=''):
    self.basename = ''
    self.armature = armature

    self.target_character = target_character
    self.demo_status = 0
    self.base_pos = (0, 0, 0)

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
    return self.character_names

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)
    self.initialize(f)

    target_character_index = -1
    for i, name in enumerate(self.character_names):
      if name == self.target_character:
        target_character_index = i
    if target_character_index < 0:
      raise DdsImportError(f'Target object not found: {self.target_character}')

    character_keyframes = []
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
          self.parse_play_camera(f)
        elif ctrl - 2 < self.total_lights:
          self.parse_play_light(f)
        elif ctrl - self.total_lights - 2 < self.character_count:
          character_index = ctrl - self.total_lights - 2
          self.parse_play_character(
              f, frame_index, character_keyframes if character_index == target_character_index else None)
        else:
          raise DdsImportError(
              f'Unexpected control value {hex(ctrl)} at offset {f.tell() - 1}')

    print(character_keyframes[:10])

    bpy.context.view_layer.objects.active = self.armature
    bpy.ops.object.mode_set(mode='POSE', toggle=False)

    if not self.armature.animation_data:
      self.armature.animation_data_create()
    if not self.armature.animation_data.action:
      self.armature.animation_data.action = bpy.data.actions.new(
          f'{self.basename}_DDS')
    action = self.armature.animation_data.action

    fcurves = [
        action.fcurves.new(f'location', index=0),
        action.fcurves.new(f'location', index=1),
        action.fcurves.new(f'location', index=2)
    ]

    # armature_inverse_matrix = self.armature.matrix_local.inverted()
    for frame_index, pos in character_keyframes:
      pos_kf = (self.armature.matrix_local @
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

  def parse_play_camera(self, f):
    # NOTE: As of now the importer does not use camera data.
    while f.tell() < f.filesize:
      ctrl = f.read_uint8()
      if ctrl == 0xB:
        break
      if ctrl == 0x3 or ctrl == 0x4:
        if self.demo_status & 0x2 > 0:
          f.skip(12)
        else:
          f.skip(6)
      elif ctrl == 0x5:
        f.skip(6)
      elif ctrl == 0x6:
        f.skip(2)
      elif ctrl == 0x7:
        f.skip(4)
      else:
        raise DdsImportError(
            f'Unexpected camera control value {hex(ctrl)} at offset {f.tell() - 1}')

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

  def parse_play_character(self, f, frame_index, inout_character_keyframes=None):
    while f.tell() < f.filesize:
      ctrl = f.read_uint8()
      if ctrl == 0xB:
        break
      if ctrl == 0x3 or ctrl == 0x4:
        if self.demo_status & 0x2 > 0:
          pos = f.read_nfloat32(3)
          self.base_pos = pos
        else:
          pos = [v + self.base_pos[i]
                 for i, v in enumerate(f.read_nfloat16(3))]
        if inout_character_keyframes is not None:
          inout_character_keyframes.append((frame_index, pos))
      elif ctrl not in (0x1, 0x2):
        raise DdsImportError(
            f'Unexpected light control value {hex(ctrl)} at offset {f.tell() - 1}')
    pass


def get_selected_armature():
  armature = None

  for obj in bpy.context.selected_objects:
    if obj.type != 'ARMATURE':
      continue
    if armature:
      return None, 'More than one armature selected. Please select only the target armature before importing the DDS.'
    armature = obj

  if not armature:
    for obj in bpy.context.scene.objects:
      if obj.type != 'ARMATURE':
        continue
      if armature:
        return None, 'More than one armature found. Please select an armature before importing the DDS.'
      armature = obj

  if not armature:
    return None, 'No armatures found in the scene.'
  return armature, ''


def get_object_list(context, filepath):
  armature, error_reason = get_selected_armature()

  if error_reason:
    return [], error_reason

  parser = DdsParser(armature)
  return parser.get_character_names(filepath), ''


def load(context, filepath, target_character):
  armature, error_reason = get_selected_armature()

  if error_reason:
    return 'CANCELLED', error_reason

  parser = DdsParser(armature, target_character)
  parser.parse(filepath)

  return 'FINISHED', ''
