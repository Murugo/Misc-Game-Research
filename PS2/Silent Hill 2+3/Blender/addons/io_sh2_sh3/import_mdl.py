# pylint: disable-import-error

if "bpy" in locals():
  # pylint: disable=used-before-assignment
  import importlib
  if "readutil" in locals():
    importlib.reload(readutil)
  if "vu" in locals():
    importlib.reload(vu)

import bpy
import math
import mathutils
import os
import struct

from .gsutil import gsutil
from .readutil import readutil
from . import vu


class MdlImportError(Exception):
  pass


class MaterialManager:
  def __init__(self):
    # {(texture index, blend) -> material}
    self.material_map = dict()

  def get_material(self, texture_index, blend, basename):
    key = (texture_index, blend)
    if key in self.material_map:
      return self.material_map[key]

    material = bpy.data.materials.new(
        name=f'{self.get_texture_name(texture_index, basename)}{"_t" if blend else ""}'
    )
    material.use_nodes = True

    bsdf = material.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Specular'].default_value = 0

    self.material_map[key] = material
    return material

  def get_materials(self, texture_index):
    materials = []
    keys = [(texture_index, False), (texture_index, True)]
    for key in keys:
      if key in self.material_map:
        materials.append(self.material_map[key])
    return materials

  def get_texture_name(self, texture_index, basename):
    return f'{basename}_tex_{texture_index}'


class ModelHeader:
  def __init__(self, f, offs):
    self.offs = offs
    f.seek(offs + 0x8)
    self.bone_transform_offs = offs + f.read_uint32()
    self.bone_count = f.read_uint32()
    self.bone_parent_table_offs = offs + f.read_uint32()
    self.helper_count = f.read_uint32()
    self.helper_table_offs = offs + f.read_uint32()
    self.helper_transform_offs = offs + f.read_uint32()
    self.submesh_count = f.read_uint32()
    self.submesh_start_offs = offs + f.read_uint32()
    self.submesh_blend_count = f.read_uint32()
    self.submesh_blend_start_offs = offs + f.read_uint32()
    self.image_count = f.read_uint32()
    self.image_table_offs = offs + f.read_uint32()
    self.texture_count = f.read_uint32()
    self.texture_table_offs = offs + f.read_uint32()
    f.skip(4)
    self.morph_base_vertex_count = f.read_uint32()
    self.morph_base_vertex_offs = offs + f.read_uint32()
    self.morph_data_count = f.read_uint32()
    self.morph_data_offs = offs + f.read_uint32()

class MdlParser:
  def __init__(self):
    self.basename = ''
    self.bone_matrices = []
    self.bone_matrices_it = []  # Inverse-transposed
    self.helper_table = []
    self.morph_targets = []
    self.armature = None
    self.vif_parser = vu.VifParser()
    self.mat_manager = MaterialManager()

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    f.seek(0x8)
    image_count = f.read_uint32()
    image_sector_offs = f.read_uint32()
    f.seek(0x14)
    model_offs = f.read_uint32()
    model_header = ModelHeader(f, model_offs)

    self.parse_morph_targets(f, model_header)
    self.parse_armature(f, model_header)
    self.parse_helper_armature(f, model_header)
    self.parse_submeshes(f, model_header.submesh_count,
                         model_header.submesh_start_offs, blend=False)
    self.parse_submeshes(f, model_header.submesh_blend_count,
                         model_header.submesh_blend_start_offs, blend=True)
    self.parse_textures(f, image_count, image_sector_offs, model_header)

    # Finalize the scene.
    self.armature.rotation_euler = (-math.pi / 2, 0, math.pi)
    self.armature.scale = (0.1, 0.1, 0.1)

  def parse_armature(self, f, header):
    self.bone_matrices = []
    self.bone_matrices_it = []
    f.seek(header.bone_transform_offs)
    for _ in range(header.bone_count):
      self.bone_matrices.append(mathutils.Matrix(
          [f.read_nfloat32(4) for _ in range(4)]
      ).transposed())
      self.bone_matrices_it.append(
          self.bone_matrices[-1].inverted().transposed())

    f.seek(header.bone_parent_table_offs)
    bone_parents = f.read_nint8(header.bone_count)

    armature_data = bpy.data.armatures.new('%s_Armature' % self.basename)
    self.armature = bpy.data.objects.new("%s_Armature" % self.basename,
                                         armature_data)

    bpy.context.scene.collection.objects.link(self.armature)
    bpy.context.view_layer.objects.active = self.armature
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)

    for index, (bone_matrix, parent_index) in enumerate(zip(self.bone_matrices, bone_parents)):
      bone = armature_data.edit_bones.new('Bone_%d' % index)
      bone.tail = (10, 0, 0)
      bone.use_inherit_rotation = True
      bone.use_local_location = True
      bone.matrix = bone_matrix
      if parent_index >= 0:
        bone.parent = armature_data.edit_bones[parent_index]
      bone.inherit_scale = 'ALIGNED'

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  # The "helper" armature contains transforms which can be used to blend
  # between a base (0) and target (1) bone in the model armature. Base and
  # target pairs for each helper are listed in the helper table. The purpose
  # of the helper armature is to calculate positions for vertices that are
  # influenced by more than one bone.
  #
  # Since Blender has its own method of applying transforms to vertex groups,
  # we do not need this second set of matrices. Code is left commented for
  # posterity.
  def parse_helper_armature(self, f, header):
    f.seek(header.helper_table_offs)
    self.helper_table = [f.read_nint8(2) for _ in range(header.helper_count)]

    # helper_matrices = []
    # f.seek(header.helper_transform_offs)
    # for i in range(header.helper_count):
    #   helper_matrix = mathutils.Matrix(
    #       [f.read_nfloat32(4) for _ in range(4)]
    #   ).transposed()
    #   helper_matrices.append(
    #       self.bone_matrices[self.helper_table[i][1]] @ helper_matrix)

    # helper_armature_data = bpy.data.armatures.new(
    #     '%s_HelperArmature' % self.basename)
    # helper_armature = bpy.data.objects.new("%s_HelperArmature" % self.basename,
    #                                        helper_armature_data)

    # bpy.context.scene.collection.objects.link(helper_armature)
    # bpy.context.view_layer.objects.active = helper_armature
    # bpy.ops.object.mode_set(mode='EDIT', toggle=False)

    # for index, helper_matrix in enumerate(helper_matrices):
    #   bone = helper_armature_data.edit_bones.new('Bone_%d_b_%d_t_%d' % (
    #       index, self.helper_table[index][0], self.helper_table[index][1]))
    #   bone.tail = (10, 0, 0)
    #   bone.use_inherit_rotation = True
    #   bone.use_local_location = True
    #   bone.matrix = helper_matrix
    #   bone.inherit_scale = 'ALIGNED'

    # bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  def parse_morph_targets(self, f, model_header):
    if not (model_header.morph_base_vertex_count or model_header.morph_data_count):
      return
    f.seek(model_header.morph_base_vertex_offs)
    base_pos_int16 = [f.read_nint16(3) for _ in range(
        model_header.morph_base_vertex_count)]
    if f.tell() % 0x10 > 0:
      f.skip(0x10 - (f.tell() % 0x10))
    base_norm_int16 = []
    has_normals = f.tell() < model_header.morph_data_offs
    if has_normals:
      base_norm_int16 = [f.read_nint16(3) for _ in range(
          model_header.morph_base_vertex_count)]

    f.seek(model_header.morph_data_offs)
    morph_target_desc = [f.read_nuint32(
        2) for _ in range(model_header.morph_data_count)]
    for vertex_count, offs in morph_target_desc:
      pos_int16 = base_pos_int16[:]
      norm_int16 = base_norm_int16[:]

      offs += model_header.offs
      f.seek(offs)
      for _ in range(vertex_count):
        delta_xyz = f.read_nint16(3)
        vertex_index = f.read_int16()
        pos_int16[vertex_index] = (
            base_pos_int16[vertex_index][0] + delta_xyz[0],
            base_pos_int16[vertex_index][1] + delta_xyz[1],
            base_pos_int16[vertex_index][2] + delta_xyz[2]
        )
      if has_normals:
        if f.tell() % 0x10 > 0:
          f.skip(0x10 - (f.tell() % 0x10))
        for _ in range(vertex_count):
          delta_xyz = f.read_nint16(3)
          vertex_index = f.read_int16()
          norm_int16[vertex_index] = (
              base_norm_int16[vertex_index][0] + delta_xyz[0],
              base_norm_int16[vertex_index][1] + delta_xyz[1],
              base_norm_int16[vertex_index][2] + delta_xyz[2]
          )

      self.morph_targets.append((pos_int16, norm_int16))

  def parse_submeshes(self, f, submesh_count, submesh_start_offs, blend=False):
    next_offs = submesh_start_offs
    for submesh_index in range(submesh_count):
      offs = next_offs
      f.seek(offs)
      next_offs = offs + f.read_uint32()
      f.skip(4)
      vif_offs = offs + f.read_uint32()
      vif_qwd = f.read_uint32()
      vif_addr = f.read_uint32()
      morph_ref_count = f.read_uint32()
      morph_ref_offs = offs + f.read_uint32()
      bone_palette_count = f.read_uint32()
      bone_palette_offs = offs + f.read_uint32()
      helper_palette_count = f.read_uint32()
      helper_palette_offs = offs + f.read_uint32()
      f.skip(12)
      texture_index_offs = offs + f.read_uint32()
      f.skip(4)
      material_type, display_group = f.read_nuint16(2)

      morph_refs = []
      if morph_ref_count:
        f.seek(morph_ref_offs)
        for _ in range(morph_ref_count):
          src_index = f.read_uint16()
          dst_addr = f.read_uint16()
          count = f.read_uint16()
          morph_refs.append((src_index, dst_addr, count))

      f.seek(bone_palette_offs)
      bone_palette = f.read_nint16(bone_palette_count)
      f.seek(helper_palette_offs)
      helper_palette = f.read_nint16(helper_palette_count)
      f.seek(texture_index_offs)
      texture_index = f.read_int16()

      f.seek(vif_offs)
      vtx, vn, uv, tri, vtx_group_dict, primary_bone_list = self.run_vif_parser(
          f.read(vif_qwd * 0x10), vif_addr, bone_palette, helper_palette)

      # Build Blender object.
      offs_str = '{0:#010x}'.format(offs)
      objname = f'{self.basename}_m_{submesh_index}_{offs_str}'
      objname += f'_{material_type}_{display_group}'
      objname += '_t' if blend else ''
      objname += '_b' if morph_ref_count > 0 else ''
      mesh_data = bpy.data.meshes.new(objname + '_mesh_data')
      mesh_data.from_pydata(vtx, [], tri)
      mesh_data.update()

      if uv:
        mesh_data.uv_layers.new(do_init=False)
        mesh_data.uv_layers[-1].data.foreach_set('uv', [
            vt for pair in [uv[loop.vertex_index] for loop in mesh_data.loops]
            for vt in pair
        ])

      obj = bpy.data.objects.new(objname, mesh_data)
      obj.data.materials.append(
          self.mat_manager.get_material(texture_index, blend,
                                        self.basename))

      # Required to derive the original position values for each vertex.
      obj['primary_bone_list'] = primary_bone_list

      # Apply blendshapes if used.
      if morph_refs and self.morph_targets:
        shape_key = obj.shape_key_add(name='ShapeKey_Base')
        shape_key.interpolation = 'KEY_LINEAR'
        obj.data.shape_keys.use_relative = True

        # Build packet to replace vertex data in VU1 memory.
        for morph_index, (morph_pos, _) in enumerate(self.morph_targets):
          shape_key = obj.shape_key_add(name='ShapeKey_%d' % morph_index)
          shape_key.interpolation = 'KEY_LINEAR'

          packet = b''
          for src_index, dst_addr, count in morph_refs:
            packet += struct.pack('<II', 0x01000104,
                                  0x69000000 | dst_addr | (count << 0x10))
            packet += b''.join([struct.pack('<hhh', morph_pos[src_index + i][0],
                               morph_pos[src_index + i][1], morph_pos[src_index + i][2]) for i in range(count)])
            if len(packet) % 0x4 > 0:
              packet += b'\x00' * (0x4 - len(packet) % 0x4)

          vtx_morph, vn_morph, _, _, _, _ = self.run_vif_parser(
              packet, vif_addr, bone_palette, helper_palette, morph_only=True)
          for i in range(len(vtx_morph)):
            shape_key.data[i].co = vtx_morph[i]
            # TODO: Sadly, Blender shape keys do not support custom split normals. Is there any other way?

      # Normals should be set after creating the mesh object to prevent Blender from recalculating them.
      custom_vn = []
      for face in mesh_data.polygons:
        for vertex_index in face.vertices:
          custom_vn.append(vn[vertex_index])
        face.use_smooth = True
      mesh_data.use_auto_smooth = True
      mesh_data.normals_split_custom_set(custom_vn)

      for i, v_list in vtx_group_dict.items():
        group = obj.vertex_groups.new(name='Bone_%d' % i)
        for v, weight in v_list:
          group.add([v], weight, 'ADD')

      # Attach geometry to armature
      if self.armature:
        obj.parent = self.armature
        modifier = obj.modifiers.new(type='ARMATURE', name='Armature')
        modifier.object = self.armature

      bpy.context.scene.collection.objects.link(obj)
      obj.select_set(state=True)

  def run_vif_parser(self, vif_packet, vif_addr, bone_palette, helper_palette, morph_only=False):
    self.vif_parser.parse(vif_packet)

    vertex_group_count, _, vertex_data_start_addr, bone_matrix_start_addr = self.vif_parser.read_uint32_xyzw(
        vif_addr)
    _, _, tristrip_addr, tristrip_end_addr = self.vif_parser.read_uint32_xyzw(
        vif_addr + 0x1)

    vtx_group_dict = dict()
    vtx = []
    vn = []
    uv = []
    primary_bone_list = []
    for vtx_group_index in range(vertex_group_count):
      vertex_count, helper_count, vertex_data_addr, vertex_data_end_addr = self.vif_parser.read_uint32_xyzw(
          vif_addr + 0x2 + vtx_group_index * 0x2)
      helper_count //= 2
      local_bone_addresses = self.vif_parser.read_uint32_xyzw(
          vif_addr + 0x3 + vtx_group_index * 0x2)[:helper_count + 1]
      local_bone_indices = [
          (addr - bone_matrix_start_addr) // 0x4 for addr in local_bone_addresses]

      bone_indices = [bone_palette[local_bone_indices[0]]]
      if bone_indices[0] not in vtx_group_dict:
        vtx_group_dict[bone_indices[0]] = []
      for i in range(helper_count):
        helper_bone_index = helper_palette[local_bone_indices[i + 1] - len(
            bone_palette)]
        target_bone = self.helper_table[helper_bone_index][1]
        bone_indices.append(target_bone)
        if target_bone not in vtx_group_dict:
          vtx_group_dict[target_bone] = []

      start_vtx_index = (vertex_data_addr - vertex_data_start_addr) // 0x4
      for vtx_index in range(vertex_count):
        pos = self.vif_parser.read_int32_xyzw(
            vertex_data_addr + vtx_index * 0x4)
        pos = [v / 0x10 for v in pos[:3]]
        pos_v = self.bone_matrices[bone_indices[0]
                                   ] @ mathutils.Vector(pos + [1.0])
        vtx.append(pos_v.to_3d().to_tuple())

        primary_bone_list.append(bone_indices[0])

        normal = self.vif_parser.read_int32_xyzw(
            vertex_data_addr + 0x1 + vtx_index * 0x4)
        normal = [-val / 0x1000 for val in normal[:3]]
        normal_v = self.bone_matrices_it[bone_indices[0]
                                         ] @ mathutils.Vector(normal + [0.0])
        vn.append(normal_v.to_3d().to_tuple())

        if morph_only:
          # UV and and vertex group assignments will not be populated.
          continue

        if helper_count > 0:
          weights = self.vif_parser.read_int32_xyzw(
              vertex_data_addr + 0x2 + vtx_index * 0x4)[:helper_count + 1]
          weights = [w / 0x1000 for w in weights]  # ITOF12
          for i, w in enumerate(weights):
            vtx_group_dict[bone_indices[i]].append(
                (start_vtx_index + vtx_index, w))
        else:
          vtx_group_dict[bone_indices[0]].append(
              (start_vtx_index + vtx_index, 1.0))

        uv_xyzw = self.vif_parser.read_int32_xyzw(
            vertex_data_addr + 0x3 + vtx_index * 0x4)
        uv.append((uv_xyzw[0] / 0x1000, 1.0 - uv_xyzw[1] / 0x1000))

    def get_vtx_index(tri_cmd):
      return ((tri_cmd & 0x7FFF) - vertex_data_start_addr) // 0x4

    tri = []
    reverse = True
    tri_xyzw_count = tristrip_end_addr - tristrip_addr
    tri_xyzw_list = [self.vif_parser.read_uint32_xyzw(
        tristrip_addr + i) for i in range(tri_xyzw_count)]
    tri_cmds = [t for xyzw in tri_xyzw_list for t in xyzw]
    for i, tri_cmd in enumerate(tri_cmds):
      if i > 1 and (tri_cmd & 0x8000) == 0:
        t1 = get_vtx_index(tri_cmd)
        t2 = get_vtx_index(tri_cmds[i - 1])
        t3 = get_vtx_index(tri_cmds[i - 2])
        if reverse:
          tri.append((t3, t2, t1))
        else:
          tri.append((t1, t2, t3))
      reverse = not reverse

    return vtx, vn, uv, tri, vtx_group_dict, primary_bone_list

  def parse_textures(self, f, image_count, image_sector_offs, header):
    # {image index -> [(texture index, palette index)]}
    image_to_textures = dict()
    for i in range(image_count):
      image_to_textures[i] = []
    f.seek(header.texture_table_offs)
    for texture_index in range(header.texture_count):
      image_index, palette_index = f.read_nint32(2)
      image_to_textures[image_index].append((texture_index, palette_index))

    gs_helper = gsutil.GSHelper()
    f.seek(image_sector_offs)
    if f.read_int32() < 0:
      f.seek(image_sector_offs + 0x8)
      f.seek(image_sector_offs + f.read_uint32())
    else:
      f.seek(image_sector_offs)
    for image_index in range(image_count):
      offs = f.tell()
      f.skip(8)
      width, height = f.read_nuint16(2)
      f.skip(4)
      image_data_size = f.read_uint32()
      header_size = f.read_uint8()
      f.skip(4)
      psm = f.read_uint8()
      unka = f.read_uint8()
      f.skip(1)
      tw, th = f.read_nuint8(2)

      unkb = 1 if unka > 0 else 0
      dbw = width >> 6 >> unkb
      rrw = width >> unkb
      rrh = height >> unka

      print(hex(offs), width, height, hex(image_data_size), hex(psm))

      f.seek(offs + header_size)

      # Upload texture data all at once (easier)
      image_data = f.read(image_data_size)
      gs_helper.UploadPSMCT32(dbp=0x1000, dbw=dbw, dsax=0,
                              dsay=0, rrw=rrw, rrh=rrh, inbuf=image_data)

      # Upload all CLUT data
      clut_dbw = 1
      if psm == gsutil.PSMT4 or psm == gsutil.PSMT8:
        print(hex(f.tell()))
        clut_data_size = f.read_uint32()
        f.skip(0xA)
        clut_width = f.read_uint8()
        f.skip(0x21)
        print(hex(clut_data_size), hex(clut_width))
        print('')

        clut_data = f.read(clut_data_size)
        clut_height = clut_data_size // (clut_width * 0x4)
        gs_helper.UploadPSMCT32(dbp=0x3640, dbw=clut_dbw, dsax=0,
                                dsay=0, rrw=clut_width, rrh=clut_height, inbuf=clut_data)

      # Build textures
      for texture_index, palette_index in image_to_textures[image_index]:
        read_cbp = 0x3640 + palette_index * 0x4
        print(
            f'Tex triple: i={image_index}, t={texture_index}, p={palette_index} ({hex(read_cbp)})')

        if psm == gsutil.PSMT4:
          pixels = gs_helper.DownloadImagePSMT4(dbp=0x1000, dbw=(
              width >> 6), dsax=0, dsay=0, rrw=width, rrh=height, cbp=read_cbp, cbw=clut_dbw, csa=0, alpha_reg=-1)
        elif psm == gsutil.PSMT8:
          pixels = gs_helper.DownloadImagePSMT8(dbp=0x1000, dbw=(
              width >> 6), dsax=0, dsay=0, rrw=width, rrh=height, cbp=read_cbp, cbw=clut_dbw, alpha_reg=-1)
        elif psm == gsutil.PSMCT32:
          raise MdlImportError(f'Unsupported PSM for download {hex(psm)}')
          # pixels = gs.gs_read_psmct32(gs_mem, dbp=0x1000, dbw=(
          #     width >> 6), rrw=width, rrh=height, cbp=read_cbp, cbw=clut_dbw, alpha_reg=-1)

        # Flip the image and convert pixels to float values so it appears correct in Blender.
        width_p = width * 4
        pixels = [
            pixels[(height - (i // width_p) - 1) *
                   width_p + (i % width_p)] / 255.0
            for i in range(width_p * height)
        ]

        texture_name = self.mat_manager.get_texture_name(
            texture_index, self.basename)
        image = bpy.data.images.new(f'{texture_name}.png',
                                    width=width,
                                    height=height)
        image.pixels = pixels
        image.update()
        # TODO: This still doesn't prevent Blender from GCing the texture?
        image.use_fake_user = True

        for material in self.mat_manager.get_materials(texture_index):
          tex_node = material.node_tree.nodes.new('ShaderNodeTexImage')
          tex_node.image = image

          bsdf = material.node_tree.nodes['Principled BSDF']
          bsdf.inputs['Specular'].default_value = 0
          material.node_tree.links.new(bsdf.inputs['Base Color'],
                                       tex_node.outputs['Color'])
          material.node_tree.links.new(bsdf.inputs['Alpha'],
                                       tex_node.outputs['Alpha'])


def load(context, filepath):
  try:
    parser = MdlParser()
    parser.parse(filepath)
  except (MdlImportError) as err:
    return 'CANCELLED', str(err)

  return 'FINISHED', ''
