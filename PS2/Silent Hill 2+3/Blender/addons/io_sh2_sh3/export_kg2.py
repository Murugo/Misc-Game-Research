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


class KgGeometry:
  def __init__(self):
    self.vertex_data = []
    self.vertex_count = 0
    self.prim = 0


class KgObject:
  def __init__(self):
    self.matrix = None
    self.matrix_inv = None
    self.matrix_inv_transpose = None
    self.kg_geometry_list = []
    self.prim = 0


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
    self.blender_object_list = []
    self.kg_object_list = []

  def init_with_selection(self):
    for obj in bpy.context.selected_objects:
      if obj.type == 'MESH':
        self.blender_object_list.append(obj)
    
    if not self.blender_object_list:
      for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
          self.blender_object_list.append(obj)

    if not self.blender_object_list:
      return 'No mesh objects found for export.'
    return None
  
  def export(self, filepath):
    for blender_obj in self.blender_object_list:
      kg_obj = KgObject()
      self.kg_object_list.append(kg_obj)

      kg_obj.matrix = self.get_transform_matrix([v.co for v in blender_obj.data.vertices])
      kg_obj.matrix_inv = kg_obj.matrix.inverted()
      kg_obj.matrix_inv_transpose = kg_obj.matrix_inv.transposed()

      if 'prim' in blender_obj:
        kg_obj.prim = blender_obj['prim']
      else:
        # Assume TRIANGLE_STRIP_ADV by default.
        kg_obj.prim = 6
      
      if kg_obj.prim in (1, 2):
        self.build_plane(blender_obj, kg_obj)
      elif kg_obj.prim in (5, 6):
        kg_obj.prim = 6
        self.build_triangle_strip_adv(blender_obj, kg_obj)
      else:
        raise KgExportError(f'Unsupported prim {kg_obj.prim} for object {blender_obj.name}')

      kg_obj.kg_geometry_list.sort(key=lambda geom: len(geom.vertex_data), reverse=True)

    self.write_file(filepath)
  
  def build_plane(self, blender_obj, kg_obj):
    for poly in blender_obj.data.polygons:
      kg_geometry = KgGeometry()
      kg_obj.kg_geometry_list.append(kg_geometry)

      normal = kg_obj.matrix_inv_transpose @ poly.normal
      kg_geometry.vertex_data.append([int(n * 0x8000 - 0.5) for n in normal.normalized().to_3d().to_tuple()] + [0])

      for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
        vertex = blender_obj.data.vertices[blender_obj.data.loops[loop_index].vertex_index]
        position = kg_obj.matrix_inv @ vertex.co
        kg_geometry.vertex_data.append([int(p) for p in position.to_3d().to_tuple()] + [1])
        kg_geometry.vertex_count += 1

  def build_triangle_strip_adv(self, blender_obj, kg_obj):
    # Start by triangulating the mesh.
    bm = bmesh.new()
    bm.from_mesh(blender_obj.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='FIXED', ngon_method='BEAUTY')
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    # Generate a graph of faces connected by shared edges.
    faces = [BMeshFace(bmface) for bmface in bm.faces]
    for bmedge in bm.edges:
      for bmface in bmedge.link_faces:
        faces[bmface.index].edges += [BMeshEdge(bmedge, faces[f.index]) for f in bmedge.link_faces if f.index != bmface.index]

    # Apply a modification of an SGI-based algorithm to generate triangle strips.
    # `face_queue` is a min heap where the top element is the face with the least amount of neighbors.
    # https://old.cescg.org/CESCG-2002/PVanecek/node4.html
    face_queue = []
    for f in faces:
      heapq.heappush(face_queue, (len(f.edges), f.bmface.index, f))
    
    class TriStrip:
      def __init__(self):
        self.loops = []
        self.flip = False
    
    def edge_eligible(edge, last_edge_pair, can_flip_strip):
      if edge.to_face.visited:
        return False
      if sorted(edge.vertex_indices) == sorted(last_edge_pair):
        return False
      if last_edge_pair[0] not in edge.vertex_indices and not can_flip_strip:
        return False
      return True

    tri_strips = []
    while face_queue:
      _, _, f = heapq.heappop(face_queue)
      if f.visited:
        continue
      f.visited = True
      strip = TriStrip()
      tri_strips.append(strip)
      for i in range(len(bm.faces)):
        if i == 0:
          # To extend the strip, select a connected triangle with the least number of neighbors.
          # If there is a tie, select the triangle with a neighbor that has the least number of neighbors (look-ahead heuristic).
          # If there is still a tie, select the triangle with the lowest BMFace index.
          next_edges = [
            (
              len(edge.to_face.edges),
              min([len(n.to_face.edges) for n in edge.to_face.edges if not n.to_face.visited], default=0),
              edge.to_face.bmface.index,
              edge
            ) for edge in f.edges if not edge.to_face.visited]
          if not next_edges:
            strip.loops.extend([bmloop for bmloop in f.bmface.loops])
            break
          _, _, _, chosen_edge = min(next_edges)

          first_loop = [bmloop for bmloop in f.bmface.loops if bmloop.vert.index not in chosen_edge.vertex_indices][0]
          last_loop = [bmloop for bmloop in chosen_edge.to_face.bmface.loops if bmloop.vert.index not in chosen_edge.vertex_indices][0]
          strip.loops.append(first_loop)
          strip.loops.append(first_loop.link_loop_next)
          strip.loops.append(first_loop.link_loop_next.link_loop_next)
          strip.loops.append(last_loop)

          f = chosen_edge.to_face
          f.visited = True
        
        else:
          # Extend the strip by following edges in a constant direction, ensuring that the strip remains sequential.
          v_index_a = strip.loops[-2].vert.index
          v_index_b = strip.loops[-3].vert.index
          last_edge_pair = (v_index_a, v_index_b)
          next_edge = [edge for edge in f.edges if edge_eligible(edge, last_edge_pair, i == 1)]
          if not next_edge:
            break
          # Flip the order of vertices in the first connecting edge if necessary to continue the strip
          if v_index_a not in next_edge[0].vertex_indices:
              # Flipping the order also changes the primitive type!
              strip.flip = True
              strip.loops[-2], strip.loops[-3] = strip.loops[-3], strip.loops[-2]
          strip.loops.append([bmloop for bmloop in next_edge[0].to_face.bmface.loops if bmloop.vert.index not in next_edge[0].vertex_indices][0])
          next_edge[0].to_face.visited = True

          f = next_edge[0].to_face
          f.visited = True

    # TODO: Vertex positions are slightly off. Could it be due to the rounding?
    vertex_data_list = []
    for strip in tri_strips:
      if len(strip.loops) < 3:
        continue
      kg_geometry = KgGeometry()
      kg_geometry.prim = kg_obj.prim - (1 if strip.flip else 0)
      kg_obj.kg_geometry_list.append(kg_geometry)
      for i, bmloop in enumerate(strip.loops):
        if i > 1:
          normal = kg_obj.matrix_inv_transpose @ bmloop.face.normal.to_4d()
          # kg_geometry.vertex_data.append([int(n * 0x8000 - 0.5) for n in normal.normalized().to_3d().to_tuple()] + [0])
          kg_geometry.vertex_data.append(normal.normalized().to_tuple())
        position = kg_obj.matrix_inv @ bmloop.vert.co.to_4d()
        # kg_geometry.vertex_data.append([int(p - 0.5) for p in position.to_3d().to_tuple()] + [1])
        kg_geometry.vertex_data.append(position.to_tuple())
        kg_geometry.vertex_count += 1
    
    # Done building triangle strips. Clean up the temporary BMesh.
    bm.free()

    return vertex_data_list

  def get_transform_matrix(self, vertices):
    x = sorted([v[0] for v in vertices])
    y = sorted([v[1] for v in vertices])
    z = sorted([v[2] for v in vertices])

    # Retain the fractional offset of the transform of an imported shadow model to avoid rounding errors.
    center_x = (x[0] + x[-1]) // 2 + (vertices[0].x % 1)
    center_y = (y[0] + y[-1]) // 2 + (vertices[0].y % 1)
    center_z = (z[0] + z[-1]) // 2 + (vertices[0].z % 1)
    center = mathutils.Vector((center_x, center_y, center_z))
    return mathutils.Matrix.Translation(center)
    
  def get_bounding_sphere(self, vertex_data):
    vertices = [mathutils.Vector(v[:3]) for v in vertex_data if v[3] == 1]
    x = sorted([v[0] for v in vertices])
    y = sorted([v[1] for v in vertices])
    z = sorted([v[2] for v in vertices])

    center_x = (x[0] + x[-1]) / 2
    center_y = (y[0] + y[-1]) / 2
    center_z = (z[0] + z[-1]) / 2
    center = mathutils.Vector((center_x, center_y, center_z))
    radius = max([(center - v).length for v in vertices])
    return int(round(center_x)), int(round(center_y)), int(round(center_z)), int(round(radius))
  
  def write_file(self, filepath):
    f = readutil.BinaryFileReadWriter(filepath)
    f.write_int32(0)
    f.write_int16(len(self.kg_object_list))
    f.write_nint16([0] * 5)
    for object_index, kg_obj in enumerate(self.kg_object_list):
      f.write_int32(0)
      f.write_int16(object_index)
      f.write_int16(len(kg_obj.kg_geometry_list))
      f.write_nuint32([0] * 4)
      f.write_nint16(self.get_bounding_sphere([v for kg_geom in kg_obj.kg_geometry_list for v in kg_geom.vertex_data]))
      f.write_nfloat32([x for row in kg_obj.matrix.transposed() for x in row])
      for kg_geom in kg_obj.kg_geometry_list:
        send_data_num = len(kg_geom.vertex_data) + 1
        qwd = int((len(kg_geom.vertex_data) + 3) // 2)
        f.write_nint16((kg_geom.vertex_count, kg_geom.prim, send_data_num, qwd))
        f.write_nint16(self.get_bounding_sphere(kg_geom.vertex_data))
        for x, y, z, w in kg_geom.vertex_data:
          if w == 1:
            f.write_nint16([int(round(n)) for n in (x, y, z)])
            f.write_int16(1)
          else:
            f.write_nint16([int(n * 0x8000 - 0.5) for n in (x, y, z)])
            f.write_int16(0)
          # f.write_nint16(xyzw)
        if len(kg_geom.vertex_data) % 2 == 1:
          f.write_nint32([0] * 2)


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
