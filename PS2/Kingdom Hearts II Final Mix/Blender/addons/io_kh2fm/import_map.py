# pylint: disable-import-error

if "bpy" in locals():
  # pylint: disable=used-before-assignment
  import importlib
  if "readutil" in locals():
    importlib.reload(readutil)

import bpy
import math
import os
import random

from mathutils import Matrix, Vector

from .readutil import readutil


class MapImportError(Exception):
  pass


def rhex(s: str) -> str:
  return hex(s)[2:]


def random_color() -> 'tuple(float, float, float, float)':
  hue = random.uniform(0.0, 360.0)
  value = random.uniform(0.25, 0.9)
  r = max(min(2 - abs((hue / 60 + 3) % 6 - 3), 1.0), 0.0) * value
  g = max(min(2 - abs((hue / 60 + 1) % 6 - 3), 1.0), 0.0) * value
  b = max(min(2 - abs((hue / 60 + 5) % 6 - 3), 1.0), 0.0) * value
  return (r, g, b, 1.0)


def create_bb_object(bb: 'tuple(float, float, float)', objname: str, world_matrix: Matrix) -> bpy.types.Object:
  def transform_vertex(x, y, z):
    return list((world_matrix @ Vector((x, y, z, 1))).xyz)
  
  bb_verts = [
    transform_vertex(bb[0], bb[1], bb[2]), transform_vertex(bb[3], bb[1], bb[2]),
    transform_vertex(bb[0], bb[4], bb[2]), transform_vertex(bb[3], bb[4], bb[2]),
    transform_vertex(bb[0], bb[1], bb[5]), transform_vertex(bb[3], bb[1], bb[5]),
    transform_vertex(bb[0], bb[4], bb[5]), transform_vertex(bb[3], bb[4], bb[5])
  ]
  bb_edges = [
    (0, 1), (1, 3), (0, 2), (2, 3), (4, 5), (5, 7), (4, 6), (6, 7),
    (0, 4), (1, 5), (2, 6), (3, 7)
  ]
  mesh_data = bpy.data.meshes.new('{}_mesh_data'.format(objname))
  mesh_data.from_pydata(bb_verts, bb_edges, [])
  mesh_data.update()
  return bpy.data.objects.new(objname, mesh_data)


class MapParser:
  def __init__(self) -> None:
    self.materials = []
    self.geom_objects = []
    self.doct_group_bb_objects = []


  def parse(self, filepath: str, import_geometry: bool, import_doct: bool, import_coct: bool) -> None:
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    map_geom_offs = 0
    map_tex_offs = 0
    doct_offs = 0
    coct_offs = 0
    for filetype, filename, fileoffset, _ in self.get_bar_files(f):
      if filetype == 0x4 and filename[0:3] == 'MAP':
        map_geom_offs = fileoffset
      elif filetype == 0x7 and filename[0:3] == 'MAP':
        map_tex_offs = fileoffset
      elif filetype == 0x5:
        doct_offs = fileoffset
      elif filetype == 0x6:
        coct_offs = fileoffset
      elif filetype == 0x7 and filename[0:3] == 'MAP':
        map_tex_offs = 0
      elif filetype == 0x6:
        self.process_coct(f, fileoffset, self.basename + '_col')
    
    if import_geometry:
      if map_tex_offs:
        self.process_textures(f, map_tex_offs, 'map')
      if map_geom_offs:
        self.process_geometry(f, map_geom_offs, 'map')
      if doct_offs and import_doct:
        self.process_doct(f, doct_offs)
        print('VIF objects: {} ({})'.format(len(self.geom_objects), rhex(len(self.geom_objects))))
        print('DOCT groups: {} ({})'.format(len(self.doct_group_bb_objects), rhex(len(self.doct_group_bb_objects))))
        self.set_geometry_parent_to_doct(f, map_geom_offs)
    if coct_offs and import_coct:
      self.process_coct(f, coct_offs)


  def get_bar_files(self, f: readutil.BinaryFileReader) -> 'list[int, str, int, int]':
    f.seek(0x4)
    num_files = f.read_uint32()
    barfiles = []
    f.skip(0x8)
    for i in range(num_files):
      filetype = f.read_uint32()
      filename = f.read_string(4)
      fileoffset = f.read_uint32()
      filesize = f.read_uint32()
      barfiles.append((filetype, filename, fileoffset, filesize))
    return barfiles


  def process_textures(self, f: readutil.BinaryFileReader, tex_offs: int, name_prefix: str) -> None:
    f.seek(tex_offs + 0xC)
    tex_count = f.read_uint32()

    # Create materials for some dummy textures
    for tex_index in range(tex_count):
      material = bpy.data.materials.new(name='{}_mat_{}'.format(name_prefix, tex_index))
      material.use_nodes = True

      vertex_color_node = material.node_tree.nodes.new('ShaderNodeVertexColor')
      bsdf = material.node_tree.nodes['Principled BSDF']
      bsdf.inputs['Specular'].default_value = 0
      bsdf.inputs['Base Color'].default_value = (0, 0, 0, 1)
      material.node_tree.links.new(bsdf.inputs['Emission'], vertex_color_node.outputs['Color'])

      self.materials.append(material)


  def process_geometry(self, f: readutil.BinaryFileReader, geom_offs: int, geom_name: str) -> None:
    max_uv_ind_flags_count = 0
    max_uv_ind_flags_offs = 0
    max_vert_count = 0
    max_vert_offs = 0

    geom_offs += 0x90
    vif_table_offs = geom_offs + 0x20
    f.seek(geom_offs + 0x10)
    vif_table_count = f.read_uint32()

    f.seek(vif_table_offs)
    vif_entries = []
    for vif_table_index in range(vif_table_count):
      vif_offs = geom_offs + f.read_uint32()
      texture_index = f.read_uint32()
      f.skip(2)
      translucent, unk = f.read_nuint16(2)
      f.skip(2)
      vif_entries.append((vif_table_index, vif_offs, texture_index, translucent, unk))
    
    # World transform.
    world_matrix = Matrix.Scale(0.02, 4) @ Matrix.Rotation(math.pi / 2, 4, 'X')

    for vif_table_index, vif_offs, texture_index, translucent, unk in vif_entries:
      f.seek(vif_offs + 0x10)
      # Do a high-level parse of the VIFcode (skipping unimportant commands).
      mask = 0

      uv = []
      ind = []
      flags = []
      vcol = []
      vtx = []
      ind_start = 0

      class VifHeader:
        def parse(self, f: readutil.BinaryFileReader, qwd: int) -> None:
          f.skip(0x10)
          self.uv_ind_flags_count, self.uv_ind_flags_addr, _, _ = f.read_nuint32(4)
          self.vertex_color_count, self.vertex_color_addr, _, _ = f.read_nuint32(4)
          self.vertex_count, self.vertex_addr, _, _ = f.read_nuint32(4)
          if qwd > 0x4:
            self.normal_count, self.normal_addr, _, _ = f.read_nuint32(4)
          else:
            self.normal_count = self.normal_addr = 0

      header = VifHeader()

      offs = vif_offs
      f.seek(offs)
      while offs < f.filesize:
        imm = f.read_uint16()
        qwd = f.read_uint8()
        cmd = f.read_uint8() & 0x7F

        if cmd >> 5 == 0b11:  # UNPACK
          if cmd == 0x60:
            break  # Done
          m = (cmd & 0x10) > 0
          addr = imm & 0x1FF
          vnvl = cmd & 0xF

          if vnvl == 0b1100:  # UNPACK V4-32
            if addr == 0 and not m:
              header.parse(f, qwd)
              if header.uv_ind_flags_count > max_uv_ind_flags_count:
                max_uv_ind_flags_count = header.uv_ind_flags_count
                max_uv_ind_flags_offs = offs
              if header.vertex_count > max_vert_count:
                max_vert_count = header.vertex_count
                max_vert_offs = offs
              ind_start = len(vtx)
            else:
              f.skip(qwd * 0x10)

          elif vnvl == 0b1000:  # UNPACK V3-32
            if addr == header.vertex_addr and m:
              for i in range(header.vertex_count):
                x, y, z = f.read_nfloat32(3)
                v = world_matrix @ Vector((x,y,z,1))
                vtx.append(list(v.xyz))
            elif addr == header.normal_addr and m:
              f.skip(qwd * 0xC)  # Unimplemented
            else:
              f.skip(qwd * 0xC)
          
          elif vnvl == 0b0010:  # UNPACK S-8
            if addr == header.uv_ind_flags_addr and m:
              if mask == 0xCFCFCFCF:
                ind += [i + ind_start for i in f.read_nuint8(header.uv_ind_flags_count)]
              elif mask == 0x3F3F3F3F:
                flags += f.read_nuint8(header.uv_ind_flags_count)
            else:
              f.skip(qwd)
            padding = (4 - (qwd % 4)) % 4
            f.skip(padding)
          
          elif vnvl == 0b0101:  # UNPACK V2-16
            if addr == header.uv_ind_flags_addr and not m:
              uv += [(f.read_int16() / 4096.0, f.read_int16() / 4096.0) for _ in range(header.uv_ind_flags_count)]
            else:
              f.skip(qwd * 0x4)
          
          elif vnvl == 0b1110:  # UNPACK V4-8
            if addr == header.vertex_color_addr:
              for i in range(header.vertex_color_count):
                vcol.append((
                  f.read_uint8() / 0x80,
                  f.read_uint8() / 0x80,
                  f.read_uint8() / 0x80,
                  f.read_uint8() / 0x80
                ))
            else:
              f.skip(qwd * 0x4)
          
          elif vnvl != 0b0000:
            raise Exception('Unexpected vnvl {} at offset {}'.format(rhex(vnvl), rhex(offs)))

        elif cmd == 0b00100000:  # STMASK
          mask = f.read_uint32()

        elif cmd == 0b00110001:  # STCOL
          f.skip(0x10)

        elif cmd not in (
          0b00000000,  # NOP
          0b00000001,  # STCYCL (always cl = 1, wl = 1)
          0b00010000,  # FLUSHE
          0b00010001,  # FLUSH
          0b00010011,  # FLUSHA
          0b00010111):  # MSCNT
          raise Exception('Unexpected cmd {} at offset {}'.format(rhex(cmd), rhex(offs)))

      tri = []
      vtx_expand = []
      for i, flag in zip(range(len(ind)), flags):
        vtx_expand.append(vtx[ind[i]])
        if flag == 0x20 or not flag:
          tri.append((i - 2, i - 1, i))
          # tri.append((ind[i - 2], ind[i - 1], ind[i]))
        if flag == 0x30 or not flag:
          tri.append((i, i - 1, i - 2))
          # tri.append((ind[i], ind[i - 1], ind[i - 2]))

      objname = '{}_vif_{}_{}'.format(self.basename, vif_table_index, rhex(unk))
      mesh_data = bpy.data.meshes.new(objname + '_mesh_data')
      mesh_data.from_pydata(vtx_expand, [], tri)
      mesh_data.update()

      mesh_data.vertex_colors.new()
      mesh_data.vertex_colors[-1].data.foreach_set('color', [rgba for col in [vcol[loop.vertex_index] for loop in mesh_data.loops] for rgba in col])

      mesh_data.uv_layers.new(do_init=False)
      mesh_data.uv_layers[-1].data.foreach_set('uv', [vt for pair in [uv[loop.vertex_index] for loop in mesh_data.loops] for vt in pair])

      obj = bpy.data.objects.new(objname + ('_t' if translucent else ''), mesh_data)
      bpy.context.scene.collection.objects.link(obj)
      obj.select_set(state=True)

      if texture_index >= 0 and texture_index < len(self.materials):
        obj.data.materials.append(self.materials[texture_index])

      self.geom_objects.append(obj)

    print('Max UV/Ind/Flag count: {}, location: {}'.format(max_uv_ind_flags_count, rhex(max_uv_ind_flags_offs)))
    print('Max Vertex count: {}, location: {}'.format(max_vert_count, rhex(max_vert_offs)))


  def process_doct(self, f: readutil.BinaryFileReader, doct_offs: int) -> None:
    f.seek(doct_offs + 0x14)
    node_table_offs = doct_offs + f.read_uint32()
    node_table_size = f.read_uint32()
    node_count = node_table_size // 0x30
    group_table_offs = doct_offs + f.read_uint32()
    group_table_size = f.read_uint32()
    group_count = group_table_size // 0x1C
    # f.seek(doct_offs + 0x24)
    # unk_table_offs = f.read_uint32() + doct_offs
    # unk_table_size = f.read_uint32()  # Always zero?

    self.doct_group_bb_objects = [None] * group_count

    # World transform for bounding boxes (note that this is *not* the same as geometry world matrix)
    world_matrix = Matrix.Scale(0.02, 4) @ Matrix.Rotation(-math.pi / 2, 4, 'X')

    # Parse octree for display nodes for occlusion culling
    node_bb_objects = [None] * node_count
    for node_index in reversed(range(node_count)):
      node_offs = node_table_offs + node_index * 0x30

      f.seek(node_offs + 0x10)
      bb = f.read_nfloat32(6)
      node_bb_obj = create_bb_object(bb, '{}_doct_node_{}_bb'.format(self.basename, node_index), world_matrix)
      node_bb_objects[node_index] = node_bb_obj
      
      f.seek(node_offs)
      node_children = f.read_nint16(8)
      for child_index in node_children:
        if child_index < 0 or not node_bb_objects[child_index]:
          continue
        node_bb_objects[child_index].parent = node_bb_obj
      
      f.seek(node_offs + 0x28)
      group_start_index = f.read_int16()
      group_end_index = f.read_int16()
      for group_index in range(group_start_index, group_end_index):
        group_offs = group_table_offs + group_index * 0x1C

        f.seek(group_offs + 0x4)
        bb = f.read_nfloat32(6)
        group_bb_obj = create_bb_object(bb, '{}_doct_node_{}_group_{}_bb'.format(self.basename, node_index, group_index), world_matrix)
        group_bb_obj.parent = node_bb_obj

        self.doct_group_bb_objects[group_index] = group_bb_obj

        bpy.context.scene.collection.objects.link(group_bb_obj)
      
      bpy.context.scene.collection.objects.link(node_bb_obj)
      node_bb_obj.select_set(state=True)


  def set_geometry_parent_to_doct(self, f: readutil.BinaryFileReader, geom_offs: int) -> None:
    geom_offs += 0x90
    f.seek(geom_offs + 0x18)
    group_offset_table_offs = geom_offs + f.read_uint32()
    f.seek(group_offset_table_offs)
    group_offset_table = [f.read_uint32() + geom_offs for _ in range(len(self.doct_group_bb_objects))]
    for group_index, group_offset in enumerate(group_offset_table):
      f.seek(group_offset)
      i = 0
      while True:
        vif_index = f.read_int16()
        if vif_index < 0:
          break
        self.geom_objects[vif_index].parent = self.doct_group_bb_objects[group_index]
        i += 1


  def process_coct(self, f: readutil.BinaryFileReader, coct_offs: int) -> None:
    # f.seek(coct_offs + 0x10)
    # header_offs = f.read_uint32() + coct_offs
    # header_size = f.read_uint32()
    f.seek(coct_offs + 0x18)
    group_table_offs = f.read_uint32() + coct_offs
    group_table_size = f.read_uint32()
    mesh_table_offs = f.read_uint32() + coct_offs
    # mesh_table_size = f.read_uint32()
    f.skip(0x4)
    poly_table_offs = f.read_uint32() + coct_offs
    poly_table_size = f.read_uint32()
    position_table_offs = f.read_uint32() + coct_offs
    position_table_size = f.read_uint32()
    # normal_table_offs = f.read_uint32() + coct_offs
    # normal_table_size = f.read_uint32()
    # unk1_table_offs = f.read_uint32() + coct_offs
    # unk1_table_size = f.read_uint32()
    # unk2_table_offs = f.read_uint32() + coct_offs
    # unk2_table_ssize = f.read_uint32()

    print("COCT: {}".format(coct_offs))
    print("Group table offs:{}".format(rhex(group_table_offs)))
    print("Mesh table offs: {}".format(rhex(mesh_table_offs)))
    print("Poly table offs: {}".format(rhex(poly_table_offs)))
    print("Poly table size: {}".format(rhex(poly_table_size)))

    # World transform for bounding boxes (note that this is *not* the same as geometry world matrix)
    world_matrix = Matrix.Scale(0.02, 4) @ Matrix.Rotation(-math.pi / 2, 4, 'X')

    vertex_table = []
    f.seek(position_table_offs)
    for i in range(int(position_table_size / 0x10)):
      x, y, z, _ = f.read_nfloat32(4)
      v = world_matrix @ Vector((x,y,z,1))
      vertex_table.append(list(v.xyz))
    
    col_objects = []
    material_index_map = dict()

    group_object_map = dict()
    group_count = int(group_table_size / 0x20)
    for group_index in range(group_count):
      group_offs = group_table_offs + group_index * 0x20
      
      f.seek(group_offs + 0x10)
      group_bb = f.read_nint16(6)
      group_bb_objname = "{}_coct_node_{}_bb".format(self.basename, group_index)
      group_bb_obj = create_bb_object(group_bb, group_bb_objname, world_matrix)
      # Set bounding box object as top-level parent of node in the collision tree
      group_object_map[group_index] = group_bb_obj
      bpy.context.scene.collection.objects.link(group_bb_obj)

      # TODO: Purpose of zero indices for specific nodes?
      f.seek(group_offs + 0x1C)
      mesh_start_index = f.read_int16()
      mesh_end_index = f.read_int16()
      for mesh_index in range(mesh_start_index, mesh_end_index):
        mesh_offs = mesh_table_offs + mesh_index * 0x14

        f.seek(mesh_offs)
        mesh_bb = f.read_nint16(6)
        mesh_bb_objname = "{}_coct_node_{}_group_{}_bb".format(self.basename, group_index, mesh_index)
        mesh_bb_obj = create_bb_object(mesh_bb, mesh_bb_objname, world_matrix)
        mesh_bb_obj.parent = group_bb_obj
        bpy.context.scene.collection.objects.link(mesh_bb_obj)

        polygons = []
        mat_indices = []
        f.seek(mesh_offs + 0xC)
        poly_start_index = f.read_uint16()
        poly_end_index = f.read_uint16()
        for poly_index in range(poly_start_index, poly_end_index):
          poly_offs = poly_table_offs + poly_index * 0x10
          f.seek(poly_offs + 0x2)
          f1, f2, f3, f4 = f.read_nint16(4)
          polygons.append((f1, f2, f3, f4))

          # Surface index that indicates the step sound effect.
          # f.seek(poly_offs)
          # surface_index = f.read_uint16()

          # Surface index that points to entry in flags table.
          f.seek(poly_offs + 0xE)
          surface_index = f.read_uint16()
          if surface_index in material_index_map:
            mat_indices.append(material_index_map[surface_index])
          else:
            material_index = len(material_index_map)
            mat_indices.append(material_index)
            material_index_map[surface_index] = material_index

        # Create smaller vertex list with only required vertices and remap face indices.
        vertices = []
        faces = []
        index_map = dict()

        def remap_index(f):
            if f in index_map:
              return index_map[f]
            vertices.append(vertex_table[f])
            new_index = len(vertices) - 1
            index_map[f] = new_index
            return new_index
        
        for f1, f2, f3, f4 in polygons:
          if f4 > 0:
            faces.append((remap_index(f1), remap_index(f2), remap_index(f3), remap_index(f4)))
          else:
            faces.append((remap_index(f1), remap_index(f2), remap_index(f3)))
        
        objname = "{}_coct_node_{}_group_{}".format(self.basename, group_index, mesh_index)

        mesh_data = bpy.data.meshes.new('{}_mesh_data'.format(objname))
        mesh_data.from_pydata(vertices, [], faces)
        mesh_data.update()
        obj = bpy.data.objects.new(objname, mesh_data)

        for i, mat_index in enumerate(mat_indices):
          mesh_data.polygons[i].material_index = mat_index

        bpy.context.scene.collection.objects.link(obj)
        obj.parent = mesh_bb_obj
        col_objects.append(obj)
  
    # Create materials based on polygon properties
    mat_pairs = [(material_index_map[x], x) for x in material_index_map]
    mat_pairs.sort()
    for _, surface_index in mat_pairs:
      material = bpy.data.materials.new(name="%s_col_surface_%s" % (self.basename, surface_index))
      material.use_nodes = True

      bsdf = material.node_tree.nodes['Principled BSDF']
      bsdf.inputs['Specular'].default_value = 0
      if surface_index == 0:
        color = (0.8, 0.8, 0.8, 1.0)
      else:
        color = random_color()
      bsdf.inputs['Base Color'].default_value = color
    
      # TODO: Not every collision mesh needs every material
      for obj in col_objects:
        obj.data.materials.append(material)

    # Visualize collision tree by reparenting groups
    for group_index in range(group_count):
      group_offs = group_table_offs + group_index * 0x20
      f.seek(group_offs)
      children = f.read_nint16(8)
      f.seek(group_offs + 0x1C)
      start_mesh = f.read_uint16()
      end_mesh = f.read_uint16()
      print("{}: {}, {} -> {}".format(group_index, children, start_mesh, end_mesh))

    for group_index in range(group_count):
      if group_index not in group_object_map:
        continue
      group_offs = group_table_offs + group_index * 0x20

      f.seek(group_offs)
      for i in range(8):
        child_index = f.read_int16()
        if child_index < 0:
          continue
        if child_index in group_object_map:
          group_object_map[child_index].parent = group_object_map[group_index]


def load(context, filepath: str, import_geometry: bool = True, import_doct: bool = False, import_coct: bool = False) -> 'tuple[str, str]':
  try:
    parser = MapParser()
    parser.parse(filepath, import_geometry, import_doct, import_coct)
  except (MapImportError) as err:
    return 'CANCELLED', str(err)

  return 'FINISHED', ''
