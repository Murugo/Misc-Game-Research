import bpy
import math
import os
import struct
import mathutils

from bpy_extras.wm_utils.progress_report import ProgressReport

# TODO: Move these to importer params
MESH_SCALE = 8.0
POSE_SCALE = 128.0
ANIM_INDEX = 1


class BinaryFileParser:
  def __init__(self, filepath):
    self.buf = open(filepath, 'rb').read()
  
  def size(self):
    return len(self.buf)
  
  def getuint8(self, offs):
    return self.buf[offs]

  def getnuint8(self, offs, n):
    return self.buf[offs:offs+n]

  def getint32(self, offs):
    return struct.unpack('<i', self.buf[offs:offs+4])[0]

  def getnint32(self, offs, n):
    return struct.unpack('<' + 'i'*n, self.buf[offs:offs+4*n])

  def getuint32(self, offs):
    return struct.unpack('<I', self.buf[offs:offs+4])[0]

  def getint16(self, offs):
    return struct.unpack('<h', self.buf[offs:offs+2])[0]

  def getnint16(self, offs, n):
    return struct.unpack('<' + 'h'*n, self.buf[offs:offs+2*n])

  def getuint16(self, offs):
    return struct.unpack('<H', self.buf[offs:offs+2])[0]

  def getnuint16(self, offs, n):
    return struct.unpack('<' + 'H'*n, self.buf[offs:offs+2*n])

  def getnuint32(self, offs, n):
    return struct.unpack('<' + 'I'*n, self.buf[offs:offs+4*n])
    
  def getfloat32(self, offs):
    return struct.unpack('<f', self.buf[offs:offs+4])[0]

  def getnfloat32(self, offs, n):
    return struct.unpack('<' + 'f'*n, self.buf[offs:offs+4*n])


class Shape:
  def __init__(self, vertex_count, bfp, vtx_offs, uv_offs, vn_offs, ind_offs,
               islongind, vtxcenter = None, parent_bone_index = -1, bone_palette = [],
               bone_weight_offs = -1, bone_index_offs = -1, bones_per_vertex = -1):
    self._bfp = bfp
    self.vertex_count = vertex_count
    self.parent_bone_index = parent_bone_index
    self.bones_per_vertex = bones_per_vertex
    self.bone_palette = bone_palette
    if not vtxcenter:
      self.parse_vtx(vtx_offs)
    else:
      self.parse_vtx_with_center(vtx_offs, vtxcenter)
    self.parse_uv(uv_offs)
    self.parse_vn(vn_offs)
    self.parse_ind(ind_offs, islongind)
    if len(self.bone_palette) > 0:
      self.parse_bone_assignments(bone_weight_offs, bone_index_offs, bone_palette)
  
  def parse_vtx(self, offs):
    self.vtx = []
    x, y, z = [val / 0x8000 * MESH_SCALE for val in self._bfp.getnint32(offs, 3)]
    for i in range(self.vertex_count):
      x += self._bfp.getint16(offs + 0x10 + i * 0x6) / 0x8000 * MESH_SCALE
      y += self._bfp.getint16(offs + 0x12 + i * 0x6) / 0x8000 * MESH_SCALE
      z += self._bfp.getint16(offs + 0x14 + i * 0x6) / 0x8000 * MESH_SCALE
      self.vtx.append((x, y, z))
  
  def parse_vtx_with_center(self, offs, vtxcenter):
    self.vtx = []
    for i in range(self.vertex_count):
      x = (vtxcenter[0] + self._bfp.getint16(offs + i * 0x6) / 0x8000) * MESH_SCALE
      y = (vtxcenter[1] + self._bfp.getint16(offs + 0x2 + i * 0x6) / 0x8000) * MESH_SCALE
      z = (vtxcenter[2] + self._bfp.getint16(offs + 0x4 + i * 0x6) / 0x8000) * MESH_SCALE
      self.vtx.append((x, y, z))
  
  def parse_uv(self, offs):
    self.uv = []
    for i in range(self.vertex_count):
      u = self._bfp.getint16(offs + i * 0x4) / 0x8000
      v = 1 - self._bfp.getint16(offs + i * 0x4  + 0x2) / 0x8000
      self.uv.append((u, v))
  
  def parse_vn(self, offs):
    self.vn = []
    for i in range(self.vertex_count):
      x = self._bfp.getint16(offs + i * 0x6) / 0x8000
      y = self._bfp.getint16(offs + 0x2 + i * 0x6) / 0x8000
      z = self._bfp.getint16(offs + 0x4 + i * 0x6) / 0x8000
      self.vn.append((x, y, z))
  
  def parse_ind(self, offs, islongind):
    self.ind = []
    reverse = True
    first = False
    for i in range(self.vertex_count):
      flag =  self._bfp.getint32(offs + i * 4) if islongind else -self._bfp.getuint8(offs + i)
      if flag >= 0:
        if first:
          # Guess whether the vertex strip needs to be flipped by comparing the orientation of the triangle with the direction of two normals
          # (The vertex strip data does not tell us this because Haunting Ground renders backfaces)
          p1 = mathutils.Vector(self.vtx[i])
          p2 = mathutils.Vector(self.vtx[i - 1])
          p3 = mathutils.Vector(self.vtx[i - 2])
          px = (p2 - p1).cross(p3 - p1)
          n1 = mathutils.Vector(self.vn[i])
          n2 = mathutils.Vector(self.vn[i - 1])
          if n1.dot(px) < 0 or n2.dot(px) < 0:
            reverse = False
          first = False

        if reverse:
          self.ind.append((i, i - 1, i - 2))
        else:
          self.ind.append((i - 2, i - 1, i))
        reverse = not reverse
      else:
        first = True

  def parse_bone_assignments(self, bone_weight_offs, bone_index_offs, bone_palette):
    self.bone_weights = []
    for i in range(self.vertex_count):
      offs = bone_weight_offs + i * self.bones_per_vertex * 2
      weights = self._bfp.getnuint16(offs, self.bones_per_vertex)
      self.bone_weights.append([w / 0x8000 for w in weights])

    self.bone_ind = []
    for i in range(self.vertex_count):
      offs = bone_index_offs + i * self.bones_per_vertex
      indices = self._bfp.getnuint8(offs, self.bones_per_vertex)
      self.bone_ind.append([(x >> 2) for x in indices])

class Submesh:
  def __init__(self, bfp, offs, istypeb):
    vertex_count = bfp.getuint32(offs)
    
    vtx_offs = offs + bfp.getuint32(offs + 0x4)
    uv_offs = offs + bfp.getuint32(offs + 0x8)
    vn_offs = offs + bfp.getuint32(offs + 0xC)
    
    if istypeb:  # Static mesh
      ind_offs = offs + bfp.getuint32(offs + 0x10)
      self.mat_index = bfp.getuint32(offs + 0x14)
      parent_bone_index = bfp.getuint32(offs + 0x1C)
      shape = Shape(
          vertex_count, bfp, vtx_offs, uv_offs, vn_offs, ind_offs,
          islongind=False, parent_bone_index=parent_bone_index)
    else:  # Skinned mesh
      bone_weight_offs = offs + bfp.getuint32(offs + 0x10)
      bone_index_offs = offs + bfp.getuint32(offs + 0x14)
      ind_offs = offs + bfp.getuint32(offs + 0x18)
      bone_palette_count = bfp.getuint32(offs + 0x24)
      bone_palette_offs = offs + bfp.getuint32(offs + 0x28)
      bone_palette = [x for x in bfp.getnuint8(bone_palette_offs, bone_palette_count)]
      bones_per_vertex = bfp.getuint32(offs + 0x2C)
      self.mat_index = bfp.getuint32(offs + 0x1C)
      shape = Shape(
          vertex_count, bfp, vtx_offs, uv_offs, vn_offs, ind_offs,
          islongind=False, bone_weight_offs=bone_weight_offs,
          bone_index_offs=bone_index_offs, bone_palette=bone_palette,
          bones_per_vertex=bones_per_vertex)
    self.shapes = [shape]


class Mesh:
  def __init__(self, index, bfp, offs, istypeb):
    self.index = index
    self.submeshes = []
    self.submesh_count = bfp.getuint32(offs)
    submesh_header_size = 0x20 if istypeb else 0x30
    for i in range(self.submesh_count):
      self.submeshes.append(Submesh(bfp, offs + i * submesh_header_size + 0x10, istypeb))


class BlendSubmesh:
  def __init__(self, bfp, offs):
    self.mat_index = bfp.getuint32(offs + 0x18)
    vertex_count = bfp.getuint32(offs + 0x4)
    blendshape_count = bfp.getuint32(offs)
    blendshape_table_offs = offs + bfp.getuint32(offs + 0x10)
    vtxcenter = [val / 0x8000 for val in bfp.getnint32(offs + 0x30, 3)]

    uv_offs = offs + bfp.getuint32(offs + 0x8)
    ind_offs = offs + bfp.getuint32(offs + 0xC)
    parent_bone_index = bfp.getuint32(offs + 0x14)
    islongind = bfp.getuint32(offs + 0x1C) == 1

    self.shapes = []
    for i in range(blendshape_count):
      vtx_offs = blendshape_table_offs + i * 0x8 + bfp.getuint32(blendshape_table_offs + i * 0x8)
      vn_offs = blendshape_table_offs + i * 0x8 + bfp.getuint32(blendshape_table_offs + i * 0x8 + 0x4)

      shape = Shape(vertex_count, bfp, vtx_offs, uv_offs, vn_offs, ind_offs, islongind, vtxcenter, parent_bone_index=parent_bone_index)
      self.shapes.append(shape)


class BlendMesh:
  def __init__(self, index, bfp, offs):
    self.index = index
    self.submeshes = []
    self.submesh_count = bfp.getuint32(offs)
    for i in range(self.submesh_count):
      self.submeshes.append(BlendSubmesh(bfp, offs + i * 0x40 + 0x10))


def rhex(s):
  return hex(s)[2:]

def load(context, filepath):
  with ProgressReport(context.window_manager) as progress:
    progress.step('Importing PCK %r...' % filepath)

    basename = os.path.splitext(os.path.basename(filepath))[0]
    bfp = BinaryFileParser(filepath)

    progress.step('Building materials...')

    model_offs = bfp.getuint32(0x4)

    #TODO: Separate material list with blend enabled for translucent meshes?
    materials = []
    mat_bfp = BinaryFileParser(os.path.splitext(filepath)[0] + '.TEX')
    if mat_bfp.size() > 0:

      texture_count = mat_bfp.getuint32(0x0)
      for i in range(texture_count):
        offs = i * 0x10 + 0x10
        psm = mat_bfp.getuint16(offs)
        width = mat_bfp.getuint16(offs + 0x4)
        height = mat_bfp.getuint16(offs + 0x6)
        dataoffs = mat_bfp.getuint32(offs + 0xC) + (i + 1) * 0x10
        datasize = mat_bfp.getuint16(offs + 0x8) * 0x10
        clutoffs = dataoffs + datasize
        print('{} {} {} {} {} {}'.format(psm, width, height, dataoffs, datasize, clutoffs))
        # clutsize = bfp.getuint16(offs + 0xA) * 0x10

        pixels = [0] * width * height * 4
        if psm == 0x13:
          for j in range(width * height):
            p = mat_bfp.getuint8(dataoffs + j)
            # Flip bits 4 and 5
            p = ((p >> 1) & 0x8) | ((p << 1) & 0x10) | (p & 0xE7)
            col = mat_bfp.getuint32(clutoffs + p * 4)
            # Blender flips images internally, hence we need to pre-flip the image
            # for the image to export correctly
            dstoffs = ((height - (j // width) - 1) * width + (j % width)) * 4
            pixels[dstoffs] = (col & 0xFF) / 0xFF
            pixels[dstoffs + 1] = ((col >> 8) & 0xFF) / 0xFF
            pixels[dstoffs + 2] = ((col >> 16) & 0xFF) / 0xFF
            pixels[dstoffs + 3] = ((col >> 24) & 0xFF) / 0x80
        else:
          raise Exception("PSM format %s not yet supported" % rhex(psm))

        image = bpy.data.images.new("%s_img_%s" % (basename, rhex(i)), width=width, height=height, alpha=True)
        image.pixels = pixels
        image.update()

        material = bpy.data.materials.new(name="%s_mat_%s" % (basename, rhex(i)))
        # material.texture_slots.add().texture = texture
        material.use_nodes = True

        tex_node = material.node_tree.nodes.new('ShaderNodeTexImage')
        tex_node.image = image

        bsdf = material.node_tree.nodes['Principled BSDF']
        if 'Specular' in bsdf.inputs:
          bsdf.inputs['Specular'].default_value = 0
        elif 'Specular IOR Level' in bsdf.inputs:
          bsdf.inputs['Specular IOR Level'].default_value = 0
        material.node_tree.links.new(bsdf.inputs['Base Color'], tex_node.outputs['Color'])
        material.node_tree.links.new(bsdf.inputs['Alpha'], tex_node.outputs['Alpha'])
        
        materials.append(material)

    if materials:
      bpy.ops.image.save_all_modified()

    progress.step('Building mesh...')

    # Parse mesh

    model_offs = bfp.getuint32(0x4)
    meshes = []

    for i in range(2):
      mesh_offs = bfp.getuint32(model_offs + 0x4 + i * 0x4)
      if mesh_offs == 0:
        continue
      meshes.append(Mesh(i, bfp, model_offs + mesh_offs, i > 0))

    blend_submesh_count = 0
    blendshape_mesh_offs = bfp.getuint32(0x8)
    if blendshape_mesh_offs > 0:
      meshes.append(BlendMesh(2, bfp, blendshape_mesh_offs))
      blend_submesh_count = meshes[-1].submesh_count
    
    print('Number of submeshes: {}'.format(blend_submesh_count))

    objects = []
    for mesh_index, mesh in enumerate(meshes):
      for submesh_index, submesh in enumerate(mesh.submeshes):
        if len(submesh.shapes) == 0:
          continue
        shape = submesh.shapes[0]

        mesh_data = bpy.data.meshes.new('%s_mesh_data' % basename)
        mesh_data.from_pydata(shape.vtx, [], shape.ind)
        mesh_data.update()

        mesh_data.uv_layers.new(do_init=False)
        mesh_data.uv_layers[-1].data.foreach_set("uv", [uv for pair in [shape.uv[loop.vertex_index] for loop in mesh_data.loops] for uv in pair])

        # mesh_data.vertex_colors.new()
        # mesh_data.vertex_colors[-1].data.foreach_set("color", [rgba for col in [mesh.vcol[loop.vertex_index] for loop in mesh_data.loops] for rgba in col])

        obj = bpy.data.objects.new("%s_mesh_%d_%d" % (basename, mesh_index, submesh_index), mesh_data)
        if submesh.mat_index >= 0 and submesh.mat_index < len(materials):
          obj.data.materials.append(materials[submesh.mat_index])

        bpy.context.scene.collection.objects.link(obj)
        objects.append(obj)

        # Apply blendshapes
        if len(submesh.shapes) > 1:
          shape_key = obj.shape_key_add(name='Basis')
          shape_key.interpolation = 'KEY_LINEAR'
          obj.data.shape_keys.use_relative = True
        for shape_index, blendshape in enumerate(submesh.shapes[1:]):
          shape_key = obj.shape_key_add(name='ShapeKey_%d' % shape_index)
          shape_key.interpolation = 'KEY_LINEAR'
          for i in range(blendshape.vertex_count):
            shape_key.data[i].co = blendshape.vtx[i]

        # Normals should be set after creating the mesh object to prevent Blender from recalculating them.
        vn = []
        for face in mesh_data.polygons:
          for vertex_index in face.vertices:
            vn.append(shape.vn[vertex_index])
          face.use_smooth = True
        if hasattr(mesh_data, 'use_auto_smooth'):
          mesh_data.use_auto_smooth = True
        mesh_data.normals_split_custom_set(vn)

        # Create vertex groups for bone assignments
        if shape.parent_bone_index >= 0:
          group = obj.vertex_groups.new(name='Bone_%d' % shape.parent_bone_index)
          for i in range(shape.vertex_count):
            group.add([i], 1.0, "ADD")
        elif len(shape.bone_palette) > 0:
          groups = []
          for bone_index in shape.bone_palette:
            groups.append(obj.vertex_groups.new(name='Bone_%d' % bone_index))
          for i in range(shape.vertex_count):
            for j in range(shape.bones_per_vertex):
              palette_index = shape.bone_ind[i][j]
              weight = shape.bone_weights[i][j]
              groups[palette_index].add([i], weight, "ADD")

    progress.step('Building armature...')

    # Parse armature

    bone_local_matrices = []
    # bone_parent_indices = []
    # bone_local_euler = []

    bone_count = bfp.getuint32(model_offs)
    bone_table_offs = model_offs + 0x10

    if bone_count > 0:
      armature_data = bpy.data.armatures.new('%s_Armature' % basename)
      armature = bpy.data.objects.new("%s_Armature" % basename, armature_data)

      bpy.context.scene.collection.objects.link(armature)
      bpy.context.view_layer.objects.active = armature
      bpy.ops.object.mode_set(mode='EDIT', toggle=False)

      for i in range(bone_count):
        offs = bone_table_offs + i * 0x70
        parent_bone_index = bfp.getint32(offs)

        local_rotation = bfp.getnfloat32(offs + 0x10, 3)
        local_euler = mathutils.Euler((local_rotation[0], local_rotation[1], local_rotation[2]))
        # bone_local_euler.append(local_euler)
        # print('Bone euler: {}'.format(local_euler))

        local_translate = mathutils.Vector(bfp.getnfloat32(offs + 0x20, 3))
        # print('Bone translate: {}'.format(local_translate))

        rotation_matrix = local_euler.to_matrix()
        rotation_matrix.resize_4x4()
        translate_matrix = mathutils.Matrix()
        translate_matrix[0][3] = local_translate[0]
        translate_matrix[1][3] = local_translate[1]
        translate_matrix[2][3] = local_translate[2]

        local_matrix = translate_matrix @ rotation_matrix
        bone_local_matrices.append(local_matrix)

        if parent_bone_index >= 0:
          global_matrix = armature_data.edit_bones[parent_bone_index].matrix @ local_matrix
        else:
          global_matrix = local_matrix
        
        # print('Bone global matrix:\n{}'.format(global_matrix))
        
        bone = armature_data.edit_bones.new('Bone_%d' % i)

        bone.tail = (0, 0.5, 0)
        bone.use_inherit_rotation = True
        bone.use_local_location = True

        bone.matrix = global_matrix
        # bone.transform(global_matrix, roll=False)

        if parent_bone_index >= 0:
          bone.parent = armature_data.edit_bones[parent_bone_index]

      for obj in objects:
        obj.parent = armature
        modifier = obj.modifiers.new(type='ARMATURE', name='Armature')
        modifier.object = armature
        obj.select_set(state=True)
      
      armature.rotation_euler = (math.pi / 2, 0, 0)
      bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    
    progress.step('Building animation...')

    # Parse a single animation

    anim_offs = bfp.getuint32(0x10)
    anim_count = bfp.getuint32(anim_offs) if anim_offs > 0 else 0
    if armature and anim_count > 0:
      bone_palette_table_offs = model_offs + bfp.getuint32(model_offs + 0xC)
      bone_palette_count = bfp.getuint8(bone_palette_table_offs)
      bone_palette = bfp.getnuint8(bone_palette_table_offs + 0x1, bone_palette_count)

      armature.animation_data_create()
      action = armature.animation_data.action = bpy.data.actions.new(name="ArmatureAction")

      shape_key_actions = []
      for i in range(blend_submesh_count):
        shape_key_anim_data = bpy.data.objects["%s_mesh_2_%d" % (basename, i)].data.shape_keys.animation_data_create()
        if i < 3:
          shape_key_action = shape_key_anim_data.action = bpy.data.actions.new("ShapeKeys%dAction" % i)
          shape_key_actions.append(shape_key_action)
        else:
          # Same blend shape controls face + teeth/eyelashes (for all (?) human characters)
          shape_key_anim_data.action = shape_key_actions[0]

      def create_fcurve_rot(bone_name):
        return [action.fcurves.new("pose.bones[\"%s\"].rotation_euler" % bone_name, index=i) for i in range(3)]
      
      def create_fcurve_pos(bone_name):
        return [action.fcurves.new("pose.bones[\"%s\"].location" % bone_name, index=i) for i in range(3)]

      offs = anim_offs + 0x10 + ANIM_INDEX * 0x14
      metadata_header_offs = offs + bfp.getuint32(offs)
      pose_header_offs = offs + bfp.getuint32(offs + 0x4)
      # TODO: Hewie has 3 additional pose headers: one for the ears, one for the tail, and one for the mouth + tongue.
      # This should be refactored into a single function which handles both metadata and pose frames.

      def parse_animation(header_offs):
        bone_count = bfp.getuint32(header_offs)
        frame_count = bfp.getuint32(header_offs + 0x4)
        pose_table_offs = header_offs + bfp.getuint32(header_offs + 0x8)

        bpy.context.scene.frame_end = frame_count

        # TODO: To animate blendshapes:
        # bpy.data.objects['FIN_000_mesh_2_0'].data.shape_keys.animation_data_create()
        # action = bpy.data.objects['FIN_000_mesh_2_0'].data.shape_keys.animation_data.action = bpy.data.actions.new("ShapeKeys0Action")
        # fcurve = action.fcurves.new("key_blocks[\"ShapeKey_0\"].value")
        # fcurve = action.fcurves.new("key_blocks[\"Shape_key_1\"].value")
        # ...
        # fcurve.keyframe_points[0].co = time, val

        for bone_index in range(bone_count):
          offs = pose_table_offs + bone_index * 0xC
          bone_palette_index = bfp.getint32(offs)
          if bone_palette_index < 0:
            # Metadata
            flags = bfp.getuint32(offs + 0x4)
            if (flags & 0x10000) > 0:
              # TODO: Interleaved?
              continue
            fdata_offs = offs + bfp.getuint32(offs + 0x8)

            effective_frame_count = frame_count if (flags & 0x10000) == 0 else 1

            # Face control
            # TODO: Refactor duplicated code
            if bone_palette_index == -0x7 and flags == 0x3:
              fcurves = [shape_key_actions[0].fcurves.new("key_blocks[\"ShapeKey_%d\"].value" % i) for i in range(0, 3)]
              for fcurve in fcurves:
                fcurve.keyframe_points.add(effective_frame_count)
                for i in range(effective_frame_count):
                  fcurve.keyframe_points[i].interpolation = 'LINEAR'
              for i in range(effective_frame_count):
                values = [v / 0x8000 for v in bfp.getnint16(fdata_offs + i * 0x8, 4)]
                fcurves[0].keyframe_points[i].co = i + 1, values[1]
                fcurves[1].keyframe_points[i].co = i + 1, values[2]
                fcurves[2].keyframe_points[i].co = i + 1, values[3]
            elif bone_palette_index == -0x8 and flags == 0x3:
              fcurves = [shape_key_actions[0].fcurves.new("key_blocks[\"ShapeKey_%d\"].value" % i) for i in range(3, 7)]
              for fcurve in fcurves:
                fcurve.keyframe_points.add(effective_frame_count)
                for i in range(effective_frame_count):
                  fcurve.keyframe_points[i].interpolation = 'LINEAR'
              for i in range(effective_frame_count):
                values = [v / 0x8000 for v in bfp.getnint16(fdata_offs + i * 0x8, 4)]
                fcurves[0].keyframe_points[i].co = i + 1, values[0]
                fcurves[1].keyframe_points[i].co = i + 1, values[1]
                fcurves[2].keyframe_points[i].co = i + 1, values[2]
                fcurves[3].keyframe_points[i].co = i + 1, values[3]
            elif bone_palette_index == -0x9 and flags == 0x3:
              fcurves = [shape_key_actions[0].fcurves.new("key_blocks[\"ShapeKey_%d\"].value" % i) for i in range(7, 11)]
              for fcurve in fcurves:
                fcurve.keyframe_points.add(effective_frame_count)
                for i in range(effective_frame_count):
                  fcurve.keyframe_points[i].interpolation = 'LINEAR'
              for i in range(effective_frame_count):
                values = [v / 0x8000 for v in bfp.getnint16(fdata_offs + i * 0x8, 4)]
                fcurves[0].keyframe_points[i].co = i + 1, values[0]
                fcurves[1].keyframe_points[i].co = i + 1, values[1]
                fcurves[2].keyframe_points[i].co = i + 1, values[2]
                fcurves[3].keyframe_points[i].co = i + 1, values[3]
            elif bone_palette_index == -0xA and flags == 0x3:
              fcurves = [shape_key_actions[0].fcurves.new("key_blocks[\"ShapeKey_%d\"].value" % i) for i in range(11, 15)]
              for fcurve in fcurves:
                fcurve.keyframe_points.add(effective_frame_count)
                for i in range(effective_frame_count):
                  fcurve.keyframe_points[i].interpolation = 'LINEAR'
              for i in range(effective_frame_count):
                values = [v / 0x8000 for v in bfp.getnint16(fdata_offs + i * 0x8, 4)]
                fcurves[0].keyframe_points[i].co = i + 1, values[0]
                fcurves[1].keyframe_points[i].co = i + 1, values[1]
                fcurves[2].keyframe_points[i].co = i + 1, values[2]
                fcurves[3].keyframe_points[i].co = i + 1, values[3]

            # Hand control
            # TODO: Refactor duplicated code
            elif bone_palette_index == -0xB:
              fcurves = [shape_key_actions[1].fcurves.new("key_blocks[\"ShapeKey_%d\"].value" % i) for i in range(9)]
              for fcurve in fcurves:
                # TODO: Frames not needed when other 7 shapes are not being keyed
                fcurve.keyframe_points.add(effective_frame_count)
                for i in range(effective_frame_count):
                  fcurve.keyframe_points[i].interpolation = 'LINEAR'
              for i in range(effective_frame_count):
                shape_base, shape, weight = bfp.getnint16(fdata_offs + i * 0x6, 3)
                weight /= 0x8000
                weight_base = 1.0 - weight
                if shape_base > 0:
                  fcurves[shape_base - 1].keyframe_points.add(1)
                  fcurves[shape_base - 1].keyframe_points[-1].interpolation = 'LINEAR'
                  fcurves[shape_base - 1].keyframe_points[-1].co = i + 1, weight_base
                if shape > 0 and shape != shape_base:
                  fcurves[shape - 1].keyframe_points.add(1)
                  fcurves[shape - 1].keyframe_points[-1].interpolation = 'LINEAR'
                  fcurves[shape - 1].keyframe_points[-1].co = i + 1, weight
            elif bone_palette_index == -0xC:
              fcurves = [shape_key_actions[2].fcurves.new("key_blocks[\"ShapeKey_%d\"].value" % i) for i in range(9)]
              for fcurve in fcurves:
                # TODO: Frames not needed when other 7 shapes are not being keyed
                fcurve.keyframe_points.add(effective_frame_count)
                for i in range(effective_frame_count):
                  fcurve.keyframe_points[i].interpolation = 'LINEAR'
              for i in range(effective_frame_count):
                shape_base, shape, weight = bfp.getnint16(fdata_offs + i * 0x6, 3)
                weight /= 0x8000
                weight_base = 1.0 - weight
                if shape_base > 0:
                  fcurves[shape_base - 1].keyframe_points.add(1)
                  fcurves[shape_base - 1].keyframe_points[-1].interpolation = 'LINEAR'
                  fcurves[shape_base - 1].keyframe_points[-1].co = i + 1, weight_base
                if shape > 0 and shape != shape_base:
                  fcurves[shape - 1].keyframe_points.add(1)
                  fcurves[shape - 1].keyframe_points[-1].interpolation = 'LINEAR'
                  fcurves[shape - 1].keyframe_points[-1].co = i + 1, weight

            continue
          
          bone_global_index = bone_palette[bone_palette_index]
          bone_name = 'Bone_%d' % bone_global_index

          bone_matrix_inv = bone_local_matrices[bone_global_index].copy()
          bone_matrix_inv.invert()
          # print('Inverted bone matrix:\n{}'.format(bone_matrix))

          # euler = bone_local_euler[bone_global_index]

          flags = bfp.getuint32(offs + 0x4)
          fdata_offs = offs + bfp.getuint32(offs + 0x8)

          # print('Bone rotation: {} {} {}'.format(math.degrees(euler.x), math.degrees(euler.y), math.degrees(euler.z)))
          armature.pose.bones[bone_name].rotation_mode = 'XYZ'

          effective_frame_count = frame_count if (flags & 0x10000) == 0 else 1

          if (flags & 0xFF) == 0x2:  # Rotation + Position
            fcurves = create_fcurve_rot(bone_name) + create_fcurve_pos(bone_name)
            for fcurve in fcurves:
              fcurve.keyframe_points.add(effective_frame_count)
              for i in range(effective_frame_count):
                fcurve.keyframe_points[i].interpolation = 'LINEAR'
            for i in range(effective_frame_count):
              rx = bfp.getint16(fdata_offs + i * 0xC) / 0x8000 * math.pi
              ry = bfp.getint16(fdata_offs + i * 0xC + 0x2) / 0x8000 * math.pi
              rz = bfp.getint16(fdata_offs + i * 0xC + 0x4) / 0x8000 * math.pi
              px = bfp.getint16(fdata_offs + i * 0xC + 0x6) / 0x8000 * POSE_SCALE
              py = bfp.getint16(fdata_offs + i * 0xC + 0x8) / 0x8000 * POSE_SCALE
              pz = bfp.getint16(fdata_offs + i * 0xC + 0xA) / 0x8000 * POSE_SCALE

              rotation_matrix = mathutils.Euler([rx, ry, rz]).to_matrix()
              rotation_matrix.resize_4x4()
              translation_matrix = mathutils.Matrix()
              translation_matrix[0][3] = px
              translation_matrix[1][3] = py
              translation_matrix[2][3] = pz

              if i == 1:
                print('\nPR Frame 0 (Bone {})):'.format(bone_global_index))
                print('Rotate: {} {} {} -> {} {} {}'.format(
                  math.degrees(rx), math.degrees(ry), math.degrees(rz),
                  math.degrees(eul[0]), math.degrees(eul[1]), math.degrees(eul[2]),
                ))
                print('Locate: {} {} {} -> {} {} {}'.format(
                  px, py, pz, mat[0][3], mat[1][3], mat[2][3]
                ))

              mat = bone_matrix_inv @ translation_matrix @ rotation_matrix
              eul = mat.to_euler()
              fcurves[0].keyframe_points[i].co = i + 1, eul[0]
              fcurves[1].keyframe_points[i].co = i + 1, eul[1]
              fcurves[2].keyframe_points[i].co = i + 1, eul[2]
              fcurves[3].keyframe_points[i].co = i + 1, mat[0][3]
              fcurves[4].keyframe_points[i].co = i + 1, mat[1][3]
              fcurves[5].keyframe_points[i].co = i + 1, mat[2][3]

          elif (flags & 0xFF) == 7:  # Rotation + Position (f)
            fcurves = create_fcurve_rot(bone_name) + create_fcurve_pos(bone_name)
            for fcurve in fcurves:
              fcurve.keyframe_points.add(effective_frame_count)
              for i in range(effective_frame_count):
                fcurve.keyframe_points[i].interpolation = 'LINEAR'
            for i in range(effective_frame_count):
              rx = bfp.getfloat32(fdata_offs + i * 0x18)
              ry = bfp.getfloat32(fdata_offs + i * 0x18 + 0x4)
              rz = bfp.getfloat32(fdata_offs + i * 0x18 + 0x8)
              px = bfp.getfloat32(fdata_offs + i * 0x18 + 0xC)
              py = bfp.getfloat32(fdata_offs + i * 0x18 + 0x10)
              pz = bfp.getfloat32(fdata_offs + i * 0x18 + 0x14)

              rotation_matrix = mathutils.Euler([rx, ry, rz]).to_matrix()
              rotation_matrix.resize_4x4()
              translation_matrix = mathutils.Matrix()
              translation_matrix[0][3] = px
              translation_matrix[1][3] = py
              translation_matrix[2][3] = pz

              mat = bone_matrix_inv @ translation_matrix @ rotation_matrix
              eul = mat.to_euler()
              fcurves[0].keyframe_points[i].co = i + 1, eul[0]
              fcurves[1].keyframe_points[i].co = i + 1, eul[1]
              fcurves[2].keyframe_points[i].co = i + 1, eul[2]
              fcurves[3].keyframe_points[i].co = i + 1, mat[0][3]
              fcurves[4].keyframe_points[i].co = i + 1, mat[1][3]
              fcurves[5].keyframe_points[i].co = i + 1, mat[2][3]
          
          elif (flags & 0xFF) == 0:  # Rotation
            fcurves = create_fcurve_rot(bone_name)
            for fcurve in fcurves:
              fcurve.keyframe_points.add(effective_frame_count)
              for i in range(effective_frame_count):
                fcurve.keyframe_points[i].interpolation = 'LINEAR'
            for i in range(effective_frame_count):
              rx = bfp.getint16(fdata_offs + i * 0x6) / 0x8000 * math.pi
              ry = bfp.getint16(fdata_offs + i * 0x6 + 0x2) / 0x8000 * math.pi
              rz = bfp.getint16(fdata_offs + i * 0x6 + 0x4) / 0x8000 * math.pi

              rotation_matrix = mathutils.Euler([rx, ry, rz]).to_matrix()
              rotation_matrix.resize_4x4()
              eul = (bone_matrix_inv @ rotation_matrix).to_euler()

              fcurves[0].keyframe_points[i].co = i + 1, eul[0]
              fcurves[1].keyframe_points[i].co = i + 1, eul[1]
              fcurves[2].keyframe_points[i].co = i + 1, eul[2]
      
      parse_animation(metadata_header_offs)
      parse_animation(pose_header_offs)

    progress.step('Done.')
    progress.step('Finished importing: %r' % filepath)

  return {'FINISHED'}
