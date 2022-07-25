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


class AncImportError(Exception):
  pass


class AncParser:
  def __init__(self):
    self.basename = ''
  
  def parse(self, filepath: str) -> None:
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    f.seek(0x4)
    frame_count = f.read_uint16()

    frame_base = bpy.context.scene.frame_current

    # TODO: Use an existing camera rig if one is selected.
    camera_obj, camera_parent_obj, camera_target_obj = self.build_camera_objects()
    camera = camera_obj.data

    if not camera.animation_data:
      camera.animation_data_create()
    if not camera_obj.animation_data:
      camera_obj.animation_data_create()
    if not camera_parent_obj.animation_data:
      camera_parent_obj.animation_data_create()
    if not camera_target_obj.animation_data:
      camera_target_obj.animation_data_create()
    camera.animation_data.action = camera_data_action = bpy.data.actions.new(f'{self.basename}_ANC')
    camera_obj.animation_data.action = camera_action = bpy.data.actions.new(f'{self.basename}_ANC')
    camera_parent_obj.animation_data.action = camera_parent_action = bpy.data.actions.new(f'{self.basename}_ANC')
    camera_target_obj.animation_data.action = camera_target_action = bpy.data.actions.new(f'{self.basename}_ANC')

    parent_loc_fcurves = [
      camera_parent_action.fcurves.new('location', index=0),
      camera_parent_action.fcurves.new('location', index=1),
      camera_parent_action.fcurves.new('location', index=2)
    ]
    target_loc_fcurves = [
      camera_target_action.fcurves.new('location', index=0),
      camera_target_action.fcurves.new('location', index=1),
      camera_target_action.fcurves.new('location', index=2)
    ]
    tilt_fcurve = camera_action.fcurves.new('rotation_euler', index=2)
    lens_fcurve = camera_data_action.fcurves.new('lens')

    def add_keyframe(fcurve, frame_index, val):
      fcurve.keyframe_points.add(1)
      kf = fcurve.keyframe_points[-1]
      kf.interpolation = 'LINEAR'
      kf.co = frame_index, val

    for frame in range(frame_count):
      # GsRVIEW2
      vpx, vpy, vpz = [v / 0x800 for v in f.read_nint16(3)]
      vrx, vry, vrz = [v / 0x800 for v in f.read_nint16(3)]
      rz = f.read_int16() / 0x168 + math.pi / 2
      fov = f.read_int16() * 0x168 / 0x1000

      # TODO: Factor of 0.37044 is an eyeballed estimate. What is the real factor?
      # MAIN_T.exe: instr @80025E78 reads the FOV value for a given frame.
      focal_length = camera.sensor_width * 0.37044 / math.tan(math.radians(fov / 2.0))

      add_keyframe(parent_loc_fcurves[0], frame_base + frame, vpx)
      add_keyframe(parent_loc_fcurves[1], frame_base + frame, vpy)
      add_keyframe(parent_loc_fcurves[2], frame_base + frame, vpz)
      add_keyframe(target_loc_fcurves[0], frame_base + frame, vrx)
      add_keyframe(target_loc_fcurves[1], frame_base + frame, vry)
      add_keyframe(target_loc_fcurves[2], frame_base + frame, vrz)
      add_keyframe(tilt_fcurve, frame_base + frame, rz)
      add_keyframe(lens_fcurve, frame_base + frame, focal_length)


  def build_camera_objects(self):
    camera_data = bpy.data.cameras.new(f'{self.basename}_Camera')
    camera_obj = bpy.data.objects.new(f'{self.basename}_Camera', camera_data)
    camera_data.display_size = 0.1
    bpy.context.scene.collection.objects.link(camera_obj)

    camera_parent_obj = bpy.data.objects.new(f'{self.basename}_CameraParent', None)
    camera_parent_obj.empty_display_type = 'PLAIN_AXES'
    camera_parent_obj.empty_display_size = 0.01
    camera_obj.parent = camera_parent_obj
    bpy.context.scene.collection.objects.link(camera_parent_obj)

    camera_obj.location = (0, 0, 0)
    camera_obj.rotation_euler = mathutils.Euler((0, 0, 0))

    camera_target_obj = bpy.data.objects.new(f'{self.basename}_CameraTarget', None)
    camera_target_obj.empty_display_type = 'PLAIN_AXES'
    camera_parent_obj.empty_display_size = 0.01
    bpy.context.scene.collection.objects.link(camera_target_obj)

    track_to_constraint = camera_parent_obj.constraints.new(type='TRACK_TO')
    track_to_constraint.target = camera_target_obj
    track_to_constraint.track_axis = 'TRACK_NEGATIVE_Z'
    track_to_constraint.up_axis = 'UP_Y'

    return camera_obj, camera_parent_obj, camera_target_obj


def load(context, filepath: str) -> 'tuple(str, str)':
  try:
    parser = AncParser()
    parser.parse(filepath)
  except (AncImportError) as err:
    return 'CANCELLED', str(err)

  return 'FINISHED', ''
