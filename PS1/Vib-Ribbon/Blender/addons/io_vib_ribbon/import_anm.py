# pylint: disable-import-error

if "bpy" in locals():
  # pylint: disable=used-before-assignment
  import importlib
  if "readutil" in locals():
    importlib.reload(readutil)

import bpy
import math
import os

from .readutil import readutil


class AnmImportError(Exception):
  pass


class AnmParser:
  def __init__(self):
    self.basename = ''

  def parse(self, filepath: str) -> None:
    # Assumes that Blender will always sort the list of objects by name.
    objects = bpy.context.selected_objects
    if not objects:
      raise AnmImportError('No objects select. Please select all objects belonging to the model before importing the ANM.')
    
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    f.seek(0x4)
    frame_count = f.read_uint16()
    frame_offs_list = [offs * 2 for offs in f.read_nuint16(frame_count + 1)]

    # bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    frame_base = bpy.context.scene.frame_current

    all_fcurves = [None for _ in range(len(objects))]

    def get_fcurve(action, path: str, index: int):
      fcurve = action.fcurves.find(path, index=index)
      if fcurve:
        return fcurve
      return action.fcurves.new(path, index=index)

    def get_obj_and_fcurves(obj_index: int):
      obj = objects[obj_index]
      if not obj.animation_data:
        obj.animation_data_create()
      if not obj.animation_data.action:
        obj.animation_data.action = bpy.data.actions.new(f'{obj.name}_ANM')
      action = obj.animation_data.action
      if not all_fcurves[obj_index]:
        all_fcurves[obj_index] = [
          get_fcurve(action, 'rotation_euler', index=0),
          get_fcurve(action, 'rotation_euler', index=1),
          get_fcurve(action, 'rotation_euler', index=2),
          get_fcurve(action, 'scale', index=0),
          get_fcurve(action, 'scale', index=1),
          get_fcurve(action, 'scale', index=2),
          get_fcurve(action, 'location', index=0),
          get_fcurve(action, 'location', index=1),
          get_fcurve(action, 'location', index=2),
        ]
      obj_fcurves = all_fcurves[obj_index]
      return obj, obj_fcurves

    for frame in range(frame_count):
      start_offs = frame_offs_list[frame]
      end_offs = frame_offs_list[frame + 1]
      f.seek(start_offs)
      active_object_indices = set()
      while f.tell() < end_offs:
        rot = []
        scale = []
        pos = []
        obj_index, flags = f.read_nuint8(2)
        if obj_index >= len(objects):
          raise AnmImportError(f'Not enough objects selected! Tried to animate nonexistent object index: {obj_index}, selected: {len(objects)}')
        if (flags & 0x1) > 0:
          rot = [v / 0x1000 * math.pi * 2 for v in f.read_nint16(3)]
        if (flags & 0x2) > 0:
          scale = [v / 0x1000 for v in f.read_nint16(3)]
        if (flags & 0x4) > 0:
          pos = [v / 0x800 for v in f.read_nint16(3)]
        
        active_object_indices.add(obj_index)
        obj, obj_fcurves = get_obj_and_fcurves(obj_index)

        if not scale:
          # Set a default scale for active objects
          scale = (1.0, 1.0, 1.0)

        if rot:
          obj.rotation_mode = 'XYZ'
          for i in range(3):
            obj_fcurves[i].keyframe_points.add(1)
            kf = obj_fcurves[i].keyframe_points[-1]
            kf.interpolation = 'LINEAR'
            kf.co = frame_base + frame, rot[i]
        if scale:
          for i in range(3):
            obj_fcurves[i + 3].keyframe_points.add(1)
            kf = obj_fcurves[i + 3].keyframe_points[-1]
            kf.interpolation = 'LINEAR'
            kf.co = frame_base + frame, scale[i]
        if pos:
          for i in range(3):
            obj_fcurves[i + 6].keyframe_points.add(1)
            kf = obj_fcurves[i + 6].keyframe_points[-1]
            kf.interpolation = 'LINEAR'
            kf.co = frame_base + frame, pos[i]

      # Hide inactive objects by setting their scale to zero
      for obj_index in range(len(objects)):
        if obj_index in active_object_indices:
          continue
        obj, obj_fcurves = get_obj_and_fcurves(obj_index)
        for i in range(3):
          kf_points = obj_fcurves[i + 3].keyframe_points
          if len(kf_points) > 0:
            kf_points[-1].interpolation = 'CONSTANT'
          kf_points.add(1)
          kf = kf_points[-1]
          kf.interpolation = 'CONSTANT'
          kf.co = frame_base + frame, 0.0

def load(context, filepath: str) -> 'tuple(str, str)':
  try:
    parser = AnmParser()
    parser.parse(filepath)
  except (AnmImportError) as err:
    return 'CANCELLED', str(err)

  return 'FINISHED', ''
  