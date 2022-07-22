# pylint: disable=import-error

bl_info = {
    "name": "Vib-Ribbon",
    "author": "Murugo",
    "version": (0, 1, 0),
    "blender": (2, 80, 0),
    "location": "File -> Import-Export",
    "description": "Import vib-ribbon (PS1) models.",
    "category": "Import-Export"
}

from bpy.props import (
    StringProperty,
)
from bpy_extras.io_utils import (
    ImportHelper,
)
import bpy


if "bpy" in locals():
  # pylint: disable=undefined-variable
  import importlib
  if "import_tmd" in locals():
    importlib.reload(import_tmd)
  if "import_anm" in locals():
    importlib.reload(import_anm)


class ImportTmd(bpy.types.Operator, ImportHelper):
  """Load a Vib-Ribbon TMD file"""
  bl_idname = "import_vib_ribbon.tmd"
  bl_label = "Import Vib-Ribbon (PS1) Model (TMD)"
  bl_options = {"PRESET", "UNDO"}

  filename_ext = ".tmd"
  filter_glob: StringProperty(default="*.tmd", options={'HIDDEN'})

  def execute(self, context):
    from . import import_tmd

    keywords = self.as_keywords(ignore=("filter_glob",))
    status, msg = import_tmd.load(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
    self.report({'INFO'}, 'TMD import successful.')
    return {status}

  def draw(self, context):
    pass


class ImportAnm(bpy.types.Operator, ImportHelper):
  """Load a Vib-Ribbon ANM file"""
  bl_idname = "import_vib_ribbon.anm"
  bl_label = "Import Vib-Ribbon (PS1) Animation (ANM)"
  bl_options = {"PRESET", "UNDO"}

  filename_ext = ".anm"
  filter_glob: StringProperty(default="*.anm", options={'HIDDEN'})

  def execute(self, context):
    from . import import_anm

    keywords = self.as_keywords(ignore=("filter_glob",))
    status, msg = import_anm.load(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
    self.report({'INFO'}, 'ANM import successful.')
    return {status}

  def draw(self, context):
    pass


def menu_func_import(self, context):
  self.layout.operator(ImportTmd.bl_idname, text="Vib-Ribbon Model (.tmd)")
  self.layout.operator(ImportAnm.bl_idname, text="Vib-Ribbon Animation (.anm)")


classes = (ImportTmd, ImportAnm,)


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
