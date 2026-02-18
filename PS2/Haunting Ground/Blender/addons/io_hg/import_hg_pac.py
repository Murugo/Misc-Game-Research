import bpy
import math
import os
import struct
import mathutils

from bpy_extras.wm_utils.progress_report import ProgressReport


class BinaryFileParser:
  def __init__(self, filepath):
    self.buf = open(filepath, 'rb').read()
  
  def getuint8(self, offs):
    return self.buf[offs]

  def getint32(self, offs):
    return struct.unpack('<i', self.buf[offs:offs+4])[0]

  def getuint32(self, offs):
    return struct.unpack('<I', self.buf[offs:offs+4])[0]

  def getint16(self, offs):
    return struct.unpack('<h', self.buf[offs:offs+2])[0]

  def getuint16(self, offs):
    return struct.unpack('<H', self.buf[offs:offs+2])[0]

  def getnuint32(self, offs, n):
    return struct.unpack('<' + 'I'*n, self.buf[offs:offs+4*n])
    
  def getfloat32(self, offs):
    return struct.unpack('<f', self.buf[offs:offs+4])[0]

  def getnfloat32(self, offs, n):
    return struct.unpack('<' + 'f'*n, self.buf[offs:offs+4*n])


def rhex(s):
  return hex(s)[2:]

def load(context, filepath):
  with ProgressReport(context.window_manager) as progress:
    progress.step('Importing PAC %r...' % filepath)

    basename = os.path.splitext(os.path.basename(filepath))[0]
    bfp = BinaryFileParser(filepath)

    geom_offs = bfp.getuint32(0xC)
    lights_offs = bfp.getuint32(0x10)
    camera_data_offs = bfp.getuint32(0x14)
    tex_offs = bfp.getuint32(0x24)

    progress.step('Building materials...')

    #TODO: Separate material list with blend enabled for translucent meshes
    materials = []
    texture_count = bfp.getuint32(tex_offs)
    for i in range(texture_count):
      offs = tex_offs + i * 0x10 + 0x10
      psm = bfp.getuint16(offs)
      width = bfp.getuint16(offs + 0x4)
      height = bfp.getuint16(offs + 0x6)
      dataoffs = tex_offs + bfp.getuint32(offs + 0xC) + (i + 1) * 0x10
      datasize = bfp.getuint16(offs + 0x8) * 0x10
      clutoffs = dataoffs + datasize
      print('{} {} {} {} {} {}'.format(psm, width, height, dataoffs, datasize, clutoffs))
      # clutsize = bfp.getuint16(offs + 0xA) * 0x10

      pixels = [0] * width * height * 4
      if psm == 0x13:
        for j in range(width * height):
          p = bfp.getuint8(dataoffs + j)
          # Flip bits 4 and 5
          p = ((p >> 1) & 0x8) | ((p << 1) & 0x10) | (p & 0xE7)
          col = bfp.getuint32(clutoffs + p * 4)
          # Blender flips images internally, hence we need to pre-flip the image
          # for the image to export correctly
          dstoffs = ((height - (j // width) - 1) * width + (j % width)) * 4
          pixels[dstoffs] = (col & 0xFF) / 0xFF
          pixels[dstoffs + 1] = ((col >> 8) & 0xFF) / 0xFF
          pixels[dstoffs + 2] = ((col >> 16) & 0xFF) / 0xFF
          pixels[dstoffs + 3] = ((col >> 24) & 0xFF) / 0x80
      else:
        raise Exception("PSM format %s not yet supported" % rhex(psm))

      image = bpy.data.images.new("%s_img_%s" % (basename, rhex(i)), width=width, height=height)
      image.pixels = pixels
      image.update()

      # texture = bpy.data.textures.new("%s_tex_%s" % (basename, rhex(i)), 'IMAGE')
      # texture.image = image

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
      
      materials.append(material)

    progress.step('Building objects...')

    # TODO: Parse other groups
    offs = geom_offs + bfp.getint32(geom_offs)
    end_offs = lights_offs if lights_offs > 0 else camera_data_offs
    while offs < end_offs:
      num_vertices = bfp.getint32(offs)
      if num_vertices <= 0:
        # break
        offs += 0x10
        continue

      name = '%s_%s' % (basename, rhex(offs))
      texture_index = bfp.getint32(offs + 0x4)

      # World matrix from transform
      transform = []
      for i in range(4):
        transform += [bfp.getnfloat32(offs + 0x10 + i * 0x10, 4)]
      world_matrix = mathutils.Matrix([transform[0], transform[1], transform[2], transform[3]])
      offs += 0x50
      
      # UVs
      vt = []
      for i in range(num_vertices):
        u = bfp.getfloat32(offs + i * 0x8)
        v = bfp.getfloat32(offs + i * 0x8 + 0x4)
        vt.append((u, 1 - v))
      offs += math.ceil(num_vertices * 0x8 / 0x10) * 0x10
      
      # Vertex colors
      vcol = []
      for i in range(num_vertices):
        r = bfp.getuint8(offs + i * 0x4) / 0x100
        g = bfp.getuint8(offs + i * 0x4 + 1) / 0x100
        b = bfp.getuint8(offs + i * 0x4 + 2) / 0x100
        a = bfp.getuint8(offs + i * 0x4 + 3) / 0x80
        vcol.append((r, g, b, a))
      offs += math.ceil(num_vertices * 0x4 / 0x10) * 0x10

      # Triangle strips
      vtx = []
      tri = []
      reverse = False
      for i in range(num_vertices):
        x, y, z = bfp.getnfloat32(offs + i * 0x10, 3)
        w = bfp.getint32(offs + i * 0x10 + 0xC)
        vtx.append((x, y, z))
        if w != 0x8000:
          if reverse:
            tri.append((i, i - 1, i - 2))
          else:
            tri.append((i - 2, i - 1, i))
          reverse = not reverse
        else:
          reverse = False
      offs += num_vertices * 0x10

      # Create new Blender object
      mesh_data = bpy.data.meshes.new('%s_mesh_data' % name)
      mesh_data.from_pydata(vtx, [], tri)
      mesh_data.update()

      mesh_data.uv_layers.new(do_init=False)
      mesh_data.uv_layers[-1].data.foreach_set("uv", [uv for pair in [vt[loop.vertex_index] for loop in mesh_data.loops] for uv in pair])

      mesh_data.vertex_colors.new()
      mesh_data.vertex_colors[-1].data.foreach_set("color", [rgba for col in [vcol[loop.vertex_index] for loop in mesh_data.loops] for rgba in col])

      obj = bpy.data.objects.new(name, mesh_data)
      obj.matrix_world = world_matrix
      if texture_index >= 0 and texture_index < len(materials):
        obj.data.materials.append(materials[texture_index])

      bpy.context.scene.collection.objects.link(obj)
      obj.select_set(state=True)

    progress.step('Done.')
    progress.step('Finished importing: %r' % filepath)

  return {'FINISHED'}


  # Example code for adding a mesh

  # verts = [(0,0,0),(0,5,0),(5,5,0),(5,0,0)]
  # faces = [(0,1,2,3)]
  
  # mesh_data = bpy.data.meshes.new("cube_mesh_data")
  # mesh_data.from_pydata(verts, [], faces)
  # mesh_data.update()

  # obj = bpy.data.objects.new("My_Object", mesh_data)

  # scene = bpy.context.scene
  # scene.collection.objects.link(obj)
  # obj.select_set(state=True)