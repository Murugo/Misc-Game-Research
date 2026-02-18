# pylint: disable-import-error

if "bpy" in locals():
  # pylint: disable=used-before-assignment
  import importlib
  if "readutil" in locals():
    importlib.reload(readutil)

import bmesh
import bpy
import heapq
import math
import mathutils
import os

from .readutil import readutil


class KgExportError(Exception):
  pass


class BMeshEdge:
  def __init__(self, bmedge, to_face):
    self.vertex_indices = [v.index for v in bmedge.verts]
    self.to_face = to_face


class BMeshFace:
  def __init__(self, bmface):
    self.bmface = bmface
    self.edges = []
    self.visited = False


class KgExporter():
  def __init__(self):
    self.armature = None
    self.bone_to_objects = {}
    self.bone_to_vertex_data_list = {}
  
  def init_with_selection(self):
    object_set = set()

    # Find objects to export that are attached to a single armature
    for obj in bpy.context.selected_objects:
      if obj.type == 'ARMATURE':
        if self.armature:
          return 'More than one armature selected. Please select only the target armature before exporting the KG1.'
        self.armature = obj
      elif obj.type == 'MESH':
        object_set.add(obj)
    
    for obj in object_set:
      if not obj.parent or obj.parent.type != 'ARMATURE':
        return 'All selected objects must be parented to an armature.'
      if self.armature and obj.parent != self.armature:
        return 'Selected objects are attached to more than one armature. Please select only the target armature before exporting the KG1.'
      self.armature = obj.parent
    
    if not self.armature:
      return 'No armature selected. Please select an armature for exporting the KG1.'

    if not object_set:
      for obj in self.armature.children:
        if obj.type != 'MESH':
          continue
        object_set.add(obj)

    # Build dictionary from bone name to list of objects
    for obj in object_set:
      if not obj.vertex_groups:
        continue
      for vertex_group in obj.vertex_groups:
        bone_name = vertex_group.name
        bone_index = int(bone_name.split('_')[1])
        found = False
        for i in range(len(obj.data.vertices)):
          if vertex_group.weight(i) > 0.0:
            if bone_index not in self.bone_to_objects:
              self.bone_to_objects[bone_index] = [obj]
            else:
              self.bone_to_objects[bone_index] += [obj]
            found = True
            break
        if found:
          break

    return None

  def export(self, filename):
    if not self.armature or not self.bone_to_objects:
      raise KgExportError('Nothing to export!')

    for bone_index in self.bone_to_objects:
      self.bone_to_vertex_data_list[bone_index] = []

    for bone_index, object_list in self.bone_to_objects.items():
      for obj in object_list:
        vertex_data_list = self.process_object(bone_index, obj)
        self.bone_to_vertex_data_list[bone_index].extend(vertex_data_list)
    
    self.write_file(filename)
  
  def process_object(self, bone_index, obj):
    # Convert the mesh to triangle strips. Start by triangulating the mesh.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='FIXED', ngon_method='BEAUTY')
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    # Generate a graph of faces connected by shared edges.
    faces = [BMeshFace(bmface) for bmface in bm.faces]
    for bmedge in bm.edges:
      for bmface in bmedge.link_faces:
        faces[bmface.index].edges += [BMeshEdge(bmedge, faces[f.index]) for f in bmedge.link_faces if f.index != bmface.index]

    # for v in bm.verts:
    #   print(f'Vertex {v.index}: {v.co}')
    # for f in faces:
    #   print(f'Face {f.bmface.index} -> {[edge.to_face.bmface.index for edge in f.edges]}')

    # Apply a modification of an SGI-based algorithm to generate triangle strips.
    # `face_queue`` is a min heap where the top element is the face with the least amount of neighbors.
    # https://old.cescg.org/CESCG-2002/PVanecek/node4.html
    face_queue = []
    for f in faces:
      heapq.heappush(face_queue, (len(f.edges), f.bmface.index, f))

    tri_strips = []
    while face_queue:
      _, _, f = heapq.heappop(face_queue)
      if f.visited:
        continue
      f.visited = True

      strip = []
      tri_strips.append(strip)
      for i in range(len(bm.faces)):
        if i == 0:
          # To extend the strip, select a connected triangle with the least number of neighbors.
          # If there is a tie, select the triangle with a neighbor that has the least number of neighbors (look-ahead heuristic).
          # If there is still a tie, seelect the triangle with the lowest BMFace index.
          next_edges = [
            (
              len(edge.to_face.edges),
              min([len(n.to_face.edges) for n in edge.to_face.edges if not n.to_face.visited], default=0),
              edge.to_face.bmface.index,
              edge
            ) for edge in f.edges if not edge.to_face.visited]
          if not next_edges:
            strip.extend([bmloop for bmloop in f.bmface.loops])
            break
          _, _, _, chosen_edge = min(next_edges)

          first_loop = [bmloop for bmloop in f.bmface.loops if bmloop.vert.index not in chosen_edge.vertex_indices][0]
          last_loop = [bmloop for bmloop in chosen_edge.to_face.bmface.loops if bmloop.vert.index not in chosen_edge.vertex_indices][0]
          strip.append(first_loop)
          strip.append(first_loop.link_loop_next)
          strip.append(first_loop.link_loop_next.link_loop_next)
          strip.append(last_loop)

          f = chosen_edge.to_face
          f.visited = True
        
        else:
          # Extend the strip by following edges in a constant direction, ensuring that the strip remains sequential.
          v_index_a = strip[i + 1].vert.index
          v_index_b = strip[i + 2].vert.index
          edge_pair = [v_index_a, v_index_b]
          next_edge = [edge for edge in f.edges if not edge.to_face.visited and sorted(edge.vertex_indices) == sorted(edge_pair)]
          if not next_edge:
            break
          strip.append([bmloop for bmloop in next_edge[0].to_face.bmface.loops if bmloop.vert.index not in edge_pair][0])
          next_edge[0].to_face.visited = True

          f = next_edge[0].to_face
          f.visited = True

    # for strip in tri_strips:
    #   print(f'Strip: {[loop.vert.index for loop in strip]}')
    #   for loop in strip:
    #     print(loop.face.normal)
    # print('')
    
    transform = self.armature.matrix_world @ self.armature.data.bones[f'Bone_{bone_index}'].matrix_local
    transform_inv = transform.inverted()
    transform_pos = transform_inv @ obj.matrix_world
    transform_normal = (transform_inv @ obj.matrix_world).transposed().inverted()
    vertex_data_list = []
    for strip in tri_strips:
      if len(strip) < 3:
        continue
      vertex_data = []
      for i, bmloop in enumerate(strip):
        if i > 1:
          # normal = transform_transpose @ (obj.matrix_world @ bmloop.face.normal)
          normal = transform_normal @ bmloop.face.normal
          vertex_data.append([int(n * 0x8000 - 0.5) for n in normal.normalized().to_3d().to_tuple()] + [0])
        position = transform_pos @ bmloop.vert.co
        vertex_data.append([int(p) for p in position.to_3d().to_tuple()] + [1])
      vertex_data_list.append(vertex_data)

    # TODO: Build bounding sphere: https://b3d.interplanety.org/en/how-to-calculate-the-bounding-sphere-for-selected-objects/

    # Done building triangle strips. Clean up the temporary BMesh.
    bm.free()

    return vertex_data_list

  def get_bounding_sphere(self, vertex_data):
    vertices = [mathutils.Vector(v[:3]) for v in vertex_data if v[3] == 1]
    x = sorted([v[0] for v in vertices])
    y = sorted([v[1] for v in vertices])
    z = sorted([v[2] for v in vertices])

    center_x = (x[0] + x[-1]) // 2
    center_y = (y[0] + y[-1]) // 2
    center_z = (z[0] + z[-1]) // 2
    center = mathutils.Vector((center_x, center_y, center_z))
    radius = max([(center - v).length for v in vertices])
    return int(center_x), int(center_y), int(center_z), int(radius)

  def write_file(self, filename):
    f = readutil.BinaryFileReadWriter(filename)
    f.write_int32(0)
    f.write_int16(len(self.bone_to_vertex_data_list))
    f.write_nint16([0] * 5)
    for bone_index, vertex_data_list in sorted(self.bone_to_vertex_data_list.items()):
      f.write_int32(0)
      f.write_int16(bone_index)
      f.write_int16(len(vertex_data_list))
      f.write_nuint32([0] * 4)
      f.write_nint16(self.get_bounding_sphere([v for vertex_data in vertex_data_list for v in vertex_data]))
      f.write_nuint32([0] * 16)  # Unused matrix
      for vertex_data in vertex_data_list:
        vertex_count = (len(vertex_data) + 2) // 2
        prim = 6  # TODO: Can this change?
        send_data_num = len(vertex_data) + 1
        qwd = int((len(vertex_data) + 2.5) // 2)
        f.write_nint16((vertex_count, prim, send_data_num, qwd))
        f.write_nint16(self.get_bounding_sphere(vertex_data))
        for xyzw in vertex_data:
          f.write_nint16(xyzw)
        if len(vertex_data) % 2 == 1:
          f.write_nint32([0] * 2)

      # TODO: Write geometry groups


def export(context, filepath):
  exporter = KgExporter()
  error_reason = exporter.init_with_selection()
  if error_reason:
    return 'CANCELLED', error_reason
  try:
    exporter.export(filepath)
  except KgExportError as err:
    return 'CANCELLED', str(err)
  return 'FINISHED', ''
