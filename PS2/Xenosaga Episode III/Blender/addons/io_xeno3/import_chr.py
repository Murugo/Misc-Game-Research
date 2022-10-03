''' Import Xenosaga Episode III (PS2) CHR model file '''

from . import vu
from .gsutil import gsutil
from .readutil import readutil
import mathutils
import bpy
import math
import os

if 'bpy' in locals():
  # pylint: disable=used-before-assignment
  import importlib
  if 'gsutil' in locals():
    importlib.reload(gsutil)
  if 'readutil' in locals():
    importlib.reload(readutil)
  if 'vu' in locals():
    importlib.reload(vu)


class ChrImportError(Exception):
  '''CHR import error.'''


class PxyMaterial:
  '''Container for a PXY model texture and Blender material.'''

  def __init__(self, material: bpy.types.Material, image: bpy.types.Image, width: int, height: int, tw: int, th: int):
    self.material = material
    self.image = image
    self.width = width
    self.height = height
    self.u_scale = (1 << tw) / width
    self.v_scale = (1 << th) / height


class MaterialManager:
  '''Manager class for Blender materials.'''

  def __init__(self, basename: str, txy: 'TxyParser'):
    self.basename = basename
    self.txy = txy
    # {(TEX0, alpha) -> PxyMaterial}
    self.pxy_material_map = dict()

  def get_pxy_material(self, tex0_value: int, clamp_value: int, alpha: bool) -> PxyMaterial:
    '''Returns a PxyMaterial for the given texture properties.'''
    key = (tex0_value, clamp_value, alpha)
    if key in self.pxy_material_map:
      return self.pxy_material_map[key]

    tex0 = gsutil.GSRegTEX0(tex0_value)
    clamp = gsutil.GSRegCLAMP(clamp_value)

    texture_name = self.txy.get_texture_name(tex0.tbp0, tex0.cbp)
    if not texture_name:
      texture_name = f'__{self.basename}_mat_{len(self.pxy_material_map)}'

    image = self.download_image(tex0, clamp, texture_name)
    width, height = image.size
    material = self.build_material(image, alpha, texture_name)

    pxy_material = PxyMaterial(
      material, image, width, height, tex0.tw, tex0.th)
    self.pxy_material_map[key] = pxy_material
    return pxy_material

  def download_image(self, tex0: gsutil.GSRegTEX0, clamp: gsutil.GSRegCLAMP, texture_name: str) -> bpy.types.Image:
    '''Returns a new image texture using data provided by the TXY.'''
    width = abs(clamp.maxu - clamp.minu) + 1
    height = abs(clamp.maxv - clamp.minv) + 1
    if tex0.psm == gsutil.PSMT4:
      pixels = self.txy.gs_helper.DownloadImagePSMT4(
        dbp=tex0.tbp0, dbw=tex0.tbw, dsax=0, dsay=0, rrw=width, rrh=height, cbp=tex0.cbp, cbw=1, csa=tex0.csa, alpha_reg=-1)
    elif tex0.psm == gsutil.PSMT8:
      pixels = self.txy.gs_helper.DownloadImagePSMT8(
        dbp=tex0.tbp0, dbw=tex0.tbw, dsax=0, dsay=0, rrw=width, rrh=height, cbp=tex0.cbp, cbw=1, alpha_reg=-1)
    elif tex0.psm == gsutil.PSMCT32:
      pixels = self.txy.gs_helper.DownloadPSMCT32(
        dbp=tex0.tbp0, dbw=tex0.tbw, dsax=0, dsay=0, rrw=width, rrh=height)
    else:
      raise ChrImportError(f'Unknown PSM {hex(tex0.psm)}! (TEX0: {hex(tex0)})')

    # Flip the image and convert pixels to float values so it appears correct in Blender.
    width_p = width * 4
    alpha_factor = 128.0 if tex0.psm == gsutil.PSMCT32 else 255.0
    pixels = [
        pixels[(height - (i // width_p) - 1) *
               width_p + (i % width_p)] / (255.0 if (i % 4) < 3 else alpha_factor)
        for i in range(width_p * height)
    ]

    image = bpy.data.images.new(f'{texture_name}.png',
                                width=width,
                                height=height,
                                alpha=True)
    image.pixels = pixels
    image.update()
    image.use_fake_user = True
    return image

  def build_material(self, image: bpy.types.Image, alpha: bool, texture_name: str) -> bpy.types.Material:
    '''Returns a new Blender material.'''
    material = bpy.data.materials.new(
      name=f'{texture_name}{"_t" if alpha else ""}'
    )
    material.use_nodes = True
    material.blend_method = 'BLEND' if alpha else 'CLIP'
    if not alpha:
      material.alpha_threshold = 0.95

    tex_node = material.node_tree.nodes.new('ShaderNodeTexImage')
    tex_node.image = image

    vcol_node = material.node_tree.nodes.new('ShaderNodeVertexColor')

    col_mult_node = material.node_tree.nodes.new('ShaderNodeMixRGB')
    col_mult_node.blend_type = 'MULTIPLY'
    col_mult_node.inputs['Fac'].default_value = 1.0
    material.node_tree.links.new(col_mult_node.inputs['Color1'],
                                 tex_node.outputs['Color'])
    material.node_tree.links.new(col_mult_node.inputs['Color2'],
                                 vcol_node.outputs['Color'])

    alpha_mult_node = material.node_tree.nodes.new('ShaderNodeMath')
    alpha_mult_node.operation = 'MULTIPLY'
    material.node_tree.links.new(alpha_mult_node.inputs[0],
                                 tex_node.outputs['Alpha'])
    material.node_tree.links.new(alpha_mult_node.inputs[1],
                                 vcol_node.outputs['Alpha'])

    bsdf = material.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Specular'].default_value = 0

    material.node_tree.links.new(bsdf.inputs['Base Color'],
                                 col_mult_node.outputs['Color'])
    material.node_tree.links.new(bsdf.inputs['Alpha'],
                                 alpha_mult_node.outputs['Value'])

    return material


class FileEntry:
  '''Top-level file entry.'''

  def __init__(self, offset: int, size: int):
    self.offset = offset
    self.size = size


class XhrBone:
  '''Single bone in an XHR hierarchy.'''

  def __init__(self,
               index: int, group: str,
               pos: 'tuple(float, float, float)',
               rot: 'tuple(float, float, float)',
               rot2: 'tuple(float, float, float)',
               scale: 'tuple(float, float, float)',
               parent: 'XhrBone' = None):
    self.index = index
    self.group = group
    self.pos = pos
    self.rot = rot
    self.rot2 = rot2
    self.scale = scale
    self.parent = parent

    # Name of the bone in Blender.
    self.name = f'Bone_{self.index}_{self.group}'

    self.local_matrix = None
    self.global_matrix = None
    self.evaluate_matrix()

  def evaluate_matrix(self) -> None:
    '''Builds local and global matrices.'''
    local_euler = mathutils.Euler(self.rot)
    local_euler2 = mathutils.Euler(self.rot2)
    mat_rot = local_euler.to_matrix().to_4x4()
    mat_rot2 = local_euler2.to_matrix().to_4x4()
    mat_scale = mathutils.Matrix()
    for i in range(3):
      mat_scale[i][i] = self.scale[i]  # pylint:disable=unsubscriptable-object
    mat_pos = mathutils.Matrix()
    for i in range(3):
      mat_pos[i][3] = self.pos[i]  # pylint:disable=unsubscriptable-object
    self.local_matrix = mat_pos @ mat_rot @ mat_rot2 @ mat_scale
    if self.parent:
      self.global_matrix = self.parent.global_matrix @ self.local_matrix
    else:
      self.global_matrix = self.local_matrix


class XhrParser:
  '''Parser class for XHR file format (hierarchy / skeleton).'''

  def __init__(self, basename: str):
    self.basename = basename
    self.bones = []
    # self.armature = None

  def parse(self, file: readutil.BinaryFileReader, offset: int) -> None:
    '''Parses bones from the XHR file at the given offset in an opened file.'''
    file.set_base_offset(offset)

    group_a_count = file.seek(0x10).read_uint32() - 1
    group_b_count = file.read_uint32()
    group_c_count = file.read_uint32()
    group_d_count = file.read_uint32()
    group_e_count = file.read_uint32()
    group_b_offset = file.seek(0x28).read_uint32()
    group_c_offset = file.read_uint32()
    group_d_offset = file.read_uint32()
    group_e_offset = file.read_uint32()

    # Root bone
    root_parent = file.seek(0x70).read_int32()
    if root_parent >= 0:
      raise ChrImportError(
         f'Expected parent of root bone to be -1, got {hex(file.tell() - 4)}')
    root_pos = file.read_nfloat32(3)
    root_rot = file.read_nfloat32(3)
    root_scale = file.read_nfloat32(3)
    self.bones.append(
      XhrBone(0, 'R', root_pos, root_rot, root_rot, root_scale))

    # Group A
    file.seek(0xB0)
    start_index = 1
    self.parse_bone_group(file, start_index, group_a_count, 0x60, 'A')

    # Group B
    file.seek(group_b_offset)
    start_index += group_a_count
    self.parse_bone_group(file, start_index, group_b_count, 0x60, 'B')

    # Group C
    file.seek(group_c_offset)
    start_index += group_b_count
    self.parse_bone_group(file, start_index, group_c_count, 0x60, 'C')

    # Group D
    file.seek(group_d_offset)
    start_index += group_c_count
    self.parse_bone_group(file, start_index, group_d_count,
                          0x70, 'D', skip_first=0x8)

    # Group E (Physics bones)
    file.seek(group_e_offset)
    start_index += group_d_count
    self.parse_physics_bone_group(file, start_index, group_e_count, 'E')

  def parse_bone_group(self, file: readutil.BinaryFileReader, start_index: int, count: int, span: int, group: str, skip_first: int = 0) -> None:
    '''Parses bones in the given group. Ignores a lot of data in each group.'''
    for index in range(count):
      parent_index = file.read_int32()
      if parent_index < -1 or parent_index >= len(self.bones):
        raise ChrImportError(
            f'Unexpected parent index {parent_index} at offset {hex(file.tell() - 4)}')
      file.skip(skip_first)
      pos = file.read_nfloat32(3)
      rot = file.read_nfloat32(3)
      rot2 = file.read_nfloat32(3)
      scale = file.read_nfloat32(3)
      file.skip(span - 0x34 - skip_first)
      self.bones.append(
          XhrBone(index + start_index, group, pos, rot, rot2, scale, self.bones[parent_index]))

  def parse_physics_bone_group(self, file: readutil.BinaryFileReader, start_index: int, count: int, group: str) -> None:
    '''Parses physics bones in the given group. Ignores most of the physics data.'''
    for index in range(count):
      parent_index = file.read_int32()
      if parent_index < -1 or parent_index >= len(self.bones):
        raise ChrImportError(
            f'Unexpected parent index {parent_index} at offset {hex(file.tell() - 4)}')
      unk_counts = sum(file.skip(0x18).read_nuint32(3))
      pos = file.skip(0x8).read_nfloat32(4)[:3]
      rot = file.read_nfloat32(4)[:3]
      rot2 = file.read_nfloat32(4)[:3]
      scale = file.read_nfloat32(4)[:3]
      file.skip(0x60 + (unk_counts << 4))
      self.bones.append(
          XhrBone(index + start_index, group, pos, rot, rot2, scale, self.bones[parent_index]))


class TxyTexture:
  '''Container for a TXY texture.'''

  def __init__(self, file: readutil.BinaryFileReader):
    self.tbp0_offset = file.read_int32() + 0x3800
    self.psm = file.read_uint32()
    self.width = file.read_int32()
    self.height = file.read_int32()
    self.cbp_offset = file.skip(0x8).read_int32() + 0x3800
    self.name = file.skip(0x24).read_string(0x20)

  def get_lookup_key(self):
    '''Returns a lookup key identifying the texture.'''
    return (self.tbp0_offset, self.cbp_offset)


class TxyParser:
  '''Parser class for TXY file format (image data for textures).'''

  def __init__(self, basename: str):
    self.basename = basename
    # {(tbp0, cbp) -> TxyTexture}
    self.txy_texture_dict = {}
    self.gs_helper = gsutil.GSHelper()

  def parse(self, file: readutil.BinaryFileReader, offset: int) -> None:
    '''Parses the TXY at the given offset from an opened file.'''
    file.set_base_offset(offset)

    data_offset = file.seek(0x10).read_uint32()
    dma_count = file.seek(data_offset + 0x14).read_uint32()
    texture_count = file.read_uint32()
    file.skip(0x4)

    class DmaEntry:
      '''DMA table entry.'''

      def __init__(self, file: readutil.BinaryFileReader):
        self.data_offs = file.read_uint32()
        self.dbp = file.read_uint32() + 0x3800
        self.rrw = file.read_uint32()
        self.rrh = file.read_uint32()
        self.data_qwc = file.skip(0x4).read_uint32()
        file.skip(0x8)

    dma_entries = [DmaEntry(file) for _ in range(dma_count)]

    file.seek(0x1B0)
    for _ in range(texture_count):
      txy_texture = TxyTexture(file)
      texture_key = txy_texture.get_lookup_key()
      self.txy_texture_dict[texture_key] = txy_texture

    # Xenosaga III processes DMA entries in the TXY in reverse order, so we do the same here.
    for dma_entry in reversed(dma_entries):
      data = file.seek(dma_entry.data_offs +
                       0x20).read((dma_entry.data_qwc - 2) * 0x10)
      self.gs_helper.UploadPSMCT32(
        dbp=dma_entry.dbp, dbw=8, dsax=0, dsay=0, rrw=dma_entry.rrw, rrh=dma_entry.rrh, inbuf=data)

  def get_texture_name(self, tbp0: int, cbp: int) -> str:
    '''Returns the texture name for the given base pointers if one exists.'''
    texture_key = (tbp0, cbp)
    if texture_key in self.txy_texture_dict:
      return self.txy_texture_dict[texture_key].name
    return ''


class PxyMesh:
  '''Class for storing a PXY mesh descriptor.'''

  def __init__(self, name: str, bone_palette: 'list(int)'):
    self.name = name
    self.bone_palette = bone_palette


class PxyParser:
  '''Parser class for PXY file format (model).'''

  def __init__(self, basename: str, xhr: XhrParser, txy: TxyParser):
    self.basename = basename
    self.bone_matrices = []
    self.pxy_meshes = []
    self.objects = []
    self.xhr = xhr
    self.material_manager = MaterialManager(basename, txy)
    # self.armature = None

  def parse(self, file: readutil.BinaryFileReader, offset: int) -> None:
    '''Parses the PXY model at the given offset from an opened file.'''
    file.set_base_offset(offset)

    # bone_count = file.seek(0x5C).read_uint32()
    # bone_table_offset = file.seek(0x64).read_uint32()
    # self.parse_armature(file, bone_count, bone_table_offset)

    vif_desc_table_offset = file.seek(0x3C).read_uint32()
    draw_table_offset = file.seek(0x40).read_uint32()
    draw_count = file.seek(0x48).read_uint32()
    base_material_table_offset = file.seek(0x54).read_uint32()
    pxy_bone_count = file.seek(0x5C).read_uint32()
    mesh_count = file.seek(0x60).read_uint32()
    mesh_table_offset = file.seek(0x6C).read_uint32()

    non_alpha_count = self.parse_base_material_table(
      file, base_material_table_offset)
    self.parse_mesh_table(file, mesh_count, mesh_table_offset, pxy_bone_count)
    self.parse_draw_table(
      file, draw_count, draw_table_offset, vif_desc_table_offset, non_alpha_count)

  def parse_armature(self, file: readutil.BinaryFileReader,
                     bone_count: int, offset: int) -> None:
    '''Parses model global matrices.'''
    # Not sure what these are. They could be global inverse matrices for each
    # bone. Not useful since we can calculate these ourselves.
    # TODO: Remove?
    file.seek(offset)
    for _ in range(bone_count):
      self.bone_matrices.append(mathutils.Matrix(
          [file.read_nfloat32(4) for _ in range(4)]
      ).transposed())

  def parse_base_material_table(self, file: readutil.BinaryFileReader, base_material_table_offset: int) -> int:
    '''Parses the base material table for draw alpha count.'''
    file.seek(base_material_table_offset)
    for _ in range(2):
      material_name = file.read_string(0x10)
      if material_name[:9] == 'non-alpha':
        return file.skip(0x8).read_uint32()
      file.skip(0x10)
    return 0

  def parse_mesh_table(self, file: readutil.BinaryFileReader, mesh_count: int, offset: int, pxy_bone_count: int) -> None:
    '''Parses the mesh table.'''
    file.seek(offset)
    for _ in range(mesh_count):
      name = file.read_string(0x20)
      bone_palette = file.skip(0x10).read_nuint8(0x40)
      if pxy_bone_count < 0x41:  # This is a hard-coded condition in MIPS.
        # Every mesh uses the full set of bones in their palette.
        bone_palette = [i for i, _ in enumerate(self.xhr.bones)][2:]
      else:
        # Each mesh uses a subset of bones indexed by the palette below.
        bone_palette = [
          b + 1 for b in bone_palette[:bone_palette.index(0) + 1]]

      self.pxy_meshes.append(PxyMesh(name, bone_palette))

  def parse_draw_table(self, file: readutil.BinaryFileReader, draw_count: int, offset: int, vif_entry_table_offset: int, non_alpha_count: int) -> None:
    '''Parses the draw table and VIF packets for vertex data.'''
    file.seek(offset)

    draw_calls = []
    for _ in range(draw_count):
      vif_index = file.skip(0x4).read_uint16()
      mesh_index = file.skip(0xA).read_uint16()
      if mesh_index >= len(self.pxy_meshes):
        raise ChrImportError(
          f'Unexpected mesh index at offset {hex(file.tell() - 4)}')
      draw_calls.append((vif_index, mesh_index))
      file.skip(0x4E)

    vif_parser = vu.VifParser()
    for draw_index, (vif_index, mesh_index) in enumerate(draw_calls):
      pxy_mesh = self.pxy_meshes[mesh_index]
      bone_palette = [self.xhr.bones[i] for i in pxy_mesh.bone_palette]
      pxy_material = None

      file.seek(vif_entry_table_offset + vif_index * 0x20)
      vif_offs, vif_qwd = file.read_nuint32(2)

      vif_packet = file.seek(vif_offs).read(vif_qwd << 4)
      offs = 0
      while offs < len(vif_packet):
        last_offs = offs
        try:
          offs = vif_parser.parse_until_run_cmd(vif_packet, offs)
        except vu.VuParseError as err:
          raise ChrImportError(
            f'Failed to parse VU packet starting at {hex(file.base_offset + vif_offs)}:\n{err}')

        if (vif_parser.read_uint32(0x0, 0) & 0x8000) == 0:
          # GS registers and other setup.
          tex0_value = vif_parser.read_uint32(0x2, 0) | (
            vif_parser.read_uint32(0x2, 1) << 32)
          clamp_value = vif_parser.read_uint32(0x4, 0) | (
            vif_parser.read_uint32(0x4, 1) << 32)
          alpha = draw_index >= non_alpha_count
          pxy_material = self.material_manager.get_pxy_material(
            tex0_value, clamp_value, alpha)
        else:
          # Vertex data.
          vertex_count = vif_parser.read_uint32(0x0, 0) & 0x7FFF
          draw_flags = vif_parser.read_uint32(0x0, 3) & 0xFF
          packed_vertex_addr = 1
          vertex_color_addr = packed_vertex_addr + vertex_count * 2
          bone_weights_addr = vertex_color_addr + vertex_count * 2
          bone_offs_table_addr = bone_weights_addr + vertex_count
          packed_vertex = [vif_parser.read_float32_xyzw(
            packed_vertex_addr + i) for i in range(vertex_count * 2)]
          packed_vertex_int = [vif_parser.read_int32_xyzw(
            packed_vertex_addr + i) for i in range(vertex_count * 2)]
          if (draw_flags & 0x1) > 0:
            vertex_colors_int = [vif_parser.read_uint32_xyzw(
              vertex_color_addr + i) for i in range(vertex_count)]
            vertex_colors = [(c[0] / 0x80, c[1] / 0x80, c[2] /
                              0x80, c[3] / 0x80) for c in vertex_colors_int]
          else:
            vertex_colors = [(1.0, 1.0, 1.0, 1.0) for _ in range(vertex_count)]
          if (draw_flags & 0xC) > 0:
            bone_weights = [vif_parser.read_float32_xyzw(
              bone_weights_addr + i) for i in range(vertex_count)]
          else:
            bone_weights = [(1.0, 0.0, 0.0, 0.0) for _ in range(vertex_count)]
          bone_offs_table = [vif_parser.read_int32_xyzw(
            bone_offs_table_addr + i) for i in range(vertex_count)]

          vertices = [(v[0], v[1], v[2]) for v in packed_vertex[:vertex_count]]
          normals = [(v[0], v[1], v[2]) for v in packed_vertex[vertex_count:]]
          flags = [(v[3] & 0x1) for v in packed_vertex_int[vertex_count:]]
          tex_u = [
            v[3] * pxy_material.u_scale for v in packed_vertex[:vertex_count]]
          tex_v = [(1.0 - v[3]) *
                   pxy_material.v_scale for v in packed_vertex[vertex_count:]]
          # Correct UV offsets for compatibility with software that does not
          # use UV repeat by default.
          u_min = min(tex_u)
          v_min = min(tex_v)
          u_offs = u_min % 1.0 - u_min
          v_offs = v_min % 1.0 - v_min
          tex_coords = list(zip(
            [u + u_offs for u in tex_u], [v + v_offs for v in tex_v]
          ))

          triangles = []
          reverse = False
          for i, _ in enumerate(flags):
            if i > 1 and flags[i] == flags[i - 1]:
              if reverse:
                triangles.append((i, i - 1, i - 2))
              else:
                triangles.append((i - 2, i - 1, i))
              reverse = not reverse
            else:
              reverse = False

          vtx_group_dict = {}
          for v_index, (bone_offs_list, weights) in enumerate(zip(bone_offs_table, bone_weights)):
            for b_offs, weight in zip(bone_offs_list, weights):
              if b_offs >= 0xFF:
                continue
              # b_offs is an offset to the bone matrix in VU memory.
              palette_index = int(b_offs // 4)
              bone_index = bone_palette[palette_index].index
              if bone_index not in vtx_group_dict:
                vtx_group_dict[bone_index] = []
              vtx_group_dict[bone_index].append((v_index, weight))

          # Build Blender object
          last_offs_str = '{:08x}'.format(
            file.base_offset + vif_offs + last_offs)
          # object_name = f'{self.basename}_D_{draw_index}_M_{mesh_index}_V_{vif_index}_F_{last_offs_str}'
          object_name = f'{self.pxy_meshes[mesh_index].name}_{draw_index}_{last_offs_str}'
          mesh_data = bpy.data.meshes.new(f'{object_name}_mesh_data')
          mesh_data.from_pydata(vertices, [], triangles)
          mesh_data.update()

          mesh_data.uv_layers.new(do_init=False)
          mesh_data.uv_layers[-1].data.foreach_set('uv', [
              vt for pair in [tex_coords[loop.vertex_index] for loop in mesh_data.loops]
              for vt in pair
          ])

          mesh_data.vertex_colors.new(do_init=False)
          mesh_data.vertex_colors[-1].data.foreach_set('color', [
              rgba for col in [vertex_colors[loop.vertex_index] for loop in mesh_data.loops]
              for rgba in col
          ])

          obj = bpy.data.objects.new(object_name, mesh_data)
          if pxy_material:
            obj.data.materials.append(pxy_material.material)
          bpy.context.scene.collection.objects.link(obj)
          obj.select_set(state=True)
          self.objects.append(obj)

          # Normals should be set after creating the mesh object to prevent Blender from recalculating them.
          custom_vn = []
          for face in mesh_data.polygons:
            for vertex_index in face.vertices:
              custom_vn.append(normals[vertex_index])
            face.use_smooth = True
          mesh_data.use_auto_smooth = True
          mesh_data.normals_split_custom_set(custom_vn)

          for bone_index, v_list in sorted(vtx_group_dict.items()):
            group = obj.vertex_groups.new(name=self.xhr.bones[bone_index].name)
            for v_index, weight in v_list:
              group.add([v_index], weight, 'ADD')


class ChrParser:
  '''Parser class for CHR file format (archive).'''

  def __init__(self):
    self.basename = ''
    self.armature = None
    self.pxy = None
    self.xhr = None
    self.txy = None

  def parse(self, filepath: str) -> None:
    '''Parse the archive at the given filepath.'''
    self.basename = os.path.splitext(os.path.basename(filepath))[0]
    file = readutil.BinaryFileReader(filepath)

    # Parse files in the CHR header. Order matters.
    file_entry_map = self.read_file_entry_map(file)
    if 'xhr' in file_entry_map:
      self.parse_xhr(file, file_entry_map['xhr'].offset)
    if 'txy' in file_entry_map:
      self.parse_txy(file, file_entry_map['txy'].offset)
    if 'pxy' in file_entry_map:
      self.parse_pxy(file, file_entry_map['pxy'].offset)

    # Build the armature.
    self.build_armature()

    # Finalize the scene.
    if self.armature:
      self.armature.rotation_euler = (math.pi / 2, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

  @staticmethod
  def read_file_entry_map(
          file: readutil.BinaryFileReader) -> ('dict(FileEntry)'):
    '''Reads the file table as a map from filename to FileEntry.'''
    file_count = file.seek(0xC).read_uint16()
    file.skip(0x2)
    file_name_list = [file.read_string(4) for _ in range(file_count)]
    file.seek(0x40)
    file_entry_list = [file.read_nuint32(2) for _ in range(file_count)]

    file_entry_map = {}
    for name, (offset, size) in zip(file_name_list, file_entry_list):
      file_entry_map[name] = FileEntry(offset + 0x40, size)
    return file_entry_map

  def parse_xhr(self, file: readutil.BinaryFileReader, offset: int) -> None:
    '''Constructs an XHR parser to build the armature.'''
    self.xhr = XhrParser(self.basename)
    return self.xhr.parse(file, offset)

  def parse_txy(self, file: readutil.BinaryFileReader, offset: int) -> None:
    '''Constructs a TXY parser to process and store image data.'''
    self.txy = TxyParser(self.basename)
    return self.txy.parse(file, offset)

  def parse_pxy(self, file: readutil.BinaryFileReader, offset: int) -> None:
    '''Invokes a PXY parser to build the model.'''
    self.pxy = PxyParser(self.basename, self.xhr, self.txy)
    return self.pxy.parse(file, offset)

  def build_armature(self) -> None:
    '''Creates the model's armature in Blender.'''
    if not self.pxy or not self.xhr:
      return

    armature_data = bpy.data.armatures.new(f'{self.basename}_Armature')
    self.armature = bpy.data.objects.new(
        f'{self.basename}_Armature', armature_data)

    bpy.context.scene.collection.objects.link(self.armature)
    bpy.context.view_layer.objects.active = self.armature
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)

    b_bones = []  # List of bones in the Blender armature.
    for bone in self.xhr.bones:
      b_bone = armature_data.edit_bones.new(bone.name)
      b_bone.tail = (0.02, 0, 0)
      b_bone.use_inherit_rotation = True
      b_bone.use_local_location = True
      b_bone.matrix = bone.global_matrix
      if bone.parent:
        b_bone.parent = b_bones[bone.parent.index]
      b_bones.append(b_bone)

    # Attach all PXY objects to the armature.
    for obj in self.pxy.objects:
      obj.parent = self.armature
      modifier = obj.modifiers.new(type='ARMATURE', name='Armature')
      modifier.object = self.armature

    # Save all generated textures.
    bpy.ops.image.save_all_modified()

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)


def load(_, filepath: str) -> 'tuple(str, str)':
  '''Loads a CHR model into the current scene.'''
  try:
    parser = ChrParser()
    parser.parse(filepath)
  except (ChrImportError) as err:
    return 'CANCELLED', str(err)

  return 'FINISHED', ''
