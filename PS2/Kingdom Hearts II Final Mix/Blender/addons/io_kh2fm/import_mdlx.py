# pylint: disable-import-error

if "bpy" in locals():
  # pylint: disable=used-before-assignment
  import importlib
  if "readutil" in locals():
    importlib.reload(readutil)

import bpy
import collections
import os
import math
import mathutils

from .gsutil import gsutil
from . import readutil

Options = collections.namedtuple('Options', ['USE_EMISSION'])


class MdlxImportError(Exception):
  pass


class MaterialManager:
  def __init__(self, options):
    # {(texture index, use_alpha) -> material}
    self.material_map = dict()
    self.options = options

  def get_material(self, texture_index, use_alpha, basename):
    key = (texture_index, use_alpha)
    if key in self.material_map:
      return self.material_map[key]

    material = bpy.data.materials.new(
        name=
        f'{self.get_texture_name(texture_index, basename)}{"_t" if use_alpha else ""}'
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


class VifHeader:
  def __init__(self, header):
    self.type = header[0]
    self.uv_ind_flags_count = header[4]
    self.uv_ind_flags_addr = header[5]
    self.vtx_bone_assign_addr = header[6]
    # self.bone_matrix_addr = header[7]
    self.vcol_count = header[8] if self.type == 1 else 0
    self.vcol_addr = header[9] if self.type == 1 else 0
    self.vtx_mix_count = header[10] if self.type == 1 else 0
    self.vtx_mix_addr = header[11] if self.type == 1 else 0
    self.vtx_count = header[12] if self.type == 1 else header[8]
    self.vtx_addr = header[13] if self.type == 1 else header[9]
    self.bone_count = header[15] if self.type == 1 else header[11]


class VifParser:
  def __init__(self, bone_matrices):
    self.bone_matrices = bone_matrices

  def parse(self, f, offs, qwc):
    uv = []
    ind = []
    flags = []
    vtx = []
    vtx_local = []
    # (bone index, weight)
    vtx_to_bone = []

    header = None
    mask = 0
    ind_start = 0

    end_offs = offs + (qwc << 4)
    # TODO: Remove use of offs. I don't believe this does any significant jumps
    # anywhere.
    while offs < end_offs:
      f.seek(offs)
      imm = f.read_uint16()
      qwd = f.read_uint8()
      cmd = f.read_uint8() & 0x7F
      offs += 0x4

      if cmd >> 5 == 0b11:  # UNPACK
        if cmd == 0x60:
          break  # Done
        m = (cmd & 0x10) > 0
        addr = imm & 0x1FF
        vnvl = cmd & 0xF

        if vnvl == 0b1100:  # UNPACK V4-32
          if addr == 0 and not m:
            header = VifHeader(f.read_nuint32(qwd << 4))
            ind_start = len(vtx)
            vtx_local = []
          elif addr == header.vtx_addr:
            vtx_local = [f.read_nfloat32(4) for _ in range(header.vtx_count)]

          elif addr == header.vtx_bone_assign_addr:
            # Assign local vertices to bones
            vtx_to_bone_local = []
            for i in range(header.bone_count):
              vtx_to_bone_local.extend([i for _ in range(f.read_uint32())])
            if header.vtx_mix_addr > 0:
              # Build final vertex list by mixing vertices
              mix_header_offs = offs + (
                  (header.vtx_mix_addr - header.vtx_bone_assign_addr) << 4)
              mix_offs = mix_header_offs + math.ceil(
                  header.vtx_mix_count / 0x4) * 0x10
              f.seek(mix_header_offs)
              mix_count_table = f.read_nuint32(header.vtx_mix_count)
              for i in range(header.vtx_mix_count):
                f.seek(mix_offs)
                for vtx_list in [
                    f.read_nuint32(i + 1) for _ in range(mix_count_table[i])
                ]:
                  bone_list = []
                  for v in vtx_list:
                    bone_list.append((vtx_to_bone_local[v], vtx_local[v][3]))
                  vtx_to_bone.append(bone_list)
                  v_mixed = mathutils.Vector((0, 0, 0, 0))
                  for v in vtx_list:
                    v_mixed += (self.bone_matrices[vtx_to_bone_local[v]]
                                @ mathutils.Vector(vtx_local[v]))
                  vtx.append(v_mixed.to_3d().to_tuple())
                mix_offs += math.ceil(
                    (mix_count_table[i] * (i + 1) * 0x4) / 0x10) * 0x10
            else:
              for i in range(len(vtx_local)):
                vtx.append(
                    (self.bone_matrices[vtx_to_bone_local[i]]
                     @ mathutils.Vector(vtx_local[i])).to_3d().to_tuple())
                vtx_to_bone.append([(vtx_to_bone_local[i], 1.0)])

          offs += qwd * 0x10

        elif vnvl == 0b1000:  # UNPACK V3-32
          if addr == header.vtx_addr and m:
            vtx_local = [
                f.read_nfloat32(3) + (1.0,) for i in range(header.vtx_count)
            ]
          offs += qwd * 0xC

        elif vnvl == 0b0010:  # UNPACK S-8
          if addr == header.uv_ind_flags_addr and m:
            if mask == 0xCFCFCFCF:
              ind += [
                  i + ind_start
                  for i in f.read_nuint8(header.uv_ind_flags_count)
              ]
            elif mask == 0x3F3F3F3F:
              flags += f.read_nuint8(header.uv_ind_flags_count)
          offs += int(math.ceil(qwd / 4)) * 0x4

        elif vnvl == 0b0101:  # UNPACK V2-16
          if addr == header.uv_ind_flags_addr and not m:
            uv += [(f.read_int16() / 4096.0, 1.0 - f.read_int16() / 4096.0)
                   for _ in range(header.uv_ind_flags_count)]
          offs += qwd * 0x4

        elif vnvl == 0b1110:  # UNPACK V4-8
          # TODO: Support vertex colors?
          # if addr == header.vertex_color_addr:
          #   for i in range(header.vertex_color_count):
          #     vcol.append((
          #       f.read_uint8() / 0x80,
          #       f.read_uint8() / 0x80,
          #       f.read_uint8() / 0x80,
          #       f.read_uint8() / 0x80
          #     ))
          offs += qwd * 0x4

        elif vnvl != 0b0000:
          raise Exception('Unexpected vnvl {} at offset {}'.format(
              hex(vnvl), hex(offs)))

      elif cmd == 0b00100000:  # STMASK
        mask = f.read_uint32()
        offs += 0x4

      elif cmd == 0b00110001:  # STCOL
        offs += 0x10

      elif cmd not in (
          0b00000000,  # NOP
          0b00000001,  # STCYCL (always cl = 1, wl = 1)
          0b00010000,  # FLUSHE
          0b00010001,  # FLUSH
          0b00010011,  # FLUSHA
          0b00010111):  # MSCNT
        raise Exception('Unexpected cmd {} at offset {}'.format(
            hex(cmd), hex(offs)))

    # Build triangle list
    tri = []
    vtx_expand = []
    vtx_to_bone_expand = []
    for i, f in zip(range(len(ind)), flags):
      vtx_expand.append(vtx[ind[i]])
      vtx_to_bone_expand.append(vtx_to_bone[ind[i]])
      if i < 2:
        continue
      if f == 0x20 or not f:
        tri.append((i - 2, i - 1, i))
      if f == 0x30 or not f:
        tri.append((i, i - 1, i - 2))

    # Build vertex groups
    vtx_groups = [[] for _ in range(len(self.bone_matrices))]
    for i, bone_list in enumerate(vtx_to_bone_expand):
      for bone, weight in bone_list:
        vtx_groups[bone].append((i, weight))

    return vtx_expand, tri, uv, vtx_groups


class MdlxParser:
  def __init__(self, options):
    self.options = options
    self.basename = ''
    self.armature = None
    self.bone_matrices = []
    self.objects = []
    self.mat_manager = MaterialManager(options)

  def parse(self, filepath):
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    f = readutil.BinaryFileReader(filepath)

    model_offs = 0
    tex_offs = 0
    for file_type, _, file_offs, _ in self.get_bar_files(f):
      if file_type == 0x4:
        model_offs = file_offs
      elif file_type == 0x7:
        tex_offs = file_offs

    if model_offs > 0:
      self.parse_model(f, model_offs)
    if tex_offs > 0:
      self.parse_textures(f, tex_offs)

  def get_bar_files(self, f):
    if f.read_uint32() != 0x1524142:  # BAR\x01
      raise MdlxImportError('Expected BAR magic at offset 0x0')
    file_count = f.read_uint32()
    f.skip(0x8)
    files = []
    for _ in range(file_count):
      file_type, file_name, file_offs, file_size = (f.read_uint32(),
                                                    f.read_string(4),
                                                    f.read_uint32(),
                                                    f.read_uint32())
      files.append((file_type, file_name, file_offs, file_size))
    return files

  def parse_model(self, f, model_offs):
    model_offs += 0x90
    f.seek(model_offs + 0x10)

    bone_count = f.read_uint16()
    f.skip(2)  # texture_count
    bone_table_offs = model_offs + f.read_uint32()
    self.parse_bones(f, bone_table_offs, bone_count)

    model_index = 0
    while model_offs > 0:
      f.seek(model_offs)
      model_type = f.read_uint32()
      f.skip(0x8)
      next_model_offs = f.read_uint32()
      if model_type == 0x3:  # Model type SKLRAW
        f.seek(model_offs + 0x1C)
        group_count = f.read_uint32()
        for group_index in range(group_count):
          group_entry_offs = model_offs + group_index * 0x20 + 0x20
          self.parse_submodel(f, group_entry_offs, model_offs, model_index,
                              group_index)
      else:
        print(
            f'Skipping unsupported model type {model_type} at offset {hex(model_offs)}'
        )

      model_offs = (next_model_offs + model_offs) if next_model_offs > 0 else 0
      model_index += 1

    # Attach geometry to armature
    if self.armature and self.objects:
      for obj in self.objects:
        obj.parent = self.armature
        modifier = obj.modifiers.new(type='ARMATURE', name='Armature')
        modifier.object = self.armature
        obj.select_set(state=True)

    # Finalize scene
    self.armature.rotation_euler = (math.pi / 2, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  def parse_bones(self, f, bone_table_offs, bone_count):
    if bone_count == 0:
      return

    self.bone_matrices = [None] * bone_count
    armature_data = bpy.data.armatures.new('%s_Armature' % self.basename)
    self.armature = bpy.data.objects.new("%s_Armature" % self.basename,
                                         armature_data)

    bpy.context.scene.collection.objects.link(self.armature)
    bpy.context.view_layer.objects.active = self.armature
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)

    f.seek(bone_table_offs)
    for _ in range(bone_count):
      index, _, parent_index, _ = f.read_nint16(
          4)  # Skip sibling index, child index
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
        global_matrix = armature_data.edit_bones[
            parent_index].matrix @ local_matrix
      else:
        global_matrix = local_matrix

      bone = armature_data.edit_bones.new('Bone_%d' % index)
      bone.tail = (4, 0, 0)
      bone.use_inherit_rotation = True
      bone.use_local_location = True
      bone.matrix = global_matrix
      if parent_index >= 0:
        bone.parent = armature_data.edit_bones[parent_index]
      # Store a custom property that preserves the original Euler angles.
      # The MSET importer will apply keyframes on top of these angles.
      bone['local_euler'] = local_euler

      self.bone_matrices[index] = global_matrix

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  def parse_submodel(self, f, group_entry_offs, base_model_offs, model_index,
                     group_index):
    f.seek(group_entry_offs)
    attr, texture_index = f.read_nuint32(2)
    use_alpha = (attr & 1) > 0
    f.skip(0x8)  # polygon_num, has_vb, alt
    dma_offs = base_model_offs + f.read_uint32()
    f.skip(0x4)  # matrixinfo_offs
    dma_qwd = f.read_uint32()
    dma_end_offs = dma_offs + (dma_qwd << 4)

    offs = dma_offs
    while offs < dma_end_offs:
      f.seek(offs)
      shape_offs = offs
      cmd = f.read_uint32()
      vif_qwc = cmd & 0xFFFF
      vif_offs = base_model_offs + f.read_uint32()
      f.skip(0x8)
      bone_palette = []
      bone_palette_matrices = []
      while cmd != 0x10000000:
        offs += 0x10
        cmd, bone_index, _, _ = f.read_nuint32(4)
        if cmd != 0x30000004:
          continue
        bone_palette.append(bone_index)
        bone_palette_matrices.append(self.bone_matrices[bone_index])

      offs += 0x10
      vif_parser = VifParser(bone_palette_matrices)
      vtx, tri, uv, vtx_groups = vif_parser.parse(f, vif_offs, vif_qwc)

      objname = '{}_{}_{}_{}'.format(self.basename, model_index, group_index,
                                     hex(shape_offs)[2:])
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
          self.mat_manager.get_material(texture_index, use_alpha,
                                        self.basename))

      for i, v_list in enumerate(vtx_groups):
        group = obj.vertex_groups.new(name='Bone_%d' % bone_palette[i])
        for v, weight in v_list:
          group.add([v], weight, 'ADD')

      bpy.context.scene.collection.objects.link(obj)
      obj.select_set(state=True)

      self.objects.append(obj)

  def parse_textures(self, f, tex_offs):
    f.seek(tex_offs + 0x4)  # Skip type, flag
    clut_data_num, image_count, texture_count = f.read_nuint32(3)
    texture_to_image_offs = tex_offs + f.read_uint32()
    image_upload_packet_offs = tex_offs + f.read_uint32()
    texture_env_packet_offs = tex_offs + f.read_uint32()
    image_data_offs = tex_offs + f.read_uint32()
    clut_data_offs = tex_offs + f.read_uint32()
    f.seek(texture_to_image_offs)
    texture_to_image_list = f.read_nuint8(texture_count)

    # Build reverse lookup from image index -> [texture indices]
    image_to_texture_dict = dict()
    for texture_index, image_index in enumerate(texture_to_image_list):
      if image_index in image_to_texture_dict:
        image_to_texture_dict[image_index].append(texture_index)
      else:
        image_to_texture_dict[image_index] = [texture_index]

    class GSContext:
      def __init__(self, gs):
        self.gs = gs
        self.bitbltbuf = None
        self.trxpos = None
        self.trxreg = None
        self.tex0 = None
        self.clamp = None

      def parse_packet(self, f, offs):
        f.seek(offs + 0x10)  # Skip DMAtag, texflush, direct packets
        # Assume GIFtag is a PACKED transfer using A+D mode
        nloop = f.read_uint16() & 0x7FFF
        f.skip(0xE)
        for _ in range(nloop):
          data, reg = f.read_nuint64(2)
          if reg == gsutil.BITBLTBUF:
            self.bitbltbuf = gsutil.GSRegBITBLTBUF(data)
          elif reg == gsutil.TRXPOS:
            self.trxpos = gsutil.GSRegTRXPOS(data)
          elif reg == gsutil.TRXREG:
            self.trxreg = gsutil.GSRegTRXREG(data)
          elif reg == gsutil.TEX0_1:
            self.tex0 = gsutil.GSRegTEX0(data)
          elif reg == gsutil.CLAMP_1:
            self.clamp = gsutil.GSRegCLAMP(data)

      def upload(self, data):
        if self.bitbltbuf.dpsm == gsutil.PSMCT32:
          self.gs.UploadPSMCT32(self.bitbltbuf.dbp, self.bitbltbuf.dbw,
                                self.trxpos.dsax, self.trxpos.dsay,
                                self.trxreg.rrw, self.trxreg.rrh, data)
        elif self.bitbltbuf.dpsm == gsutil.PSMT8:
          self.gs.UploadPSMT8(self.bitbltbuf.dbp, self.bitbltbuf.dbw,
                              self.trxpos.dsax, self.trxpos.dsay,
                              self.trxreg.rrw, self.trxreg.rrh, data)
        elif self.bitbltbuf.dpsm == gsutil.PSMT4:
          self.gs.UploadPSMT4(self.bitbltbuf.dbp, self.bitbltbuf.dbw,
                              self.trxpos.dsax, self.trxpos.dsay,
                              self.trxreg.rrw, self.trxreg.rrh, data)

      def download_and_parse_texture(self):
        rrw, rrh, dsax, dsay = self.get_region()
        if self.tex0.psm == gsutil.PSMT8:
          pixels = self.gs.DownloadImagePSMT8(self.tex0.tbp0,
                                              self.tex0.tbw,
                                              dsax,
                                              dsay,
                                              rrw,
                                              rrh,
                                              self.tex0.cbp,
                                              cbw=1,
                                              alpha_reg=-1)
        elif self.tex0.psm == gsutil.PSMT4:
          pixels = self.gs.DownloadImagePSMT4(self.tex0.tbp0,
                                              self.tex0.tbw,
                                              dsax,
                                              dsay,
                                              rrw,
                                              rrh,
                                              self.tex0.cbp,
                                              cbw=1,
                                              csa=self.tex0.csa,
                                              alpha_reg=-1)
        else:
          raise MdlxImportError(f'Unsupported PSM {hex(self.tex0.psm)}!')

        # Flip the image so it appears correct in Blender, and convert
        # components to float values.
        rrwp = rrw * 4
        pixels = [
            pixels[(rrh - (i // rrwp) - 1) * rrw * 4 + (i % rrwp)] / 255.0
            for i in range(rrwp * rrh)
        ]
        return pixels

      def get_region(self):
        # width (rrw), height (rrh), dsax, dsay
        return (abs(self.clamp.maxu - self.clamp.minu) + 1,
                abs(self.clamp.maxv - self.clamp.minv) + 1,
                min(self.clamp.minu,
                    self.clamp.maxu), min(self.clamp.minv, self.clamp.maxv))

      def __repr__(self):
        return (
            f'BITBLTBUF: {self.bitbltbuf}\nTRXPOS: {self.trxpos}\nTRXREG: {self.trxreg}\n'
            + f'TEX0: {self.tex0}\nCLAMP: {self.clamp}')

    gs = gsutil.GSHelper()

    clut_context = GSContext(gs)
    clut_context.parse_packet(f, image_upload_packet_offs)

    f.seek(image_upload_packet_offs + 0x74)
    clut_data_offs = tex_offs + f.read_uint32()  # DMAtag REF address
    f.skip(0x4)
    clut_data_size = f.read_uint16() << 4

    f.seek(clut_data_offs)
    clut_data = f.read(clut_data_size)
    if len(clut_data) < clut_data_size:
      # Pad CLUT data when there are fewer colors than the specified size
      clut_data += b'\x00' * (clut_data_size - len(clut_data))
    clut_context.upload(clut_data)

    image_context = GSContext(gs)
    for image_index in range(image_count):
      packet_offs = image_upload_packet_offs + (image_index + 1) * 0x90
      image_context.parse_packet(f, packet_offs)
      f.seek(packet_offs + 0x74)
      image_data_offs = tex_offs + f.read_uint32()  # DMAtag REF address
      f.skip(0x4)
      image_data_size = f.read_uint16() << 4

      f.seek(image_data_offs)
      image_context.upload(f.read(image_data_size))

      for texture_index in image_to_texture_dict[image_index]:
        packet_offs = texture_env_packet_offs + texture_index * 0xA0
        image_context.parse_packet(f, packet_offs)
        pixels = image_context.download_and_parse_texture()

        width, height, _, _ = image_context.get_region()
        texture_name = self.mat_manager.get_texture_name(
            texture_index, self.basename)
        image = bpy.data.images.new(f'{texture_name}.png',
                                    width=width,
                                    height=height)
        image.pixels = pixels
        image.update()

        for material in self.mat_manager.get_materials(texture_index):
          tex_node = material.node_tree.nodes.new('ShaderNodeTexImage')
          tex_node.image = image

          bsdf = material.node_tree.nodes['Principled BSDF']
          bsdf.inputs['Specular'].default_value = 0
          if self.options.USE_EMISSION:
            material.node_tree.links.new(bsdf.inputs['Emission'],
                                         tex_node.outputs['Color'])
            bsdf.inputs['Base Color'].default_value = (0, 0, 0, 1)
          else:
            material.node_tree.links.new(bsdf.inputs['Base Color'],
                                         tex_node.outputs['Color'])
          material.node_tree.links.new(bsdf.inputs['Alpha'],
                                       tex_node.outputs['Alpha'])


def load(context, filepath, *, use_emission=False):
  options = Options(use_emission)

  try:
    parser = MdlxParser(options)
    parser.parse(filepath)
  except (MdlxImportError) as err:
    return 'CANCELLED', str(err)

  return 'FINISHED', ''
