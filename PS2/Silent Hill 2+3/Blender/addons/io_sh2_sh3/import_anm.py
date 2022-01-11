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

# Model ID -> (frame_size, alias, filename)
SH3_MODEL_ID_INFO = {
    0x100: (0x108, 'Heather', 'chhaa'),
    0x101: (0x0, 'Douglas', 'chdaa'),
    0x102: (0x2DE, 'Claudia', 'chcaa'),
    0x103: (0x1E0, 'Vincent', 'chvaa'),
    0x104: (0x1F6, 'Douglas', 'chdaa'),
    0x200: (0xBE, 'Double Head', 'en_one'),
    0x201: (0x68, 'Numb Body', 'en_ckn'),
    0x202: (0x90, 'Closer', 'en_aid'),
    0x203: (0xDC, 'Nurse', 'en_nse'),
    0x204: (0x96, 'Insane Cancer', 'en_deb'),
    0x205: (0x86, 'Pendulum', 'en_fly'),
    0x206: (0xD0, 'Scraper', 'en_ap2'),
    0x207: (0x74, '"Sewer Monster"', 'en_rod'),
    0x208: (0x22, '', 'en_ded1'),
    0x209: (0x2E, 'Carousel Horse', 'en_mry'),
    0x20A: (0x8A, 'Slurper', 'en_lie'),
    0x20B: (0x7A, 'Slurper', 'en_lix'),
    0x210: (0xF0, 'Split Worm', 'en_smb'),
    0x211: (0xD0, 'Missionary', 'en_apb'),
    0x212: (0x11C, 'Valtiel', 'en_spi'),
    0x213: (0xD0, 'Leonard', 'en_hpb'),
    0x214: (0x22E, 'God', 'en_shb'),
    0x215: (0x116, 'Memory of Alessa', 'en_bhr'),
    0x101C: (0x22, 'Freezer?', 'bg_fre'),
    0x101E: (0x8A, 'Hospital ladder room wall detail', 'bg_huo'),
    0x101F: (0x11C, 'Valtiel', 'bg_spi'),
    0x1020: (0x46, 'Curtains', 'bg_mes'),
    0x1024: (0x92, 'Subway', 'bg_sya'),
    0x1033: (0x16, 'Dagger', 'it_dagger'),  # TODO: Texture fails to import
    # TODO: ANM references a nonexistent third bone
    0x1038: (0x2E, '', 'bg_ded1'),
    0x103D: (0x80, 'Glutton', 'bg_zbb'),
    0x103E: (0x46, 'Slave', 'bg_slv'),
    0x1043: (0x34, 'Borley Haunted Mansion corpse', 'bg_ddd'),
    0x104E: (0x16, 'Radio', 'it_radio2'),
    0x104F: (0xA8, 'Alessa and Cheryl curtains', 'bg_lyc'),
}


class AnmImportError(Exception):
  pass


class AnmParserSh2:
  def __init__(self, armature):
    self.basename = ''
    self.armature = armature

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    # TODO: A better way to identify model IDs for SH2 animations?
    # frame_size = 0x210  # James
    # frame_size = 0x240  # Red Pyramid Thing
    frame_size = 0

    # TODO: Separate parsing and Blender related code into two functions
    bpy.context.view_layer.objects.active = self.armature
    bpy.ops.object.mode_set(mode='POSE', toggle=False)

    if not self.armature.animation_data:
      self.armature.animation_data_create()
    action = self.armature.animation_data.action = bpy.data.actions.new(
        f'{self.basename}_ANM')

    all_bone_fcurves = [[] for _ in range(len(self.armature.data.bones))]

    frame_index = 0
    bone_base_index = 0
    while f.tell() < f.filesize - 4:
      if bone_base_index > 0 and ((frame_size > 0 and (f.tell() % frame_size) == 0) or bone_base_index > len(self.armature.data.bones)):
        frame_index += 1
        bone_base_index = 0

        print(f'Frame start: {hex(f.tell())}')

      flags = f.read_uint32()

      if bone_base_index == 0 and (flags & 0xF) == 0 and flags > 0:
        print(f'Frame SKIP: {hex(f.tell())}')
        # Hack to re-align the start of the frame to the nearest word.
        # SH2 animation data is not always contiguous...
        # (Why is this not a concern in practice? Because the game stores
        # a table in the executable which points to the start of each clip
        # in the ANM.)
        flags = (flags >> 16) & 0xFFFF | (f.read_uint16() << 16)

      for ind in range(8):
        flag = (flags >> (ind << 2)) & 0x7
        if flag == 0:
          continue

        if flag not in (0x1, 0x2):
          raise AnmImportError(
              f'Unhandled flag value {hex(flag)} for data at offset {hex(f.tell())}')

        bone_index = bone_base_index + ind
        bone_name = f'Bone_{bone_index}'
        bone = self.armature.data.bones[bone_name]

        pos = None
        if flag & 0x2 > 0:
          if bone.parent is None:
            pos = f.read_nfloat32(3)
          else:
            pos = f.read_nfloat16(3)
        euler_xyz = [v / 0x1000 for v in f.read_nint16(3)]

        bone_matrix = bone.matrix_local
        if bone.parent:
          bone_matrix = bone.parent.matrix_local.inverted() @ bone_matrix
        self.armature.pose.bones[bone_name].rotation_mode = 'XYZ'

        rotation_matrix = mathutils.Euler(
            (euler_xyz[0], euler_xyz[1], euler_xyz[2])).to_matrix().to_4x4()
        translation_matrix = mathutils.Matrix()
        if pos:
          for j in range(3):
            translation_matrix[j][3] = pos[j]
        mat = bone_matrix.inverted() @ translation_matrix @ rotation_matrix

        kf_pos = (mat[0][3], mat[1][3], mat[2][3])
        kf_euler = mat.to_euler()

        if frame_index == 0:
          fcurves = [
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].rotation_euler', index=0),
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].rotation_euler', index=1),
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].rotation_euler', index=2),
          ]
          if pos:
            fcurves += [
                action.fcurves.new(
                    f'pose.bones["{bone_name}"].location', index=0),
                action.fcurves.new(
                    f'pose.bones["{bone_name}"].location', index=1),
                action.fcurves.new(
                    f'pose.bones["{bone_name}"].location', index=2)
            ]
          all_bone_fcurves[bone_index] = fcurves

        for j, fcurve in enumerate(all_bone_fcurves[bone_index]):
          if j >= 3 and not pos:
            continue
          fcurve.keyframe_points.add(1)
          if j < 3:
            fcurve.keyframe_points[-1].interpolation = 'LINEAR'
            fcurve.keyframe_points[-1].co = frame_index + 1, kf_euler[j]
          else:
            # TODO: How does SH2 handle sparse translation frames?
            fcurve.keyframe_points[-1].interpolation = 'CONSTANT'
            fcurve.keyframe_points[-1].co = frame_index + 1, kf_pos[j - 3]

      bone_base_index += 8

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)


class AnmParser:
  def __init__(self, armature):
    self.basename = ''
    self.armature = armature

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    model_id = f.read_uint32()
    print(f'* ANM {self.basename}: Model ID = {hex(model_id)}')
    if model_id not in SH3_MODEL_ID_INFO:
      raise AnmImportError(f'Unrecognized model ID: {hex(model_id)}')
    frame_size, _, _ = SH3_MODEL_ID_INFO[model_id]

    # TODO: Separate parsing and Blender related code into two functions
    bpy.context.view_layer.objects.active = self.armature
    bpy.ops.object.mode_set(mode='POSE', toggle=False)

    if not self.armature.animation_data:
      self.armature.animation_data_create()
    action = self.armature.animation_data.action = bpy.data.actions.new(
        f'{self.basename}_ANM')

    all_bone_fcurves = [[] for _ in range(len(self.armature.data.bones))]

    frame_index = 0
    bone_base_index = 0
    while f.tell() < f.filesize:
      # if frame_index >= 250:
      #   break
      if bone_base_index > 0 and ((f.tell() - 0x4) % frame_size) == 0:
        frame_index += 1
        bone_base_index = 0
        # break  # Just the first frame for now

      flags = f.read_uint32()
      for ind in range(8):
        flag = (flags >> (ind << 2)) & 0x7
        # print(
        #     f'Bone {bone_base_index + ind}: Flag {hex(flag)} Offs {hex(f.tell())}')
        if flag == 0:
          continue

        if flag not in (0x1, 0x2, 0x5, 0x6):
          raise AnmImportError(
              f'Unhandled flag value {hex(flag)} for data at offset {hex(f.tell())}')

        bone_index = bone_base_index + ind
        bone_name = f'Bone_{bone_index}'
        bone = self.armature.data.bones[bone_name]

        pos = None
        if flag & 0x2 > 0:
          if bone.parent is None:
            pos = f.read_nfloat32(3)
          else:
            pos = f.read_nfloat16(3)
        quat_xyz = [v / 0x8000 for v in f.read_nint16(3)]
        quat_x2 = quat_xyz[0] * quat_xyz[0]
        quat_y2 = quat_xyz[1] * quat_xyz[1]
        quat_z2 = quat_xyz[2] * quat_xyz[2]
        quat_w = math.sqrt(max(1.0 - quat_x2 - quat_y2 - quat_z2, 0.0))

        if flag & 0x4 > 0:
          quat_w *= -1.0

        bone_matrix = bone.matrix_local
        if bone.parent:
          bone_matrix = bone.parent.matrix_local.inverted() @ bone_matrix

        rotation_matrix = mathutils.Quaternion(
            (quat_w, quat_xyz[0], quat_xyz[1], quat_xyz[2]))
        rotation_matrix = rotation_matrix.to_matrix().to_4x4()
        translation_matrix = mathutils.Matrix()
        if pos:
          for j in range(3):
            translation_matrix[j][3] = pos[j]
        if pos:
          mat = bone_matrix.inverted() @ translation_matrix @ rotation_matrix
        else:
          mat = bone_matrix.inverted() @ rotation_matrix

        kf_pos = (mat[0][3], mat[1][3], mat[2][3])
        kf_quat = mat.to_quaternion()

        if frame_index == 0:
          fcurves = [
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].rotation_quaternion', index=0),
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].rotation_quaternion', index=1),
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].rotation_quaternion', index=2),
              action.fcurves.new(
                  f'pose.bones["{bone_name}"].rotation_quaternion', index=3)
          ]
          if pos:
            fcurves += [
                action.fcurves.new(
                    f'pose.bones["{bone_name}"].location', index=0),
                action.fcurves.new(
                    f'pose.bones["{bone_name}"].location', index=1),
                action.fcurves.new(
                    f'pose.bones["{bone_name}"].location', index=2)
            ]
          all_bone_fcurves[bone_index] = fcurves

        for j, fcurve in enumerate(all_bone_fcurves[bone_index]):
          fcurve.keyframe_points.add(1)
          fcurve.keyframe_points[-1].interpolation = 'LINEAR'
          if j < 4:
            fcurve.keyframe_points[-1].co = frame_index + 1, kf_quat[j]
          else:
            fcurve.keyframe_points[-1].co = frame_index + 1, kf_pos[j - 4]

      bone_base_index += 8

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)


def load(context, filepath, is_sh2=False):
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

  if is_sh2:
    parser = AnmParserSh2(armature)
    parser.parse(filepath)
  else:
    parser = AnmParser(armature)
    parser.parse(filepath)

  return 'FINISHED', ''
