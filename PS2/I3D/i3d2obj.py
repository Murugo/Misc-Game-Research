# Converts a .i3d model file or a Rule of Rose (PS2) .MDL model file to OBJ.

import argparse
import argparse
import math
import numpy as np
import os
import sys
import struct

parser = argparse.ArgumentParser(description='''
Converts a .i3d model file or a Rule of Rose (PS2) .MDL model file to OBJ.
''')

def err(msg):
    print("Error: {}".format(msg))
    sys.exit(1)

def getuint16(b, offs = 0):
    return struct.unpack('<H', b[offs:offs+2])[0]

def getnuint16(b, offs, n):
    return struct.unpack('<' + 'H'*n, b[offs:offs+2*n])

def getuint32(b, offs = 0):
    return struct.unpack('<I', b[offs:offs+4])[0]

def getfloat32(b, offs):
    return struct.unpack('<f', b[offs:offs+4])[0]

def getnfloat32(b, offs, n):
    return struct.unpack('<' + 'f'*n, b[offs:offs+4*n])

parser.add_argument('mdlpath', help='Input path of .MDL/.I3D file', nargs=1)
args = parser.parse_args()

if len(args.mdlpath[0]) == 0:
    parser.print_usage()
    sys.exit(1)

# Extracts a file from an RPK archive with the given index.
def ReadRpkFile(f, index):
    f.seek(0)
    header = f.read(0x20)
    totalsize = getuint32(header, 0x4)
    filesize = 0
    fileoffs = 0
    if header[:4] == b'RTPK':
        numfiles = getuint16(header, 0xE)
        if index < 0 or index >= numfiles:
            err("File index {} out of range in RTPK archive".format(index))

        if header[0xA] == 0x2:  # Offset table only
            f.seek(index * 0x4 + 0x20)
            fileoffs = getuint32(f.read(4))
            if index == numfiles - 1:
                filesize = totalsize - fileoffs
            else:
                filesize = getuint32(f.read(4)) - fileoffs
        elif header[0xA] == 0x3:  # Size and offset tables
            f.seek(index * 0x4 + 0x20)
            filesize = getuint32(f.read(4))
            f.seek((numfiles + index) * 4 + 0x20)
            fileoffs = getuint32(f.read(4))
    elif header[:7] == b'I3D_BIN':
        filesize = totalsize
    else:
        err("Not an RTPK archive or I3D file!")
    f.seek(fileoffs)
    return f.read(filesize)


class Node:
    def __init__(self, buf, offs):
        self.dataOffs = getuint32(buf, offs)
        self.dataType = buf[offs + 0x7] & 0x7F
        self.children = []
        numChildren = getuint16(buf, offs + 0x4)
        firstChildOffs = getuint32(buf, offs + 0x8)
        for i in range(numChildren):
            self.children.append(Node(buf, firstChildOffs + i * 0x10))
    
    def getChildrenByType(self, dataType):
        result = []
        for child in self.children:
            result += child.getChildrenByType(dataType)
        if self.dataType == dataType:
            result = [self] + result
        return result


def parseName(buf, offs):
    endOffs = offs
    while buf[endOffs] != 0:
        endOffs += 1
    return buf[offs:endOffs].decode(encoding='ascii')


class SubmeshPiece:
    def __init__(self, offs):
        self.offs = offs
        self.vtx = []
        self.vt = []
        self.vn = []
        self.ind = []


class Submesh:
    def __init__(self, offs, materialIndex):
        self.offs = offs
        self.materialIndex = materialIndex
        self.submeshPieces = []


class Mesh:
    def __init__(self, offs):
        self.offs = offs
        self.submeshes = []


class MeshInstance:
    def __init__(self, offs, combinedMeshOffs):
        self.offs = offs
        self.combinedMeshOffs = combinedMeshOffs
        self.meshes = []


vumem = [[0, 0, 0, 0] for _ in range(0x1000)]  # VU1 memory is 16K bytes
def parseVif(buf, offs):
    endoffs = offs + (buf[offs + 0x4] << 4) + 0x10
    offs += 0x10
    vif_r = [0, 0, 0, 0]  # Can I assume this?
    vif_c = [1, 1, 1, 1]  # Pretty sure I can assume this at least
    cl = 1
    wl = 1
    mask = [0 for _ in range(16)]

    def maybe_mask_value(val, index, cycle, use_mask):
        if not use_mask or mask[index] == 0b00:
            return val
        if mask[index + min(cycle, 3) * 4] == 0b01:
            return vif_r[index]
        if mask[index + min(cycle, 3) * 4] == 0b10:
            return vif_c[min(3, cycle)]
        return 0

    while offs < endoffs:
        imm, qwd, cmd = struct.unpack('<HBB', buf[offs:offs+4])
        cmd &= 0x7F
        offs += 4
        if cmd == 0b00000000:  # NOP
            continue
        elif cmd == 0b00000001:  # STCYCLE
            cl = imm & 0xFF
            wl = (imm >> 8) & 0xFF
        elif cmd == 0b00110000:  # STROW
            vif_r = getnfloat32(buf, offs, 4)
            offs += 0x10
        elif cmd == 0b00110001:  # STCOL
            vif_c = getnfloat32(buf, offs, 4)
            offs += 0x10
        elif cmd == 0b00100000:  # STMASK
            m = getuint32(buf, offs)
            mask = [((m >> (i << 1)) & 0x3) for i in range(16)]
            offs += 4
        elif cmd >> 5 == 0b11:  # UNPACK
            # NOTE: This has to handle both skipping writes (cl >= wl) and filling writes (cl < wl)!
            addr = imm & 0x3FF
            vnvl = cmd & 0xF
            m = (cmd & 0x10) > 0
            j = 0
            if vnvl == 0b0000:  # S-32
                width = 4
                for i in range(qwd):
                    val = 0
                    if cl >= wl or (i % wl) < cl:
                        val = getfloat32(buf, width * j + offs)
                        j += 1
                    addroffs = cl * (i // wl) + (i % wl) if cl >= wl else 0
                    vumem[addr + addroffs] = [
                        maybe_mask_value(val, 0, i, m),
                        maybe_mask_value(val, 1, i, m),
                        maybe_mask_value(val, 2, i, m),
                        maybe_mask_value(val, 3, i, m),
                    ]
            elif vnvl == 0b0100:  # V2-32
                width = 8
                for i in range(qwd):
                    val = [0, 0]
                    if cl >= wl or (i % wl) < cl:
                        val = getnfloat32(buf, width * j + offs, 2)
                        j += 1
                    addroffs = cl * (i // wl) + (i % wl) if cl >= wl else 0
                    vumem[addr + addroffs] = [
                        maybe_mask_value(val[0], 0, i, m),
                        maybe_mask_value(val[1], 1, i, m),
                        maybe_mask_value(0, 2, i, m),
                        maybe_mask_value(0, 3, i, m),
                    ]
            elif vnvl == 0b1000:  # V3-32
                width = 12
                for i in range(qwd):
                    val = [0, 0, 0]
                    if cl >= wl or (i % wl) < cl:
                        val = getnfloat32(buf, width * j + offs, 3)
                        j += 1
                    addroffs = cl * (i // wl) + (i % wl) if cl >= wl else 0
                    vumem[addr + addroffs] = [
                        maybe_mask_value(val[0], 0, i, m),
                        maybe_mask_value(val[1], 1, i, m),
                        maybe_mask_value(val[2], 2, i, m),
                        maybe_mask_value(0, 3, i, m),
                    ]
            elif vnvl == 0b1100:  # V4-32
                width = 16
                for i in range(qwd):
                    val = [0, 0, 0, 0]
                    if cl >= wl or (i % wl) < cl:
                        val = getnfloat32(buf, width * j + offs, 4)
                        j += 1
                    addroffs = cl * (i // wl) + (i % wl) if cl >= wl else 0
                    vumem[addr + addroffs] = [
                        maybe_mask_value(val[0], 0, i, m),
                        maybe_mask_value(val[1], 1, i, m),
                        maybe_mask_value(val[2], 2, i, m),
                        maybe_mask_value(val[3], 3, i, m),
                    ]
            else:
                err('Unsupported unpack vnvl {} at offset {}'.format(hex(vnvl), hex(offs)))
            offs += j * width
        else:
            err('Unrecognized vifcmd {} at offset {}'.format(hex(cmd), hex(offs)))

if __name__ == '__main__':
    if not os.path.exists(args.mdlpath[0]):
        err("Path not found: {}".format(args.mdlpath[0]))

    mdlpath = sys.argv[1] if sys.argv[1][0] != '-' else args.mdlpath[0]  # Drag-and-drop hack
    basepath = os.path.splitext(mdlpath)[0]
    basename = os.path.splitext(os.path.basename(mdlpath))[0]

    f = open(mdlpath, 'rb')
    buf = ReadRpkFile(f, 1)[0x10:]
    f.close()
    if len(buf) < 0x10:
        err('I3D model file is too small! {} bytes'.format(len(buf)))

    # Construct the entire node tree recursively.
    rootNode = Node(buf, 0)

    # Traverse node tree and find all nodes of interest.
    materialNodes = rootNode.getChildrenByType(0x25)
    combinedMeshNodes = rootNode.getChildrenByType(0x2D)
    boneNodes = rootNode.getChildrenByType(0x2A)

    # Get all material names. Assume these are the same as texture names.
    materialNames = []
    for materialNode in materialNodes:
        materialOffs = materialNode.children[0].children[0].dataOffs
        nameOffs = getuint32(buf, materialOffs + 0x18) + materialOffs
        materialNames.append(parseName(buf, nameOffs))
    
    # Parse mesh instances attached to bones.
    meshInstances = []
    for boneIndex in range(len(boneNodes)):
        meshInstanceNodes = boneNodes[boneIndex].getChildrenByType(0x59)
        if len(meshInstanceNodes) == 0:
            continue

        def getTransform(buf, offs, ind):
            transformOffs = offs + ind * 0x40
            matrix = []
            for i in range(4):
                matrix += [[getfloat32(buf, transformOffs + i * 0x10 + j * 0x4) for j in range(4)]]
            return np.matrix(matrix).transpose()

        # Get global transform of current bone.
        transformTableOffs = getuint32(buf, rootNode.dataOffs + 0x14) + rootNode.dataOffs
        baseTransform = getTransform(buf, transformTableOffs, boneIndex)

        for meshInstanceNode in meshInstanceNodes:
            # Parse mesh instance data.
            boneListOffs = getuint32(buf, meshInstanceNode.dataOffs) + meshInstanceNode.dataOffs
            combinedMeshIndex = getuint16(buf, meshInstanceNode.dataOffs + 0x4)
            boneListCount = getuint16(buf, meshInstanceNode.dataOffs + 0x6)
            boneList = getnuint16(buf, boneListOffs, boneListCount)

            combinedMeshNode = combinedMeshNodes[combinedMeshIndex]
            meshInstance = MeshInstance(meshInstanceNode.dataOffs, combinedMeshNode.dataOffs)
            meshInstances.append(meshInstance)

            bindPoseTableOffs = 0
            if combinedMeshNode.children[0].dataOffs > 0:  # Node type 0x46
                # Sadly I can't compute a single transform for the entire combined mesh
                # since different meshes may have different relative bind poses.
                bindPoseTableOffs = getuint32(buf, combinedMeshNode.children[0].dataOffs) + combinedMeshNode.children[0].dataOffs
            
            meshNodes = combinedMeshNode.getChildrenByType(0x4B)
            meshNodes += combinedMeshNode.getChildrenByType(0x4C)
            for meshNode in meshNodes:
                mesh = Mesh(meshNode.dataOffs)
                meshInstance.meshes.append(mesh)
                transform = baseTransform
                if meshNode.dataType == 0x4C and (buf[meshNode.dataOffs + 0x5] & 0x8) > 0:
                    # Use global transform of bone assigned to the instance.
                    boneListIndex = getuint16(buf, meshNode.dataOffs + 0x8)
                    transform = getTransform(buf, transformTableOffs, boneList[boneListIndex])
                
                for submeshNode in meshNode.getChildrenByType(0x4D):
                    materialIndex = buf[submeshNode.dataOffs + 0xC]
                    submesh = Submesh(submeshNode.dataOffs, materialIndex)
                    mesh.submeshes.append(submesh)

                    for submeshPieceNode in submeshNode.getChildrenByType(0x56):
                        submeshPiece = SubmeshPiece(submeshPieceNode.dataOffs)
                        submesh.submeshPieces.append(submeshPiece)

                        vertexWeightNodes = submeshPieceNode.getChildrenByType(0x31)
                        if vertexWeightNodes and bindPoseTableOffs > 0:
                            boneIndex = getuint16(buf, vertexWeightNodes[0].dataOffs + 0x4)
                            # Theoretically, the entire submesh should have the same relative bind pose.
                            # We do this at the submesh level rather than the vertex level since this
                            # is cheaper.
                            # TODO: This does not work for all models, e.g. pcdoll.
                            inverseBindPose = getTransform(buf, bindPoseTableOffs, boneIndex)
                            boneTransform = getTransform(buf, transformTableOffs, boneList[boneIndex])
                            transform = boneTransform * inverseBindPose

                        vertexNode = submeshPieceNode.children[4].children[0]
                        vertexCount = buf[vertexNode.dataOffs + 0x6]
                        if buf[vertexNode.dataOffs + 0x8] == 1:
                            parseVif(buf, vertexNode.dataOffs)
                            for i in range(vertexCount):
                                v = transform * np.array(vumem[i]).reshape(-1, 1)
                                submeshPiece.vtx.extend(v.flatten().tolist())
                        else:
                            for i in range(vertexCount):
                                v = transform * np.array(getnfloat32(buf, vertexNode.dataOffs + i * 0x10 + 0x10, 4)).reshape(-1, 1)
                                submeshPiece.vtx.extend(v.flatten().tolist())

                        ind = []
                        # Join indices and texture coordinates across all sub-pieces. There is far too much indentation here.
                        for indexListNode in submeshPieceNode.getChildrenByType(0x47):
                            uvBufferNode = indexListNode.children[1].children[0]
                            uvCount = buf[uvBufferNode.dataOffs + 0x6]
                            if buf[uvBufferNode.dataOffs + 0x8] == 1:
                                parseVif(buf, uvBufferNode.dataOffs)
                                submeshPiece.vt.extend(vumem[:uvCount])
                            else:
                                for i in range(uvCount):
                                    submeshPiece.vt.append(getnfloat32(buf, uvBufferNode.dataOffs + i * 0x10 + 0x10, 4))
                            
                            indOffs = indexListNode.dataOffs
                            indCount = buf[indOffs + 0x5]
                            indOffs += 0x10
                            for i in range(indCount):
                                ind.append(struct.unpack('BBBB', buf[indOffs + i * 4: indOffs + i * 4 + 4]))
                        
                        for i in range(len(ind)):
                            _, ctrl, _, reverse = ind[i]
                            if ctrl == 0x80:
                                continue
                            if reverse:
                                submeshPiece.ind.append([ (ind[i-2][0], i-2), (ind[i-1][0], i-1), (ind[i][0], i) ])
                            else:
                                submeshPiece.ind.append([ (ind[i][0], i), (ind[i-1][0], i-1), (ind[i-2][0], i-2) ])

    # Export OBJ and MTL.
    objpath = os.path.join(os.path.dirname(mdlpath), basename + '_out.obj')
    mtlpath = os.path.splitext(objpath)[0] + '.mtl'

    with open(objpath, 'w') as f:
        vlast = 1
        vtlast = 1
        f.write('mtllib {}\n\n'.format(os.path.relpath(mtlpath, os.path.dirname(objpath))))
        for meshInstance in meshInstances:
            for mesh in meshInstance.meshes:
                for submesh in mesh.submeshes:
                    groupName = '{}_{}_{}_{}'.format(hex(meshInstance.offs)[2:], hex(meshInstance.combinedMeshOffs)[2:], hex(mesh.offs)[2:], hex(submesh.offs)[2:])
                    f.write('g {}\n'.format(groupName))
                    if submesh.materialIndex >= 0:
                        f.write('usemtl {}\n'.format(materialNames[submesh.materialIndex]))
                    for submeshPiece in submesh.submeshPieces:
                        for v in submeshPiece.vtx:
                            f.write('v {} {} {}\n'.format(v[0], v[1], v[2]))
                        for vt in submeshPiece.vt:
                            f.write('vt {} {}\n'.format(vt[0], 1 - vt[1]))
                        for ind in submeshPiece.ind:
                            f.write('f {}\n'.format(' '.join(['{}/{}'.format(vlast + ind[i][0], vtlast + ind[i][1]) for i in range(3)])))
                        f.write('\n')
                        vlast += len(submeshPiece.vtx)
                        vtlast += len(submeshPiece.vt)

    with open(mtlpath, 'w+') as fout:
        for mtl in materialNames:
            fout.write('newmtl {}\n'.format(mtl))
            fout.write('Ka 0.5 0.5 0.5\n')
            if len(mtl) == 0:
                fout.write('Kd 1.0 1.0 1.0\n')
            else:
                fout.write('map_Kd {}.png\n'.format(mtl))
            fout.write('Ks 0.0 0.0 0.0\n')
            fout.write('Ns 500\n')
            fout.write('illum 2\n\n')
    
    print("Done: {}".format(basename))
