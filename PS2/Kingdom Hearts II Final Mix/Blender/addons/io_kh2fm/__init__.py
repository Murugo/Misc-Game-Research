# pylint: disable=import-error

bl_info = {
    "name":
        "Kingdom Hearts II Final Mix",
    "author":
        "Murugo",
    "version": (0, 1, 0),
    "blender": (2, 80, 0),
    "location":
        "File -> Import-Export",
    "description":
        "Import-Export Kingdom Hearts II Final Mix (PS2) models, Import models from KHIIFM file formats.",
    "category":
        "Import-Export"
}

if "bpy" in locals():
  # pylint: disable=undefined-variable
  import importlib
  if "import_mdlx" in locals():
    importlib.reload(import_mdlx)
  if "import_mset" in locals():
    importlib.reload(import_mset)
  if "import_map" in locals():
    importlib.reload(import_map)

import bpy
from bpy.props import (
    BoolProperty,
    StringProperty,
)
from bpy_extras.io_utils import (
    ImportHelper,)


class ImportMdlx(bpy.types.Operator, ImportHelper):
  """Load a Kingdom Hearts II Final Mix MDLX file"""
  bl_idname = "import_kh2fm.mdlx"
  bl_label = "Import Kingdom Hearts II Final Mix (PS2) Model (MDLX)"
  bl_options = {'PRESET', 'UNDO'}

  filename_ext = ".mdlx"
  filter_glob: StringProperty(default="*.mdlx", options={'HIDDEN'})

  use_emission: BoolProperty(
      name="Use Emission Property",
      description="Connect image textures to emission property in each shader.",
      default=True,
  )

  def execute(self, context):
    from . import import_mdlx

    keywords = self.as_keywords(ignore=("filter_glob",))
    status, msg = import_mdlx.load(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}

  def draw(self, context):
    pass


class MDLX_PT_import_options(bpy.types.Panel):
  bl_space_type = 'FILE_BROWSER'
  bl_region_type = 'TOOL_PROPS'
  bl_label = "Import MDLX"
  bl_parent_id = "FILE_PT_operator"

  @classmethod
  def poll(cls, context):
    sfile = context.space_data
    operator = sfile.active_operator

    return operator.bl_idname == "IMPORT_KH2FM_OT_mdlx"

  def draw(self, context):
    layout = self.layout
    layout.use_property_split = True
    layout.use_property_decorate = False

    sfile = context.space_data
    operator = sfile.active_operator

    layout.prop(operator, 'use_emission')


class ImportMset(bpy.types.Operator, ImportHelper):
  """Load a Kingdom Hearts II Final Mix MSET file"""
  bl_idname = "import_kh2fm.mset"
  bl_label = "Import Kingdom Hearts II Final Mix (PS2) MSET/ANB"
  bl_options = {'PRESET', 'UNDO'}

  filename_ext = ".mset"
  filter_glob: StringProperty(default="*.mset;*.anb", options={'HIDDEN'})

  def execute(self, context):
    from . import import_mset

    keywords = self.as_keywords(ignore=(
        "axis_forward",
        "axis_up",
        "filter_glob",
        "split_mode",
    ))
    status, msg = import_mset.load(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}

  def draw(self, context):
    pass


class ImportMap(bpy.types.Operator, ImportHelper):
  """Load a Kingdom Hearts II Final Mix MAP file"""
  bl_idname = "import_kh2fm.map"
  bl_label = "Import Kingdom Hearts II Final Mix (PS2) MAP"
  bl_options = {'PRESET', 'UNDO'}

  filename_ext = ".map"
  filter_glob: StringProperty(
    default="*.map",
    options={'HIDDEN'}
  )

  import_geometry: BoolProperty(
    name="Import Geometry",
    description="Import map geometry",
    default=True,
  )

  import_doct: BoolProperty(
    name="Import DOCT",
    description="Import the draw octree and parent geometry to corresponding nodes in the tree",
    default=False,
  )

  import_coct: BoolProperty(
    name="Import COCT",
    description="Import the collision octree and create collision meshes",
    default=False,
  )

  def execute(self, context):
    from . import import_map

    keywords = self.as_keywords(ignore=("axis_forward",
                                        "axis_up",
                                        "filter_glob",
                                        ))

    status, msg = import_map.load(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}

  def draw(self, context):
    pass


class MAP_PT_import_options(bpy.types.Panel):
  bl_space_type = 'FILE_BROWSER'
  bl_region_type = 'TOOL_PROPS'
  bl_label = "Options"
  bl_parent_id = "FILE_PT_operator"

  @classmethod
  def poll(cls, context):
    sfile = context.space_data
    operator = sfile.active_operator

    return operator.bl_idname == "IMPORT_KH2FM_OT_map"
  

  def draw(self, context):
    layout = self.layout
    layout.use_property_split = True
    layout.use_property_decorate = False

    sfile = context.space_data
    operator = sfile.active_operator

    layout.prop(operator, 'import_geometry')
    sub = layout.row()
    sub.enabled = operator.import_geometry
    sub.prop(operator, "import_doct")
    layout.prop(operator, 'import_coct')


def menu_func_import(self, context):
  self.layout.operator(ImportMdlx.bl_idname,
                       text="Kingdom Hearts II Final Mix Model (.mdlx)")
  self.layout.operator(
      ImportMset.bl_idname,
      text="Kingdom Hearts II Final Mix Animation (.mset, .anb)")
  self.layout.operator(ImportMap.bl_idname, text="Kingdom Hearts II Final Mix MAP (.map)")


classes = (
    ImportMdlx,
    ImportMset,
    ImportMap,
    MDLX_PT_import_options,
    MAP_PT_import_options
)


def register():
  for cls in classes:
    bpy.utils.register_class(cls)
  bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
  for cls in classes:
    bpy.utils.unregister_class(cls)
  bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
  register()
