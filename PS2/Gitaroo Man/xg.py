''' Converts a Gitaroo Man .XG model file to .OBJ or .FBX. '''

import ctypes
import os
import struct
import sys
import FbxCommon
from fbx import *

EXPORT_OBJ = False
EXPORT_FBX = True
USE_FBX_BINARY_FORMAT = True
EXPORT_ANIMATION = True
EXPORT_NORMALS = False  # Currently broken.
DEBUG_PRINT_DAG = False

# Constants
FRAMES_PER_SECOND = 60.
PLAYBACK_SPEED = 1./8.


def error(message):
  print('ERROR:', message)
  sys.exit(1)


class BinaryFileReader:
  def __init__(self, filename):
    self.f = open(filename, 'rb')
    
  def getbyte(self):
    b = self.f.read(1)
    if b:
      return struct.unpack('<B', b)[0]
    
  def getshort(self):
    return struct.unpack('<H', self.f.read(2))[0]
    
  def getint(self):
    return struct.unpack('<I', self.f.read(4))[0]
    
  def getsignedint(self):
    return struct.unpack('<i', self.f.read(4))[0]
    
  def getfloat(self):
    return struct.unpack('<f', self.f.read(4))[0]
    
  def getsignedshort(self):
    return struct.unpack('<h', self.f.read(2))[0]
    
  def getblock(self, len, func):
    b = []
    for i in range(len):
      b += [func()]
    return b
    
  def getstringb(self):
    len = self.getbyte()
    if len:
      return self.f.read(len).decode('cp932')
  
  def read(self, n):
    return self.f.read(n)
  
  def seek(self, n):
    self.f.seek(n)
    
  def tell(self):
    return self.f.tell()
  
  def skip(self, n):
    self.f.seek(self.f.tell() + n)
    
  def close(self):
    self.f.close()


def parse_data_vertices(f):
  type = f.getint()
  len = f.getint()
  blocks = []
  if type == 1:
    bsize = 4   # X,Y,Z,W
  elif type == 3:
    bsize = 7   # X,Y,Z,W, NX,NY,NZ
  elif type == 7:
    bsize = 11  # X,Y,Z,W, NX,NY,NZ, X2,Y2,Z2,W2
  elif type == 11:
    bsize = 9   # X,Y,Z,W, NX,NY,NZ, U,V
  elif type == 15:
    bsize = 13  # X,Y,Z,W, NX,NY,NZ, X2,Y2,Z2,W2, U,V
  
  for i in range(len):
    b = []
    for j in range(bsize):
      b += [f.getfloat()]
    blocks += [b]
  
  return [type, len, blocks]

def parse_data_vertex_targets(f):
  len = f.getint()
  blocks = []
  curblock = []
  for i in range(len):
    val = f.getsignedint()
    if val >= 0:
      curblock += [val]
    else:
      blocks += [curblock]
      curblock = []
  return blocks
  
def parse_data_keys(f):
  # It's suspected that the size of this block is dependent on the model entry in the .XGM file.
  # For now just seek to the end of the data field by finding the next valid tag.
  tag = f.read(4)
  while tag != b"\x09inp" and tag != b"\x07tar":
    tag = f.read(4)  # Skip floats
  f.seek(f.tell() - 4)
  return []


obj_defs = {
  # Object Type
  "xgDagMesh": {
    # Parameters
    "primType":          ["int"],
    "primCount":         ["int"],
    "primData":          ["int"],
    "triFanCount":       ["int"],
    "triFanData":        ["len", ["int"]],
    "triStripCount":     ["int"],
    "triStripData":      ["len", ["int"]],
    "triListCount":      ["int"],
    "triListData":       ["len", ["int"]],
    "cullFunc":          ["int"],
    "inputGeometry":     ["str"],
    "outputGeometry":    ["str"],
    "inputMaterial":     ["str"],
    "outputMaterial":    ["str"]
  },
  "xgBgGeometry": {
    "density":           ["float"],
    "vertices":          [parse_data_vertices],
    "inputGeometry":     ["str"],
    "outputGeometry":    ["str"]
  },
  "xgEnvelope": {
    "startVertex":       ["int"],
    "weights":           ["len", [4,"float"]],
    "vertexTargets":     [parse_data_vertex_targets],
    "inputMatrix1":      ["str"],
    "envelopeMatrix":    ["str"],
    "inputGeometry":     ["str"],
    "outputGeometry":    ["str"]
  },
  "xgDagTransform": {
    "inputMatrix":       ["str"],
    "outputMatrix":      ["str"]
  },
  "xgBone": {
    "restMatrix":        [16,"float"],
    "inputMatrix":       ["str"],
    "outputMatrix":      ["str"]
  },
  "xgBgMatrix": {
    "position":          [3,"float"],
    "rotation":          [4,"float"],
    "scale":             [3,"float"],
    "inputPosition":     ["str"],
    "inputRotation":     ["str"],
    "inputScale":        ["str"],
    "outputQuat":        ["str"],
    "outputVec3":        ["str"],
    "inputParentMatrix": ["str"],
    "outputMatrix":      ["str"]
  },
  "xgMaterial": {
    "blendType":         ["int"],
    "shadingType":       ["int"],
    "diffuse":           [4,"float"],
    "specular":          [4,"float"],
    "flags":             ["int"],
    "textureEnv":        ["int"],
    "uTile":             ["int"],
    "vTile":             ["int"],
    "inputTexture":      ["str"],
    "outputTexture":     ["str"]
  },
  "xgMultiPassMaterial": {
    "inputMaterial":     ["str"],
    "outputMaterial":    ["str"]
  },
  "xgTexture": {
    "url":               ["str"],
    "mipmap_depth":      ["int"]
  },
  "xgTime": {
    "numFrames":         ["float"],
    "time":              ["float"]
  },
  "xgVec3Interpolator": {
    "type":              ["int"],
    "keys":              ["len", [3,"float"]],
    "inputTime":         ["str"],
    "outputTime":        ["str"]
  },
  "xgQuatInterpolator": {
    "type":              ["int"],
    "keys":              ["len", [4,"float"]],
    "inputTime":         ["str"],
    "outputTime":        ["str"]
  },
  "xgVertexInterpolator": {
    "type":              ["int"],
    "times":             ["len", ["float"]],
    "keys":              [parse_data_keys],
    "targets":           ["len", ["int"]],
    "inputTime":         ["str"],
    "outputTime":        ["str"]
  },
  "xgNormalInterpolator": {
    "type":              ["int"],
    "times":             ["len", ["float"]],
    "keys":              [parse_data_keys],
    "targets":           ["len", ["int"]],
    "inputTime":         ["str"],
    "outputTime":        ["str"]
  },
  "xgTexCoordInterpolator": {
    "type":              ["int"],
    "times":             ["len", ["float"]],
    "keys":              [parse_data_keys],
    "targets":           ["len", ["int"]],
    "inputTime":         ["str"],
    "outputTime":        ["str"]
  },
  "xgShapeInterpolator": {
    "type":              ["int"],
    "times":             ["len", ["float"]],
    "keys":              [parse_data_keys],
    "targets":           ["len", ["int"]],
    "inputTime":         ["str"],
    "outputTime":        ["str"]
  }
}


def parse_param_data(data_list, f):
    data = []
    count = 1
    blocklen = 0
    for t in data_list:
      if type(t) is int:
        count = t
        
      elif type(t) is str:
        for i in range(count):
          if t == "int":
            data += [f.getint()]
          elif t == "sint":
            data += [f.getsignedint()]
          elif t == "float":
            data += [f.getfloat()]
          elif t == "str":
            data += [f.getstringb()]
          elif t == "len":
            blocklen = f.getint()
        count = 1
        
      elif type(t) is list:
        block = []
        for i in range(blocklen):
          block += [parse_param_data(t, f)]
        if len(block) > 0:
          data += block
        
      elif hasattr(t, '__call__'):
        data += t(f)
        
    return data


def parse_object(obj_type, f):
  params = {}
  
  prev_empty = False
  while True:
    if prev_empty:
      prev_empty = False
    else:
      tag = f.getstringb()
    if not tag:
      error("Expected } while parsing object of type " + obj_type)
    
    if tag == "}":
      break
    
    elif tag in obj_defs[obj_type]:
      param_list = obj_defs[obj_type]
      data_list = param_list[tag]
      data = parse_param_data(data_list, f)
      
      if len(data) > 0 and type(data[0]) is str and (data[0] in param_list or data[0] == "}"):
        # Empty
        if tag not in params:
          params[tag] = []
        #print tag, ":", params[tag]  ###
        #raw_input('')                ###
        if data[0] == "}":
          break
        else:
          tag = data[0]
          prev_empty = True
      
      else:
        if tag in params:
          params[tag] += data
        else:
          params[tag] = data
        #print tag, ":", params[tag]  ###
        #raw_input('')                ###
      
    else:
      error("Unknown object parameter " + tag + " in object of type " + obj_type)
  return params


def parse_dag(f):
  dag = {}
  while True:
    tag = f.getstringb()
    if not tag:
      error("Expected } while parsing \"dag\"")
    if tag == "}":
      break
    else:
      pass #TODO: Is it necessary to parse this tree?
  return dag


def parse_xg(f):
  dag = {}
  objs = {}
  obj_types = {}

  while True:
    tag = f.getstringb()
    if not tag:
      break
      
    if tag == "dag":
      if f.getstringb() != "{":
        error("Unexpected { following \"dag\"")
      dag = parse_dag(f)
      
    elif tag in obj_defs:
      obj_type = tag
      obj_name = f.getstringb()
      if not obj_name or obj_name in ["{", "}", ";"]:
        error("Expected object name after type")
      
      next = f.getstringb()
      if next == ";":
        continue  # Ignore declaration
      elif next != "{":
        error("Unexpected string \"" + next + "\" after object name")
      
      obj = {}
      obj["type"] = obj_type
      obj["params"] = parse_object(obj_type, f)
      objs[obj_name] = obj
      if obj_type not in obj_types:
        obj_types[obj_type] = [obj_name]
      else:
        obj_types[obj_type] += [obj_name]
  
    elif tag == "{" or "}":
      error("Unexpected " + tag)
      
    else:
      error("Unknown object type " + tag)
  return dag, objs, obj_types

def fixString(buffer):
  result = ""
  for c in buffer:
    if ord(c) >= 128:
      result += format(ord(c), 'x')
    else:
      result += c
  return result

def outputFbx(filebasename, objs, materialNames, boneNames, meshNames, timeNames):
  (sdk_manager, scene) = FbxCommon.InitializeSdkObjects()
  root_node = scene.GetRootNode()
  def add_lists(a, b):
    if len(a) != len(b):
      return a
    for i in range(len(a)):
      a[i] += b[i]
    return a
  def mul_lists(a, b):
    if len(a) != len(b):
      return a
    for i in range(len(a)):
      a[i] *= b[i]
    return a
      
  # Create Materials
  materials = {}
  for i in range(len(materialNames)):
    materialNameFbx = materialNames[i].replace('$', '_')
    xgMaterial = objs[materialNames[i]]
    if xgMaterial["type"] == "xgMultiPassMaterial":
      materialNameFbx = xgMaterial["params"]["inputMaterial"][1]
      xgMaterial = objs[xgMaterial["params"]["inputMaterial"][1]]["params"]
    else:
      xgMaterial = xgMaterial["params"]
    
    material = FbxSurfacePhong.Create(sdk_manager, materialNameFbx)
    material.Diffuse.Set(xgMaterial["diffuse"][0])
    material.DiffuseFactor.Set(1.)
    material.Specular.Set(xgMaterial["specular"][0])
    material.TransparencyFactor.Set(1.0 - xgMaterial["diffuse"][3])
    material.TransparentColor.Set(1.0 - xgMaterial["diffuse"][3])
    
    if "inputTexture" in xgMaterial:
      xgTexture = objs[xgMaterial["inputTexture"][0]]["params"]
      texUrl = xgTexture["url"][0].replace('.imx', '.png')
      if '/' in texUrl:
        texUrl = texUrl[len(texUrl) - texUrl[::-1].index('/'):]
      texture = FbxFileTexture.Create(sdk_manager, materialNameFbx)
      texture.SetFileName(texUrl)
      texture.SetTextureUse(FbxTexture.eStandard)
      texture.SetMappingType(FbxTexture.eUV)
      texture.SetMaterialUse(FbxFileTexture.eModelMaterial)
      texture.SetAlphaSource(FbxTexture.eRGBIntensity)
      texture.SetSwapUV(False)
      material.Diffuse.ConnectSrcObject(texture)
      
      print("*** Texture required:", texUrl)
    
    materials[materialNames[i]] = material
  
  geomEnvNames = []
  meshNodeDict = {}
  meshVIndexMin = {}
  meshVIndexMax = {}
  
  # Create Meshes
  for i in range(len(meshNames)):
    xgDagMesh = objs[meshNames[i]]["params"]
    xgBgGeometryName = xgDagMesh["inputGeometry"][0]
    xgBgGeometry = objs[xgBgGeometryName]["params"]
    meshNameFbx = meshNames[i].replace('$', '_')
    mesh = FbxMesh.Create(sdk_manager, meshNameFbx)
    
    meshNode = FbxNode.Create(sdk_manager, meshNameFbx)
    meshNode.SetNodeAttribute(mesh)
    
    meshNodeDict[meshNames[i]] = meshNode
    
    if "inputGeometry" in xgBgGeometry:
      xgEnvelopeNames = xgBgGeometry["inputGeometry"]
      for name in xgEnvelopeNames:
        xgEnvelope = objs[name]["params"]
        if "inputGeometry" in xgEnvelope:
          geomEnvName = xgEnvelope["inputGeometry"][0]
          if geomEnvName not in geomEnvNames:
            geomEnvNames += [geomEnvName]
    
    #TODO: Support multipass materials
    if xgDagMesh["inputMaterial"][0] in materials:
      meshNode.AddMaterial(materials[xgDagMesh["inputMaterial"][0]])
      meshNode.SetShadingMode(FbxNode.eTextureShading)
    
    primType = xgDagMesh["primType"][0]
    vType, vCount, vData = xgBgGeometry["vertices"]
    vBlock = [(v[0], v[1], v[2]) for v in vData]
    nBlock = [(v[4], v[5], v[6]) for v in vData] if vType > 1 else []
    if vType == 11:
      uvBlock = [(v[7], v[8]) for v in vData]
    elif vType == 15:
      uvBlock = [(v[11], v[12]) for v in vData]
    else:
      uvBlock = []

    # triangles
    triangles = []
    vMin = len(vBlock) + 1
    vMax = 0
    
    def shouldreverse(vB, nB, s1, s2, s3):
      if len(nB) > 0:
        ux = vB[s2][0] - vB[s1][0]
        uy = vB[s2][1] - vB[s1][1]
        uz = vB[s2][2] - vB[s1][2]
        vx = vB[s3][0] - vB[s1][0]
        vy = vB[s3][1] - vB[s1][1]
        vz = vB[s3][2] - vB[s1][2]
        
        nx = uy*vz - uz*vy
        ny = uz*vx - ux*vz
        nz = ux*vy - uy*vx
        
        # nxavg = (nB[s1][0] + nB[s2][0] + nB[s3][0]) / 3.
        # nyavg = (nB[s1][1] + nB[s2][1] + nB[s3][1]) / 3.
        # nzavg = (nB[s1][2] + nB[s2][2] + nB[s3][2]) / 3.
        
        # return nx*nxavg + ny*nyavg + nz*nzavg > 0

        r1 = 1 if (nx*nB[s1][0] + ny*nB[s1][1] + nz*nB[s1][2]) > 0 else 0
        r2 = 1 if (nx*nB[s2][0] + ny*nB[s2][1] + nz*nB[s2][2]) > 0 else 0
        r3 = 1 if (nx*nB[s3][0] + ny*nB[s3][1] + nz*nB[s3][2]) > 0 else 0
        return r1 + r2 + r3 >= 2
      return False
    
    def trackminmax(s1, s2, s3, vMin, vMax):
      sMin = min(s1, s2, s3)
      if sMin < vMin:
        vMin = sMin
      sMax = max(s1, s2, s3)
      if sMax > vMax:
        vMax = sMax
      return vMin, vMax
    
    # Triangle lists
    tListCount = xgDagMesh["triListCount"][0]
    tLists = []
    tListVTotal = 0
    if tListCount > 0:
      if primType == 4:
        # Explicit List
        tListCount = xgDagMesh["triListData"][0][0]
        tLists = [v[0] for v in xgDagMesh["triListData"][1:]]
        tListVTotal = tListCount
      elif primType == 5:
        # Start + End
        tListStart = xgDagMesh["triListData"][0][0]
        tListCount = xgDagMesh["triListData"][1][0]
        tLists = range(tListStart, tListStart + tListCount)
        tListVTotal = sum([v[0] for v in xgDagMesh["triListData"][1:]])
      else:
        error("Unsupported primType: " + str(primType))
    
      for j in range(len(tLists))[::3]:
        s1 = tLists[j]
        s2 = tLists[j+1]
        s3 = tLists[j+2]
        vMin, vMax = trackminmax(s1, s2, s3, vMin, vMax)
        if shouldreverse(vBlock, nBlock, s1, s2, s3):
          triangles += [(s3, s2, s1)]
        else:
          triangles += [(s1, s2, s3)]
    
    # Triangle strips
    tStripCount = xgDagMesh["triStripCount"][0]
    tStrips = []
    tStripVTotal = 0
    if tStripCount > 0:
      if primType == 4:
        # Explicit List
        stripSize = 0
        ind = 0
        for j in range(tStripCount):
          strip = []
          stripSize = xgDagMesh["triStripData"][ind][0]
          tStripVTotal += stripSize
          for k in range(stripSize):
            strip += xgDagMesh["triStripData"][ind+k+1]
          tStrips += [strip]
          ind += stripSize + 1
      elif primType == 5:
        # Start + List of # of vertices per strip
        tStripStart = xgDagMesh["triStripData"][0][0]
        ind = 0
        for j in range(tStripCount):
          stripSize = xgDagMesh["triStripData"][j+1][0]
          strip = range(tStripStart+ind, tStripStart+ind+stripSize)
          tStrips += [strip]
          ind += stripSize
        tStripVTotal = sum([v[0] for v in xgDagMesh["triStripData"][1:]])
      else:
        error("Unsupported primType: " + str(primType))
        
      for j in range(len(tStrips)):
        strip = tStrips[j]
        reverse = shouldreverse(vBlock, nBlock, strip[0], strip[1], strip[2])
        for k in range(len(strip) - 2):
          s1 = strip[k]
          s2 = strip[k+1]
          s3 = strip[k+2]
          vMin, vMax = trackminmax(s1, s2, s3, vMin, vMax)
          if reverse:
            triangles += [(s3, s2, s1)]
          else:
            triangles += [(s1, s2, s3)]
          reverse = not reverse
          
    # Pre-adjust vertices given rest pose and bone transform.
    if "inputGeometry" in xgBgGeometry:
      xgEnvelopeNames = xgBgGeometry["inputGeometry"]
      for name in xgEnvelopeNames:
        xgEnvelope = objs[name]["params"]
        if "inputMatrix1" not in xgEnvelope:
          continue  # no bone
        boneName = xgEnvelope["inputMatrix1"][0]
        xgBone = objs[boneName]["params"]
        xgBoneMatrix = objs[xgBone["inputMatrix"][0]]["params"]
        xgBonePos = xgBoneMatrix["position"]
        xgBoneRot = xgBoneMatrix["rotation"]
        xgBoneScl = xgBoneMatrix["scale"]
        
        M_r = FbxMatrix()
        for j in range(16):
          M_r.Set(j // 4, j % 4, xgBone["restMatrix"][j])
        M_r_it = M_r.Inverse().Transpose()

        M_s = FbxMatrix()
        M_s.SetTRS(FbxVector4(), FbxVector4(), FbxVector4(-1.0, 1.0, 1.0))
        M_r = M_s * M_r
        
        for j in range(len(xgEnvelope["vertexTargets"])):
          for k in xgEnvelope["vertexTargets"][j]:
            v = FbxVector4(vBlock[k][0], vBlock[k][1], vBlock[k][2], 1.0)
            v = M_r.MultNormalize(v)
            vBlock[k] = [v[0], v[1], v[2]]
            if nBlock:
              n = FbxVector4(nBlock[k][0], nBlock[k][1], nBlock[k][2], 0.0)

              # Because MultNormalize normalizes the w component of the vector to 1,
              # there is literally no way to multiply a standard matrix by a normal
              # vector using the FBX SDK...
              nx, ny, nz = nBlock[k]
              nnx = M_r_it.Get(0, 0) * nx + M_r_it.Get(0, 1) * ny + M_r_it.Get(0, 2) * nz
              nny = M_r_it.Get(1, 0) * nx + M_r_it.Get(1, 1) * ny + M_r_it.Get(1, 2) * nz
              nnz = M_r_it.Get(2, 0) * nx + M_r_it.Get(2, 1) * ny + M_r_it.Get(2, 2) * nz
              nBlock[k] = [-nnx, nny, nnz]

        # M_w = FbxAMatrix()
        # M_w.SetT(FbxVector4(-xgBonePos[0], xgBonePos[1], xgBonePos[2]))
        # M_q = FbxAMatrix()
        # M_q.SetQ(FbxQuaternion(-xgBoneRot[0], xgBoneRot[1], xgBoneRot[2], xgBoneRot[3]))
        # M_s = FbxAMatrix()
        # M_s.SetS(FbxVector4(xgBoneScl[0], xgBoneScl[1], xgBoneScl[2]))
        
        # M_final = FbxMatrix(M_w) * FbxMatrix(M_q) * FbxMatrix(M_s)
        
        # for j in range(len(xgEnvelope["vertexTargets"])):
        #   for k in xgEnvelope["vertexTargets"][j]:
        #     v = FbxVector4(vBlock[k][0], vBlock[k][1], vBlock[k][2], 1.0)
        #     v = M_final.MultNormalize(v)
        #     vBlock[k] = [v[0], v[1], v[2]]
   
    # Vertices
    mesh.InitControlPoints(vMax - vMin + 1)
    for j in range(vMin, vMax + 1):
      v = FbxVector4(vBlock[j][0], vBlock[j][1], vBlock[j][2])
      mesh.SetControlPointAt(v, j - vMin)
          
    # Add triangles to mesh.
    for s1, s2, s3 in triangles:
      s1 -= vMin
      s2 -= vMin
      s3 -= vMin
      mesh.BeginPolygon()
      mesh.AddPolygon(s1)
      mesh.AddPolygon(s2)
      mesh.AddPolygon(s3)
      mesh.EndPolygon()
    
    if not mesh.GetLayer(0):
      mesh.CreateLayer()
    
    # Tex coords
    if len(uvBlock) > 0:
      layerElemUV = FbxLayerElementUV.Create(mesh, "DiffuseUV")
      layerElemUV.SetMappingMode(FbxLayerElement.eByControlPoint)
      layerElemUV.SetReferenceMode(FbxLayerElement.eDirect)
      mesh.GetLayer(0).SetUVs(layerElemUV, FbxLayerElement.eTextureDiffuse)
      for j in range(vMin, vMax + 1):
        u, v = uvBlock[j]
        uv = FbxVector2(u, 1.0 - v)
        layerElemUV.GetDirectArray().Add(uv)
      
    # Normals
    if EXPORT_NORMALS and len(nBlock) > 0:
      layerElemNormal = FbxLayerElementNormal.Create(mesh, "Normal")
      layerElemNormal.SetMappingMode(FbxLayerElement.eByControlPoint)
      layerElemNormal.SetReferenceMode(FbxLayerElement.eDirect)
      mesh.GetLayer(0).SetNormals(layerElemNormal)
      for j in range(vMin, vMax + 1):
        nx, ny, nz = nBlock[j]
        n = FbxVector4(nx, ny, nz)
        layerElemNormal.GetDirectArray().Add(n)
    
    root_node.AddChild(meshNode)
    
    meshVIndexMin[meshNames[i]] = vMin
    meshVIndexMax[meshNames[i]] = vMax

  boneNodeDict = {}
    
  # Create skeleton.
  for i in range(len(boneNames)):
    xgBone = objs[boneNames[i]]["params"]
    xgBoneMatrix = objs[xgBone["inputMatrix"][0]]["params"]
    xgBonePos = xgBoneMatrix["position"]
    xgBoneRot = xgBoneMatrix["rotation"]
    
    mat = FbxAMatrix()
    mat.SetQ(FbxQuaternion(-xgBoneRot[0], xgBoneRot[1], xgBoneRot[2], xgBoneRot[3]))
    xgBoneRot = mat.GetR()

    xgBoneScl = xgBoneMatrix["scale"]
    if "inputParentMatrix" in xgBoneMatrix:
      xgParentBoneMatrix = objs[xgBoneMatrix["inputParentMatrix"][0]]["params"]
      while xgParentBoneMatrix:
        xgBonePos = add_lists(xgBonePos, xgParentBoneMatrix["position"])
        xgBoneRot = add_lists(xgBoneRot, xgBoneMatrix["rotation"])
        xgBoneScl = mul_lists(xgBoneScl, xgBoneMatrix["scale"])
        if "inputParentMatrix" in xgParentBoneMatrix:
          xgParentBoneMatrix = objs[xgParentBoneMatrix["inputParentMatrix"][0]]["params"]
        else:
          xgParentBoneMatrix = None
    
    boneNameFbx = fixString(boneNames[i].replace('$', '_'))
    boneAttr = FbxSkeleton.Create(sdk_manager, boneNameFbx)
    boneAttr.SetSkeletonType(FbxSkeleton.eLimbNode)
    bone = FbxNode.Create(sdk_manager, boneNameFbx)
    bone.SetNodeAttribute(boneAttr)
    bone.LclTranslation.Set(FbxDouble3(xgBonePos[0]*-1, xgBonePos[1], xgBonePos[2]))
    bone.LclRotation.Set(FbxDouble3(xgBoneRot[0], xgBoneRot[1], xgBoneRot[2]))
    # Skipping bone scale since this breaks FBX export in Maya (e.g. Panpeus).
    #bone.LclScaling.Set(FbxDouble3(xgBoneScl[0], xgBoneScl[1], xgBoneScl[2]))

    boneNodeDict[boneNames[i]] = bone

    root_node.AddChild(bone)
    
  # Create skin clusters and bind pose.
  for i in range(len(meshNames)):
    xgDagMesh = objs[meshNames[i]]["params"]
    xgBgGeometryName = xgDagMesh["inputGeometry"][0]
    xgBgGeometry = objs[xgBgGeometryName]["params"]
    
    meshNode = meshNodeDict[meshNames[i]]
    vMin = meshVIndexMin[meshNames[i]]
    
    skin = FbxSkin.Create(sdk_manager, "")
    if "inputGeometry" in xgBgGeometry:
      xgEnvelopeNames = xgBgGeometry["inputGeometry"]
      for name in xgEnvelopeNames:
        xgEnvelope = objs[name]["params"]
        if "inputMatrix1" not in xgEnvelope:
          continue  # no bone
        boneName = xgEnvelope["inputMatrix1"][0]
        xgBone = objs[boneName]["params"]
        xgBoneMatrix = objs[xgBone["inputMatrix"][0]]["params"]
        xgBonePos = xgBoneMatrix["position"]
        xgBoneRot = xgBoneMatrix["rotation"]
        xgBoneScl = xgBoneMatrix["scale"]
        bone = boneNodeDict[boneName]
        
        cluster = FbxCluster.Create(sdk_manager, "")
        cluster.SetLink(bone)
        cluster.SetLinkMode(FbxCluster.eTotalOne)
        
        # M_iwt = FbxAMatrix()
        # M_iwt.SetT(FbxVector4(xgBonePos[0], xgBonePos[1], xgBonePos[2]))
        
        # M_iwq = FbxAMatrix()
        # q = FbxQuaternion(xgBoneRot[0], xgBoneRot[1], xgBoneRot[2], xgBoneRot[3])
        # M_iwq.SetQ(q)

        # M_iws = FbxAMatrix()
        # # M_iws.SetS(FbxVector4(1. / xgBoneScl[0], 1. / xgBoneScl[1], 1. / xgBoneScl[2]))
        
        # cluster.SetTransformMatrix((M_iwq * M_iwt))
        
        # The below doesn't work for some bones...
        #M_iw = scene.GetAnimationEvaluator().GetNodeGlobalTransform(bone).Inverse()
        #cluster.SetTransformMatrix(M_iw)
        
        for j in range(len(xgEnvelope["vertexTargets"])):
          for v in xgEnvelope["vertexTargets"][j]:
            cluster.AddControlPointIndex(v - vMin, xgEnvelope["weights"][j][0])
            
        skin.AddCluster(cluster)

    meshNode.GetNodeAttribute().AddDeformer(skin)
    
    bindPose = FbxPose.Create(sdk_manager, meshNames[i] + 'bindpose')
    bindPose.SetIsBindPose(True)
    bindPose.Add(meshNode, FbxMatrix())
    if "inputGeometry" in xgBgGeometry:
      xgEnvelopeNames = xgBgGeometry["inputGeometry"]
      for name in xgEnvelopeNames:
        xgEnvelope = objs[name]["params"]
        if "inputMatrix1" not in xgEnvelope:
          continue  # no bone
        boneName = xgEnvelope["inputMatrix1"][0]
        bone = boneNodeDict[boneName]
        bindPose.Add(bone, FbxMatrix(), True)
    scene.AddPose(bindPose)

  # Create animation data. Note that all animations will be concatenated together.
  # The XGM archive may contain metadata that splits animation clips?
  if EXPORT_ANIMATION and len(timeNames) > 0:
    xgTime = objs[timeNames[0]]["params"]
    t = FbxTime()
    
    timespan = FbxTimeSpan()
    t.SetSecondDouble(0)
    timespan.SetStart(t)
    t.SetSecondDouble(xgTime["numFrames"][0] / PLAYBACK_SPEED / FRAMES_PER_SECOND)
    print("Number of Frames:", t.GetFrameCount())
    timespan.SetStop(t)
    scene.GetGlobalSettings().SetTimelineDefaultTimeSpan(timespan)
    
    animStack = FbxAnimStack.Create(scene, "XGAnim")
    animLayer = FbxAnimLayer.Create(scene, "Base Layer")
    animStack.AddMember(animLayer)
    
    for i in range(len(boneNames)):
      xgBone = objs[boneNames[i]]["params"]
      xgBoneMatrix = objs[xgBone["inputMatrix"][0]]["params"]
      bone = boneNodeDict[boneNames[i]]

      # Position Keyframes (assuming a flat skeletal structure)
      if "inputPosition" in xgBoneMatrix:
        xgPosInterp = objs[xgBoneMatrix["inputPosition"][0]]["params"]
        if xgPosInterp["type"][0] == 1:
          curveX = bone.LclTranslation.GetCurve(animLayer, "X", True)
          curveY = bone.LclTranslation.GetCurve(animLayer, "Y", True)
          curveZ = bone.LclTranslation.GetCurve(animLayer, "Z", True)
          for i, (x, y, z) in enumerate(xgPosInterp["keys"]):
            x *= -1
            t.SetSecondDouble(float(i) / PLAYBACK_SPEED / FRAMES_PER_SECOND)
          
            curveX.KeyModifyBegin()
            key = curveX.KeyAdd(t)[0]
            curveX.KeySetValue(key, x)
            curveX.KeySetInterpolation(key, FbxAnimCurveDef.eInterpolationCubic)
            curveX.KeyModifyEnd()
            
            curveY.KeyModifyBegin()
            key = curveY.KeyAdd(t)[0]
            curveY.KeySetValue(key, y)
            curveY.KeySetInterpolation(key, FbxAnimCurveDef.eInterpolationCubic)
            curveY.KeyModifyEnd()
            
            curveZ.KeyModifyBegin()
            key = curveZ.KeyAdd(t)[0]
            curveZ.KeySetValue(key, z)
            curveZ.KeySetInterpolation(key, FbxAnimCurveDef.eInterpolationCubic)
            curveZ.KeyModifyEnd()
        else:
          print("Warning: Unknown animation type", xgPosInterp["type"])
      
      # Rotation Keyframes
      if "inputRotation" in xgBoneMatrix:
        xgPosInterp = objs[xgBoneMatrix["inputRotation"][0]]["params"]
        if xgPosInterp["type"][0] == 1:
          curveX = bone.LclRotation.GetCurve(animLayer, "X", True)
          curveY = bone.LclRotation.GetCurve(animLayer, "Y", True)
          curveZ = bone.LclRotation.GetCurve(animLayer, "Z", True)
          for i, (x, y, z, w) in enumerate(xgPosInterp["keys"]):
            mat = FbxAMatrix()
            mat.SetQ(FbxQuaternion(-x, y, z, w))
            rot = mat.GetR()
            x, y, z = (rot[0], rot[1], rot[2])
            t.SetSecondDouble(float(i) / PLAYBACK_SPEED / FRAMES_PER_SECOND)
          
            curveX.KeyModifyBegin()
            key = curveX.KeyAdd(t)[0]
            curveX.KeySetValue(key, x)
            curveX.KeySetInterpolation(key, FbxAnimCurveDef.eInterpolationCubic)
            curveX.KeyModifyEnd()
            
            curveY.KeyModifyBegin()
            key = curveY.KeyAdd(t)[0]
            curveY.KeySetValue(key, y)
            curveY.KeySetInterpolation(key, FbxAnimCurveDef.eInterpolationCubic)
            curveY.KeyModifyEnd()
            
            curveZ.KeyModifyBegin()
            key = curveZ.KeyAdd(t)[0]
            curveZ.KeySetValue(key, z)
            curveZ.KeySetInterpolation(key, FbxAnimCurveDef.eInterpolationCubic)
            curveZ.KeyModifyEnd()
        else:
          print("Warning: Unknown animation type", xgPosInterp["type"])
      
      # Scale Keyframes
      if "inputScale" in xgBoneMatrix:
        xgPosInterp = objs[xgBoneMatrix["inputScale"][0]]["params"]
        if xgPosInterp["type"][0] == 1:
          curveX = bone.LclScaling.GetCurve(animLayer, "X", True)
          curveY = bone.LclScaling.GetCurve(animLayer, "Y", True)
          curveZ = bone.LclScaling.GetCurve(animLayer, "Z", True)
          for i, (x, y, z) in enumerate(xgPosInterp["keys"]):
            t.SetSecondDouble(float(i) / PLAYBACK_SPEED / FRAMES_PER_SECOND)
          
            curveX.KeyModifyBegin()
            key = curveX.KeyAdd(t)[0]
            curveX.KeySetValue(key, x)
            curveX.KeySetInterpolation(key, FbxAnimCurveDef.eInterpolationCubic)
            curveX.KeyModifyEnd()
            
            curveY.KeyModifyBegin()
            key = curveY.KeyAdd(t)[0]
            curveY.KeySetValue(key, y)
            curveY.KeySetInterpolation(key, FbxAnimCurveDef.eInterpolationCubic)
            curveY.KeyModifyEnd()
            
            curveZ.KeyModifyBegin()
            key = curveZ.KeyAdd(t)[0]
            curveZ.KeySetValue(key, z)
            curveZ.KeySetInterpolation(key, FbxAnimCurveDef.eInterpolationCubic)
            curveZ.KeyModifyEnd()
        else:
          print("Warning: Unknown animation type", xgPosInterp["type"])
  
  file_format = -1
  if USE_FBX_BINARY_FORMAT:
    io_plugin_reg = sdk_manager.GetIOPluginRegistry()
    format_count = io_plugin_reg.GetWriterFormatCount()
    for i in range(format_count):
      if not io_plugin_reg.WriterIsFBX(i):
        continue
      if 'binary' in io_plugin_reg.GetWriterFormatDescription(i):
        file_format = i
        break

  filename = filebasename + ".fbx"
  FbxCommon.SaveScene(sdk_manager, scene, filename, pFileFormat=file_format)
  
  sdk_manager.Destroy()


def outputMesh(filebasename, objs, meshNames):
  def ffloat(val):
    return "%.4f" % val
  def ffloatarr(vals):
    return " ".join([ffloat(v) for v in vals])
  def slash(val, count):
    return "/".join([str(val) for i in range(count)])

  # Material
  with open(filebasename + ".mat", "w+") as f:
    matNames = []
    for i in range(len(meshNames)):
      xgDagMesh = objs[meshNames[i]]
      xgMaterialName = xgDagMesh["params"]["inputMaterial"][0]
      if xgMaterialName not in matNames:
        matNames += [xgMaterialName]
  
    for i in range(len(matNames)):
      xgMaterial = objs[matNames[i]]
      
      f.write("newmtl " + matNames[i].replace('$', '_') + "\n")
      f.write("illum 2\n")
      if "diffuse" in xgMaterial["params"]:
        f.write("Kd " + ffloatarr(xgMaterial["params"]["diffuse"][:3]) + "\n")
      f.write("Ka 0.0000 0.0000 0.0000\n")
      if "specular" in xgMaterial["params"]:
        f.write("Ks " + ffloatarr(xgMaterial["params"]["specular"][:3]) + "\n")
      
      if "inputTexture" in xgMaterial["params"]:
        xgTextureName = xgMaterial["params"]["inputTexture"][0]
        xgTexture = objs[xgTextureName]
        texname = xgTexture["params"]["url"][0]
        texname = texname[:texname.find(".")] + ".png"
        f.write("map_Kd " + texname + "\n")
        print("Texture needed:", texname)
      
      f.write("\n")
  
  # Wavefront OBJ
  with open(filebasename + ".obj", "w+") as f:
    f.write("mtllib " + filebasename + ".mat\n")
    f.write("o " + filebasename + "\n\n")
    
    pos = []
    uvs = []
    norms = []
    
    def shouldreverse(startIndex):
      if len(norms) > 0:
        ux = pos[vIndex+1][0] - pos[vIndex][0]
        uy = pos[vIndex+1][1] - pos[vIndex][1]
        uz = pos[vIndex+1][2] - pos[vIndex][2]
        vx = pos[vIndex+2][0] - pos[vIndex][0]
        vy = pos[vIndex+2][1] - pos[vIndex][1]
        vz = pos[vIndex+2][2] - pos[vIndex][2]
        
        nx = uy*vz - uz*vy
        ny = uz*vx - ux*vz
        nz = ux*vy - uy*vx
        
        nxavg = (norms[vIndex][0] + norms[vIndex+1][0] + norms[vIndex+2][0]) / 3
        nyavg = (norms[vIndex][1] + norms[vIndex+1][1] + norms[vIndex+2][1]) / 3
        nzavg = (norms[vIndex][2] + norms[vIndex+1][2] + norms[vIndex+2][2]) / 3
        
        return nx*nxavg + ny*nyavg + nz*nzavg > 0
      return False
    
    vIndex = 1
    vTotalCount = 0
    for i in range(0, len(meshNames)):
      xgDagMesh = objs[meshNames[i]]
      xgBgGeometryName = xgDagMesh["params"]["inputGeometry"][0]
      xgBgGeometry = objs[xgBgGeometryName]
      
      f.write("g " + meshNames[i].replace('$', '_') + "\n")
      f.write("usemtl " + xgDagMesh["params"]["inputMaterial"][0].replace('$', '_') + "\n")
      
      # Vertices (only those that are used by the mesh, not the whole list)
      vType, vCount, vData = xgBgGeometry["params"]["vertices"]
      primType = xgDagMesh["params"]["primType"][0]
      
      tStripCount = xgDagMesh["params"]["triStripCount"][0]
      tStrips = []
      tStripVTotal = 0
      if tStripCount > 0:
        if primType == 4:
          # Explicit List
          stripSize = 0
          ind = 0
          for j in range(tStripCount):
            stripSize = xgDagMesh["params"]["triStripData"][ind][0]
            tStripVTotal += stripSize
            for k in range(stripSize):
              tStrips += xgDagMesh["params"]["triStripData"][ind+k+1]
            ind += stripSize + 1
        elif primType == 5:
          # Start + List of # of vertices per strip
          tStripStart = xgDagMesh["params"]["triStripData"][0][0]
          tStripVTotal = sum([v[0] for v in xgDagMesh["params"]["triStripData"][1:]])
          tStrips = list(range(tStripStart, tStripStart+tStripVTotal))
        else:
          error("Unsupported primType: " + str(primType))
      
      tListCount = xgDagMesh["params"]["triListCount"][0]
      tLists = []
      tListVTotal = 0
      if tListCount > 0:
        if primType == 4:
          # Explicit List
          tListCount = xgDagMesh["params"]["triListData"][0][0]
          tLists = [v[0] for v in xgDagMesh["params"]["triListData"][1:]]
          tListVTotal = tListCount
        elif primType == 5:
          # Start + End
          tListStart = xgDagMesh["params"]["triListData"][0][0]
          tListCount = xgDagMesh["params"]["triListData"][1][0]
          tLists = list(range(tListStart, tListStart + tListCount))
          tListVTotal = sum([v[0] for v in xgDagMesh["params"]["triListData"][1:]])
        else:
          error("Unsupported primType: " + str(primType))
      
      for j in tLists + tStrips:
        if vType == 1:
          x, y, z, w = vData[j]
          x *= -1.0
          f.write("v " + ffloatarr([x,y,z]) + "\n")
          pos += [[x,y,z]]
        elif vType == 3:
          x, y, z, w, nx, ny, nz = vData[j]
          x *= -1.0
          nx *= -1.0
          f.write("v " + ffloatarr([x,y,z]) + "\n")
          pos += [[x,y,z]]
          norms += [[nx,ny,nz]]
        elif vType == 7:
          x, y, z, w, nx, ny, nz, x2, y2, z2, w2 = vData[j]
          x *= -1.0
          x2 *= -1.0
          nx *= -1.0
          f.write("v " + ffloatarr([x,y,z]) + "\n")
          pos += [[x,y,z]]
          norms += [[nx,ny,nz]]
        elif vType == 11:
          x, y, z, w, nx, ny, nz, u, v = vData[j]
          x *= -1.0
          nx *= -1.0
          f.write("v " + ffloatarr([x,y,z]) + "\n")
          pos += [[x,y,z]]
          norms += [[nx,ny,nz]]
          uvs += [[u,v]]
        elif vType == 15:
          x, y, z, w, nx, ny, nz, x2, y2, z2, w2, u, v = vData[j]
          x *= -1.0
          x2 *= -1.0
          nx *= -1.0
          f.write("v " + ffloatarr([x,y,z]) + "\n")
          pos += [[x,y,z]]
          norms += [[nx,ny,nz]]
          uvs += [[u,v]]
        
      # Normals
      for nx, ny, nz in norms[vIndex-1:]:
        f.write("vn " + ffloatarr([nx,ny,nz]) + "\n")
        
      # Texture Coordinates
      for u, v in uvs[vIndex-1:]:
        f.write("vt " + ffloatarr([u,v*-1]) + "\n")
      
      # Triangle Lists
      tListData = xgDagMesh["params"]["triListData"]
      for k in range(tListCount // 3):
        if shouldreverse(vIndex):
          f.write("f " + slash(vIndex+k*3+2,3) + " " + slash(vIndex+k*3+1,3) + " " + slash(vIndex+k*3,3) + "\n")
        else:
          f.write("f " + slash(vIndex+k*3,3) + " " + slash(vIndex+k*3+1,3) + " " + slash(vIndex+k*3+2,3) + "\n")
      vIndex += tListCount
      
      # Triangle Strips
      tStripData = xgDagMesh["params"]["triStripData"]
      tStripSize = 0
      ind = 0
      for j in range(tStripCount):
      
        if primType == 4:
          tStripSize = tStripData[ind][0]
          ind += tStripSize + 1
        elif primType == 5:
          tStripSize = tStripData[j+1][0]
        
        for k in range(tStripSize - 2):
          if k == 0:
            reverse = shouldreverse(vIndex)
          if reverse:
            f.write("f " + slash(vIndex+2,3) + " " + slash(vIndex+1,3) + " " + slash(vIndex,3) + "\n")
          else:
            f.write("f " + slash(vIndex,3) + " " + slash(vIndex+1,3) + " " + slash(vIndex+2,3) + "\n")
          reverse = not reverse
          vIndex += 1
        vIndex += 2

      f.write("\n")

      
def testVertices(objs, meshNames):
  for meshName in meshNames:
    print(meshName)
    xgDagMesh = objs[meshName]["params"]
    xgBgGeometryName = xgDagMesh["inputGeometry"][0]
    xgBgGeometry = objs[xgBgGeometryName]["params"]

    if "inputGeometry" in xgBgGeometry:
      min = 50
      for envName in xgBgGeometry["inputGeometry"]:
        xgEnvelope = objs[envName]["params"]
        for b in xgEnvelope["vertexTargets"]:
          for i in b:
            if i < min:
              min = i
        
        if "inputGeometry" in xgEnvelope:
          geomEnvName = xgEnvelope["inputGeometry"][0]
          xgEnvGeometry = objs[geomEnvName]["params"]
          
    print("Vertex count:", xgBgGeometry["vertices"][1])
    print("Envelope vertex count:", xgEnvGeometry["vertices"][1])
    print(min)
            
    print('')


def printDag(objs, obj_types):
  for objName in objs:
    obj = objs[objName]
    print(obj["type"], objName)
    for paramName in obj["params"]:
      param = obj["params"][paramName]
      isStr = False
      for p in param:
        if type(p) is str:
          isStr = True
          break
      if isStr:
        print("  ", paramName, "=", param)
    print("")


def main():
  if len(sys.argv) != 2:
    print("Usage: python xg.py <XG File>")
    sys.exit(1)
   
  filename = sys.argv[1]
  
  try:
    f = BinaryFileReader(filename)
  except IOError as e:
    if e.errno == 2:
      error("File not found: " + filename)
    else:
      error(e)
  except:
    error(e)
  
  header = f.read(8)
  if header != b"XGBv1.00":
    error("File type not supported")
  
  dag, objs, obj_types = parse_xg(f)
  
  if DEBUG_PRINT_DAG:
    printDag(objs, obj_types)
  
  prefix = filename[:filename.index('.')]
  if EXPORT_OBJ:
    outputMesh(prefix, objs, obj_types["xgDagMesh"])

  if EXPORT_FBX:
    mats = obj_types["xgMaterial"]
    if "xgMultiPassMaterial" in obj_types:
      mats += obj_types["xgMultiPassMaterial"]
    outputFbx(prefix, objs, mats, obj_types["xgBone"] if "xgBone" in obj_types else [], obj_types["xgDagMesh"], obj_types["xgTime"] if "xgTime" in obj_types else [])
  
  # testVertices(objs, obj_types["xgDagMesh"])
  
  print("\nDone!")


if __name__ == "__main__":
  main()
