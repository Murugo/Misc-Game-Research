# pylint: disable-import-error

if "bpy" in locals():
  # pylint: disable=used-before-assignment
  import importlib
  if "readutil" in locals():
    importlib.reload(readutil)

import bpy
import collections
import math
import mathutils
import os
import re

from . import readutil

Options = collections.namedtuple('Options', [])

CHANNEL_SCX = 0
CHANNEL_SCY = 1
CHANNEL_SCZ = 2
CHANNEL_RTX = 3
CHANNEL_RTY = 4
CHANNEL_RTZ = 5
CHANNEL_ETX = 6
CHANNEL_ETY = 7
CHANNEL_ETZ = 8

KF_TYPE_CONSTANT = 0
KF_TYPE_LINEAR = 1
KF_TYPE_HERMITE = 2


class MsetImportError(Exception):
  pass


class BoneTransform:
  def __init__(self, bone):
    if bone.parent:
      bone_parent_matrix_inv = bone.parent.matrix_local.copy()
      bone_parent_matrix_inv.invert()
      self.bone_matrix_local = bone_parent_matrix_inv @ bone.matrix_local
    else:
      self.bone_matrix_local = bone.matrix_local.copy()
    self.bone_matrix_inv = self.bone_matrix_local.copy()
    self.bone_matrix_inv.invert()
    self.pos, self.rot, self.scale = self.bone_matrix_local.decompose()
    rot_euler_property = bone.get('local_euler')  # Set by MDLX importer.
    if rot_euler_property:
      self.rot_euler = mathutils.Euler(rot_euler_property)
    else:
      self.rot_euler = self.rot.to_euler()


class Keyframe:
  def __init__(self, time, value, kf_type, slope_in, slope_out):
    self.time = time
    self.value = value
    self.type = kf_type
    self.slope_in = slope_in
    self.slope_out = slope_out

  def interpolate(self, other_keyframe, time):
    if self.type == KF_TYPE_CONSTANT:
      return self.value
    elif self.type == KF_TYPE_LINEAR:
      return self.value + (time - self.time) * (
          other_keyframe.value - self.value) / (other_keyframe.time - self.time)
    elif self.type == KF_TYPE_HERMITE:
      t = (time - self.time) / (other_keyframe.time - self.time)
      t2 = t * t
      t3 = t2 * t
      h00 = 2 * t3 - 3 * t2 + 1
      h01 = -2 * t3 + 3 * t2
      h10 = t3 - 2 * t2 + t
      h11 = t3 - t2
      p0 = h00 * self.value
      p1 = h01 * other_keyframe.value
      m0 = h10 * (other_keyframe.time - self.time) * self.slope_out
      m1 = h11 * (other_keyframe.time - self.time) * other_keyframe.slope_in
      return p0 + m0 + p1 + m1
    return 0.0


class Fcurve:
  def __init__(self):
    # Keyframes sorted by time.
    self.keyframes = []

  def set_keyframe(self,
                   time,
                   value,
                   kf_type=KF_TYPE_CONSTANT,
                   slope_in=0.0,
                   slope_out=0.0):
    if not self.keyframes:
      self.keyframes.append(Keyframe(time, value, kf_type, slope_in, slope_out))
      return
    last_keyframe = self.keyframes[-1]
    if abs(last_keyframe.time - time) < 1e-5:
      last_keyframe.value = value
      last_keyframe.type = kf_type
      last_keyframe.slope_in = slope_in
      last_keyframe.slope_out = slope_out
    elif last_keyframe.time < time:
      self.keyframes.append(Keyframe(time, value, kf_type, slope_in, slope_out))
    else:
      raise MsetImportError(
          f'Tried to set keyframe out of order: time = {time}, previous time = {last_keyframe.time}'
      )

  def get_value_at_time(self, time):
    if not self.keyframes:
      return 0.0

    # Perform a binary search for the specific keyframe at the given time.
    minpos = 0
    maxpos = len(self.keyframes) - 1
    iterations = 0
    while minpos < maxpos:
      iterations += 1
      if iterations >= 10000:
        raise MsetImportError(
            'get_value_at_time() exceeded maximum number of iterations!')
      midpos = (minpos + maxpos) // 2
      mid_keyframe = self.keyframes[midpos]
      if abs(mid_keyframe.time - time) < 1e-5:
        # Keyframe exists.
        return mid_keyframe.value
      elif time < mid_keyframe.time:
        maxpos = midpos - 1
      else:
        minpos = midpos + 1

    keyframe = self.keyframes[minpos]
    if abs(keyframe.time - time) < 1e-5:
      # Keyframe exists.
      return keyframe.value
    elif time < keyframe.time:
      if minpos == 0:
        # Constant value determined by first keyframe.
        return keyframe.value
      # Interpolate between this and the previous keyframe.
      return self.keyframes[minpos - 1].interpolate(keyframe, time)
    if minpos == len(self.keyframes) - 1:
      # Constant value determined by last keyframe.
      return keyframe.value
    # Interpolate between this and the next keyframe.
    return keyframe.interpolate(self.keyframes[minpos + 1], time)

  def get_max_time(self):
    return self.keyframes[-1].time


# Timeline class which holds ANB fcurves for a single bone.
class BoneTimeline:
  def __init__(self, bone_transform):
    self.bone_transform = bone_transform
    # Fcurves for each channel (0-2 = scale, 3-5 = rotation, 6-8 = position).
    self.fcurves = [Fcurve() for _ in range(9)]
    self.times = set()

    # Add default keyframe using the edit bone transform.
    self.fcurves[CHANNEL_SCX].set_keyframe(0.0, bone_transform.scale[0])
    self.fcurves[CHANNEL_SCY].set_keyframe(0.0, bone_transform.scale[0])
    self.fcurves[CHANNEL_SCZ].set_keyframe(0.0, bone_transform.scale[0])
    self.fcurves[CHANNEL_RTX].set_keyframe(0.0, bone_transform.rot_euler[0])
    self.fcurves[CHANNEL_RTY].set_keyframe(0.0, bone_transform.rot_euler[1])
    self.fcurves[CHANNEL_RTZ].set_keyframe(0.0, bone_transform.rot_euler[2])
    self.fcurves[CHANNEL_ETX].set_keyframe(0.0, bone_transform.pos[0])
    self.fcurves[CHANNEL_ETY].set_keyframe(0.0, bone_transform.pos[1])
    self.fcurves[CHANNEL_ETZ].set_keyframe(0.0, bone_transform.pos[2])

  def set_keyframe(self,
                   time,
                   value,
                   channel,
                   kf_type=KF_TYPE_CONSTANT,
                   slope_in=0.0,
                   slope_out=0.0):
    self.times.add(round(time, 6))
    return self.fcurves[channel].set_keyframe(time, value, kf_type, slope_in,
                                              slope_out)

  def get_value_at_time(self, time, channel):
    return self.fcurves[channel].get_value_at_time(time)

  def get_max_time(self):
    return max([fcurve.get_max_time() for fcurve in self.fcurves])

  def get_decomposed_transform_at_time(self,
                                       time,
                                       prev_euler=None,
                                       prev_scale=None,
                                       axis_flip=False):
    kf_scale = [
        self.fcurves[CHANNEL_SCX].get_value_at_time(time),
        self.fcurves[CHANNEL_SCY].get_value_at_time(time),
        self.fcurves[CHANNEL_SCZ].get_value_at_time(time)
    ]
    kf_rot_euler = [
        self.fcurves[CHANNEL_RTX].get_value_at_time(time),
        self.fcurves[CHANNEL_RTY].get_value_at_time(time),
        self.fcurves[CHANNEL_RTZ].get_value_at_time(time)
    ]
    kf_pos = [
        self.fcurves[CHANNEL_ETX].get_value_at_time(time),
        self.fcurves[CHANNEL_ETY].get_value_at_time(time),
        self.fcurves[CHANNEL_ETZ].get_value_at_time(time)
    ]

    rotation_matrix = mathutils.Euler(kf_rot_euler).to_matrix()
    rotation_matrix.resize_4x4()
    translation_matrix = mathutils.Matrix()
    for i in range(3):
      translation_matrix[i][3] = kf_pos[i]
    scale_matrix = mathutils.Matrix()
    for i in range(3):
      scale_matrix[i][i] = kf_scale[i]

    mat = self.bone_transform.bone_matrix_inv @ translation_matrix @ rotation_matrix @ scale_matrix

    scale = mat.to_scale()
    pos = [mat[0][3], mat[1][3], mat[2][3]]
    if prev_euler:
      # Avoid axis flips by providing the previous frame's rotation for smoother
      # interpolation.
      rot_euler = mat.to_euler('XYZ', prev_euler)
    else:
      rot_euler = mat.to_euler('XYZ')

    if (prev_scale and (scale[0] > 0) != (prev_scale[0] > 0) and
        (scale[1] > 0) != (prev_scale[1] > 0) and (scale[2] > 0) !=
        (prev_scale[2] > 0)):
      # Avoid axis flips caused by negated scale.
      axis_flip = not axis_flip

    if axis_flip:
      rot_euler = mathutils.Euler(
          [rot_euler[0], rot_euler[1] + math.pi, rot_euler[2]])
      rot_euler.make_compatible(prev_euler)

    return scale, rot_euler, pos, axis_flip


class MotionPrototype0RawHeader:
  def __init__(self, f, offs):
    self.model_bone_count = f.read_uint16()
    self.aux_bone_count = f.read_uint16() - self.model_bone_count
    self.frame_count = f.read_uint32()
    self.aux_bone_hrc_table_offs = offs + f.read_uint32()
    self.flag_table_offs = offs + f.read_uint32()
    self.time_index_count = f.read_uint32()
    self.static_pose_table_offs = offs + f.read_uint32()
    self.static_pose_count = f.read_uint32()
    self.position_info_offs = offs + f.read_uint32()
    self.direct_fcurve_table_offs = offs + f.read_uint32()
    self.direct_fcurve_count = f.read_uint32()
    self.indirect_fcurve_table_offs = offs + f.read_uint32()
    self.indirect_fcurve_count = f.read_uint32()
    self.fcurve_key_table_offs = offs + f.read_uint32()
    self.time_table_offs = offs + f.read_uint32()
    self.value_table_offs = offs + f.read_uint32()
    self.slope_table_offs = offs + f.read_uint32()
    self.constraint_table_offs = offs + f.read_uint32()
    self.constraint_count = f.read_uint32()
    # TODO: Support active constraint, limiters and expression trees.
    # TODO: Parse FPS field?


class MsetParser:
  def __init__(self, options, armature):
    self.options = options
    self.basename = ''
    self.armature = armature

    self.time_table = []
    self.value_table = []
    self.slope_table = []

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    index = 0
    for filetype, filename, fileoffset, filesize in self.get_bar_files(f):
      if filesize == 0:
        continue
      if filetype == 0x11 and filesize > 0:
        # Parse only the first ANB.
        if index == 0:
          self.parse_anb(f, fileoffset, filename)
        index += 1
      elif filetype == 0x9:
        # Parse only the first animation.
        self.parse_anim(f, fileoffset, filename)
        return

  def get_bar_files(self, f, offs=0):
    f.seek(offs)
    if f.read_uint32() != 0x1524142:  # BAR\x01
      raise MsetImportError('Expected BAR magic at offset 0x0')
    file_count = f.read_uint32()
    f.skip(0x8)
    files = []
    for _ in range(file_count):
      file_type, file_name, file_offs, file_size = (f.read_uint32(),
                                                    f.read_string(4),
                                                    f.read_uint32(),
                                                    f.read_uint32())
      files.append((file_type, file_name, offs + file_offs, file_size))
    return files

  def parse_anb(self, f, offs, name):
    for filetype, _, fileoffset, filesize in self.get_bar_files(f, offs):
      if filetype == 0x9 and filesize > 0:
        # Parse only the first animation.
        self.parse_anim(f, fileoffset, name)
        return

  def parse_anim(self, f, offs, anb_name):
    offs += 0x90
    f.seek(offs)
    motion_type = f.read_uint32()
    if motion_type != 0:  # PROTOTYPE_0
      raise MsetImportError(f'Motion type not supported: {motion_type}')
    ignore_scale = f.read_uint32() == 1
    f.skip(0x8)
    header = MotionPrototype0RawHeader(f, offs)

    model_bone_count, aux_bone_count = self.get_existing_bone_counts()

    if header.model_bone_count != model_bone_count:
      raise MsetImportError(
          f'FK bone count mismatch ({model_bone_count} model != {header.model_bone_count} anb). Did you import an animation for the wrong model?'
      )
    if aux_bone_count > 0 and header.aux_bone_count != aux_bone_count:
      # TODO: More sophisticated IK rig matching (tree similarity?).
      # Two animations may have the same number of IK helpers, but different
      # constraints applied, resulting in import artifacts.
      raise MsetImportError(
          f'IK bone count mismatch ({aux_bone_count} model != {header.aux_bone_count} anb). Please apply this animation to a fresh impored model.'
      )

    if aux_bone_count == 0 and header.aux_bone_count > 0 and header.aux_bone_hrc_table_offs > 0:
      self.create_aux_bones(f, header)

    bone_transforms = []
    bone_count = header.model_bone_count + header.aux_bone_count
    for i in range(bone_count):
      bone_transforms.append(
          BoneTransform(self.armature.data.bones[self.get_bone_name(i,
                                                                    header)]))

    self.parse_bone_constraints(f, header)
    # May add helper bones to the armature (Blender only).
    self.parse_bone_flags_and_ik(f, header)

    bone_timelines = [
        BoneTimeline(bone_transforms[i]) for i in range(bone_count)
    ]
    self.init_value_tables(f, header)
    self.parse_static_pose(f, header, bone_timelines)
    self.parse_fcurves(f, header.direct_fcurve_table_offs,
                       header.direct_fcurve_count, header, bone_timelines)
    self.parse_fcurves(f,
                       header.indirect_fcurve_table_offs,
                       header.indirect_fcurve_count,
                       header,
                       bone_timelines,
                       base_id=header.model_bone_count)
    self.apply_blender_fcurves(header, bone_timelines, anb_name, ignore_scale)

  def get_existing_bone_counts(self):
    model_bone_name_re = re.compile('^Bone_\d+$')
    aux_bone_name_re = re.compile('^Bone_\d+_Aux$')
    model_bone_count = 0
    aux_bone_count = 0
    for bone in self.armature.data.bones:
      if model_bone_name_re.match(bone.name):
        model_bone_count += 1
      elif aux_bone_name_re.match(bone.name):
        aux_bone_count += 1
    return model_bone_count, aux_bone_count

  def create_aux_bones(self, f, header):
    bpy.context.view_layer.objects.active = self.armature
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)

    f.seek(header.aux_bone_hrc_table_offs)
    for _ in range(header.aux_bone_count):
      # Skip sibling index, child index
      index, _, parent_index, _ = f.read_nint16(4)
      f.skip(8)  # Skip reserved, flag
      scale = f.read_nfloat32(4)[:3]
      rotation = f.read_nfloat32(4)[:3]
      position = f.read_nfloat32(4)

      local_euler = mathutils.Euler(rotation)
      mat_rotation = local_euler.to_matrix()
      mat_rotation.resize_4x4()
      mat_scale = mathutils.Matrix()
      mat_scale[0][0] = scale[0]
      mat_scale[1][1] = scale[1]
      mat_scale[2][2] = scale[2]
      mat_position = mathutils.Matrix()
      mat_position[0][3] = position[0]
      mat_position[1][3] = position[1]
      mat_position[2][3] = position[2]
      local_matrix = mat_position @ mat_rotation @ mat_scale
      if parent_index >= 0:
        global_matrix = self.armature.data.edit_bones[
            parent_index].matrix @ local_matrix
      else:
        global_matrix = local_matrix

      bone = self.armature.data.edit_bones.new(f'Bone_{index}_Aux')
      bone.tail = (5, 0, 0)
      bone.use_inherit_rotation = True
      bone.use_local_location = True
      bone.matrix = global_matrix
      if parent_index >= 0:
        bone.parent = self.armature.data.edit_bones[parent_index]
      # Store a custom property that preserves the original Euler angles.
      # The importer will apply keyframes on top of these angles.
      bone['local_euler'] = local_euler

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  def parse_bone_constraints(self, f, header):
    bpy.context.view_layer.objects.active = self.armature
    bpy.ops.object.mode_set(mode='POSE', toggle=False)

    f.seek(header.constraint_table_offs)
    for _ in range(header.constraint_count):
      link_type, _ = f.read_nuint8(2)  # Skip temp active flag
      passive_index, active_index, _ = f.read_nuint16(3)  # Skip active_index_2
      f.skip(4)  # TODO: activation base, activation count

      passive_bone_name = self.get_bone_name(passive_index, header)
      active_bone_name = self.get_bone_name(active_index, header)
      passive_pose_bone = self.armature.pose.bones[passive_bone_name]

      if link_type == 0x0:  # POSITION
        if 'POSITION' in passive_pose_bone.constraints:
          continue
        constraint = passive_pose_bone.constraints.new('COPY_LOCATION')
        constraint.name = 'POSITION'
        constraint.target = self.armature
        constraint.subtarget = active_bone_name

      elif link_type == 0x2:  # ROTATION
        if 'ROTATION' in passive_pose_bone.constraints:
          continue
        constraint = passive_pose_bone.constraints.new('COPY_ROTATION')
        constraint.name = 'ROTATION'
        constraint.target = self.armature
        constraint.subtarget = active_bone_name

      elif link_type == 0x3:  # DIR
        # TODO: Not game-accurate, but TRACK_X may be correct in the least.
        if 'DIR' in passive_pose_bone.constraints:
          continue
        constraint = passive_pose_bone.constraints.new('LOCKED_TRACK')
        constraint.name = 'DIR'
        constraint.target = self.armature
        constraint.subtarget = active_bone_name
        constraint.track_axis = 'TRACK_X'
        constraint.lock_axis = 'LOCK_Y'

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  def parse_bone_flags_and_ik(self, f, header):
    class BoneFlags:
      def __init__(self, flags):
        self.ik_type = flags & 0x3
        self.trans = (flags & 0x4) > 0
        self.rotation = (flags & 0x8) > 0
        self.fixed = (flags & 0x10) > 0
        self.calculated = (flags & 0x20) > 0
        self.calc_matrix_2_rot = (flags & 0x40) > 0
        self.ext_effector = (flags & 0x80) > 0

    bone_flags = [0] * (header.model_bone_count + header.aux_bone_count)
    f.seek(header.flag_table_offs)
    for _ in range(header.model_bone_count + header.aux_bone_count):
      index, flags = f.read_nuint16(2)
      bone_flags[index] = BoneFlags(flags)

    # Set up IK chains based on flags.
    for bone_index, flags in enumerate(bone_flags):
      if flags.ik_type == 0:
        continue
      elif flags.ik_type == 0x1:
        # IK chain with length 1.
        bpy.context.view_layer.objects.active = self.armature
        bpy.ops.object.mode_set(mode='POSE', toggle=False)

        root_bone_name = self.get_bone_name(bone_index, header)
        effector_bone_name = self.get_bone_name(bone_index + 1, header)
        if 'POSITION' not in self.armature.pose.bones[
            effector_bone_name].constraints:
          print(
              f'WARNING: Expected "POSITION" constraint on bone {effector_bone_name} for IK chain starting at {root_bone_name}'
          )
          bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
          continue
        if 'IK' in self.armature.pose.bones[root_bone_name].constraints:
          bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
          continue

        bpy.ops.object.mode_set(mode='EDIT', toggle=False)

        root_edit_bone = self.armature.data.edit_bones[root_bone_name]
        effector_edit_bone = self.armature.data.edit_bones[effector_bone_name]
        # Connect the root bone to its effector to get the IK constraint to
        # work. Fudging the matrix of the root bone is okay because Blender's
        # IK solver will calculate it.
        root_edit_bone.tail = effector_edit_bone.head

        bpy.ops.object.mode_set(mode='POSE', toggle=False)

        root_pose_bone = self.armature.pose.bones[root_bone_name]
        effector_pose_bone = self.armature.pose.bones[effector_bone_name]
        # TODO: Consider removing the copy location constraint afterward to
        # prevent stretching?
        copy_location_constraint = effector_pose_bone.constraints['POSITION']
        ik_constraint = root_pose_bone.constraints.new('IK')
        ik_constraint.chain_count = 1
        ik_constraint.target = copy_location_constraint.target
        ik_constraint.subtarget = copy_location_constraint.subtarget
        ik_constraint.use_tail = True

        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

      elif flags.ik_type & 0x2:
        # IK chain with length 2.
        bpy.context.view_layer.objects.active = self.armature
        bpy.ops.object.mode_set(mode='POSE', toggle=False)
        is_leg_ik = flags.ik_type == 0x2

        root_parent_bone_name = self.get_bone_name(bone_index - 1, header)
        root_bone_name = self.get_bone_name(bone_index, header)
        mid_bone_name = self.get_bone_name(bone_index + 1, header)
        effector_bone_name = self.get_bone_name(bone_index + 2, header)
        if 'POSITION' not in self.armature.pose.bones[
            effector_bone_name].constraints:
          print(
              f'WARNING: Expected "POSITION" constraint on bone {effector_bone_name} for IK chain starting at {root_bone_name}'
          )
          bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
          continue
        if 'IK' in self.armature.pose.bones[mid_bone_name].constraints:
          bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
          continue

        bpy.ops.object.mode_set(mode='EDIT', toggle=False)

        mid_edit_bone = self.armature.data.edit_bones[mid_bone_name]
        effector_edit_bone = self.armature.data.edit_bones[effector_bone_name]
        # Connect the mid bone to its effector to get the Blender IK constraint
        # to work. Fudging the matrix of the mid bone is okay because Blender's
        # IK solver will calculate it.
        #
        # TODO: This breaks Goofy's IK rig due to a rotation constraint applied
        # on the model's elbow joint to copy the elbow IK helper. One solution
        # in this case (not great) is to also modify the model elbow joint to
        # match the new transform of the IK helper.
        mid_edit_bone.tail = effector_edit_bone.head

        # Create a new bone for the pole target.
        root_parent_edit_bone = self.armature.data.edit_bones[
            root_parent_bone_name]
        pole_translation = mathutils.Matrix.Translation(
            mathutils.Vector([0, 0, 50 if is_leg_ik else -50]))
        pole_rotation = mathutils.Matrix()
        pole_transform = pole_translation @ pole_rotation
        pole_target_bone_name = f'{root_parent_bone_name}_PoleTarget'
        pole_target_bone = self.armature.data.edit_bones.new(
            pole_target_bone_name)
        pole_target_bone.tail = (8, 0, 0)
        pole_target_bone.use_inherit_rotation = True
        pole_target_bone.use_local_location = True
        pole_target_bone.matrix = root_parent_edit_bone.matrix @ pole_transform
        pole_target_bone.parent = root_parent_edit_bone

        bpy.ops.object.mode_set(mode='POSE', toggle=False)

        mid_pose_bone = self.armature.pose.bones[mid_bone_name]
        effector_pose_bone = self.armature.pose.bones[effector_bone_name]
        # TODO: Consider removing the copy location constraint to prevent
        # stretching?
        copy_location_constraint = effector_pose_bone.constraints['POSITION']

        ik_constraint = mid_pose_bone.constraints.new('IK')
        ik_constraint.chain_count = 2
        ik_constraint.target = copy_location_constraint.target
        ik_constraint.subtarget = copy_location_constraint.subtarget
        ik_constraint.pole_target = self.armature  # target_armature
        ik_constraint.pole_subtarget = pole_target_bone_name
        ik_constraint.use_tail = True

        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  def init_value_tables(self, f, header):
    f.seek(header.time_table_offs)
    self.time_table = f.read_nfloat32(header.time_index_count)

    # Estimate the size of the value and slope tables by assuming data is
    # contiguous. It is okay to read more values than needed since no keyframe
    # will reference them.
    offsets = [
        header.aux_bone_hrc_table_offs, header.flag_table_offs,
        header.static_pose_table_offs, header.position_info_offs,
        header.direct_fcurve_table_offs, header.indirect_fcurve_table_offs,
        header.fcurve_key_table_offs, header.time_table_offs,
        header.value_table_offs, header.slope_table_offs,
        header.constraint_table_offs
    ]
    offsets.sort()
    for i in range(len(offsets) - 1):
      if offsets[i] == header.value_table_offs:
        end_offs = offsets[i + 1]
        f.seek(header.value_table_offs)
        self.value_table = f.read_nfloat32((end_offs - offsets[i]) // 4)
      elif offsets[i] == header.slope_table_offs:
        end_offs = offsets[i + 1]
        f.seek(header.slope_table_offs)
        self.slope_table = f.read_nfloat32((end_offs - offsets[i]) // 4)

  def parse_static_pose(self, f, header, bone_timelines):
    f.seek(header.static_pose_table_offs)
    for _ in range(header.static_pose_count):
      bone_index = f.read_uint16()
      channel = f.read_uint8()
      f.skip(1)
      value = f.read_float32()
      bone_timelines[bone_index].set_keyframe(0.0,
                                              value,
                                              channel,
                                              kf_type=KF_TYPE_CONSTANT)

  def parse_fcurves(self,
                    f,
                    table_offs,
                    count,
                    header,
                    bone_timelines,
                    base_id=0):
    if not self.time_table or not self.value_table or not self.slope_table:
      raise MsetImportError(
          'Must call init_value_tables() before parsing fcurves!')

    f.seek(table_offs)
    fcurve_entries = []
    for _ in range(count):
      bone_index = f.read_uint16() + base_id
      # TODO: Parse premode, postmode?
      channel = f.read_uint8() & 0xF
      key_count = f.read_uint8()
      key_start_index = f.read_uint16()
      fcurve_entries.append((bone_index, channel, key_count, key_start_index))

    for bone_index, channel, key_count, key_start_index in fcurve_entries:
      f.seek(header.fcurve_key_table_offs + key_start_index * 0x8)
      for _ in range(key_count):
        kf_type_and_time = f.read_uint16()
        kf_type = kf_type_and_time & 0x3
        time = self.time_table[kf_type_and_time >> 2]
        value = self.value_table[f.read_uint16()]
        slope_in = self.slope_table[f.read_uint16()]
        slope_out = self.slope_table[f.read_uint16()]
        bone_timelines[bone_index].set_keyframe(time, value, channel, kf_type,
                                                slope_in, slope_out)

  def apply_blender_fcurves(self,
                            header,
                            bone_timelines,
                            anb_name='Default',
                            ignore_scale=False):
    bpy.context.view_layer.objects.active = self.armature
    bpy.ops.object.mode_set(mode='POSE', toggle=False)

    if not self.armature.animation_data:
      self.armature.animation_data_create()
    action = self.armature.animation_data.action = bpy.data.actions.new(
        anb_name)

    for bone_index, bone_timeline in enumerate(bone_timelines):
      bone_name = self.get_bone_name(bone_index, header)
      pose_bone = self.armature.pose.bones[bone_name]
      pose_bone.rotation_mode = 'XYZ'

      fcurves = []
      if not ignore_scale:
        fcurves.append(
            action.fcurves.new(f'pose.bones["{bone_name}"].scale', index=0))
        fcurves.append(
            action.fcurves.new(f'pose.bones["{bone_name}"].scale', index=1))
        fcurves.append(
            action.fcurves.new(f'pose.bones["{bone_name}"].scale', index=2))
      else:
        fcurves.extend([None, None, None])
      fcurves.append(
          action.fcurves.new(f'pose.bones["{bone_name}"].rotation_euler',
                             index=0))
      fcurves.append(
          action.fcurves.new(f'pose.bones["{bone_name}"].rotation_euler',
                             index=1))
      fcurves.append(
          action.fcurves.new(f'pose.bones["{bone_name}"].rotation_euler',
                             index=2))
      fcurves.append(
          action.fcurves.new(f'pose.bones["{bone_name}"].location', index=0))
      fcurves.append(
          action.fcurves.new(f'pose.bones["{bone_name}"].location', index=1))
      fcurves.append(
          action.fcurves.new(f'pose.bones["{bone_name}"].location', index=2))

      def add_keyframe(channel, time, value):
        fcurves[channel].keyframe_points.add(1)
        fcurves[channel].keyframe_points[-1].interpolation = 'BEZIER'
        fcurves[channel].keyframe_points[-1].co = time, value

      # KH2 fcurves animate the bone transform directly. Blender animates bones
      # in pose space, sort of like an additive layer on top of the bone's edit
      # transform.
      #
      # We need to change the basis of the transform to pose space at each time
      # step. This method is *very* slow since it creates a lot of excessive
      # keyframes, but right now I do not have a good way to apply the fcurves
      # in the ANB directly.

      # TODO: Consider creating an action which "resets" the local transform of
      # each bone to the identity matrix and using Blender's NLA feature apply
      # another action on top of it which contains the original fcurves.
      prev_euler = None
      prev_scale = None
      axis_flip = False
      for t in range(math.ceil(bone_timeline.get_max_time()) + 1):
        scale, rot_euler, pos, axis_flip = bone_timeline.get_decomposed_transform_at_time(
            t, prev_euler, prev_scale, axis_flip)
        if not ignore_scale:
          add_keyframe(CHANNEL_SCX, t, scale[0])
          add_keyframe(CHANNEL_SCY, t, scale[1])
          add_keyframe(CHANNEL_SCZ, t, scale[2])
        add_keyframe(CHANNEL_RTX, t, rot_euler[0])
        add_keyframe(CHANNEL_RTY, t, rot_euler[1])
        add_keyframe(CHANNEL_RTZ, t, rot_euler[2])
        add_keyframe(CHANNEL_ETX, t, pos[0])
        add_keyframe(CHANNEL_ETY, t, pos[1])
        add_keyframe(CHANNEL_ETZ, t, pos[2])
        prev_euler = rot_euler
        prev_scale = scale

      for channel in range(9):
        fcurves[channel].update()

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  def get_bone_name(self, index, header):
    return f'Bone_{index}{"" if index < header.model_bone_count else "_Aux"}'


def load(context, filepath):
  options = Options()

  armature = None
  for obj in bpy.context.selected_objects:
    if obj.type != 'ARMATURE':
      continue
    if armature:
      return 'CANCELLED', 'More than one armature selected. Please select only the target armature before importing the MSET.'
    armature = obj

  if not armature:
    for obj in bpy.context.scene.objects:
      if obj.type != 'ARMATURE':
        continue
      if armature:
        return 'CANCELLED', 'More than one armature found. Please select an armature before importing the MSET.'
      armature = obj

  if not armature:
    return 'CANCELLED', 'No armatures found in the scene.'

  parser = MsetParser(options, armature)
  parser.parse(filepath)

  return 'FINISHED', ''
