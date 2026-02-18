# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8-80 compliant>

bl_info = {
  "name": "Haunting Ground PAC/PCK format",
  "author": "Murugo",
  "version": (0, 1, 0),
  "blender": (4, 0, 0),
  "location": "File -> Import-Export",
  "description": "Import-Export Haunting Ground (PS2) models, Import mesh and materials from a Haunting Ground stage PAC file or model PCK file",
  "category": "Import-Export"
}

# if "bpy" in locals():
#   import importlib
#   if "import_hg_pac" in locals():
#     importlib.reload(import_hg_pac)

if "bpy" in locals():
  import importlib
  importlib.reload(import_hg_pac)
  importlib.reload(import_hg_pck)
else:
  from . import import_hg_pac
  from . import import_hg_pck


import bpy
from bpy.props import (
  StringProperty,
)
from bpy_extras.io_utils import (
  ImportHelper,
  orientation_helper,
)

@orientation_helper(axis_forward="-Z", axis_up="Y")
class ImportHgPac(bpy.types.Operator, ImportHelper):
  """Load a Haunting Ground PAC file"""
  bl_idname = "import_scene.pac"
  bl_label = "Import Haunting Ground (PS2) Stage PAC"
  bl_options = {'PRESET', 'UNDO'}

  filename_ext = ".pac"
  filter_glob: StringProperty(
    default="*.pac",
    options={'HIDDEN'}
  )

  def execute(self, context):
    from . import import_hg_pac

    keywords = self.as_keywords(ignore=("axis_forward",
                                        "axis_up",
                                        "filter_glob",
                                        "split_mode",
                                        ))

    return import_hg_pac.load(context, **keywords)

  def draw(self, context):
    pass


@orientation_helper(axis_forward="-Z", axis_up="Y")
class ImportHgPck(bpy.types.Operator, ImportHelper):
  """Load a Haunting Ground PCK file"""
  bl_idname = "import_model.pck"
  bl_label = "Import Haunting Ground (PS2) Model PCK"
  bl_options = {'PRESET', 'UNDO'}

  filename_ext = ".pck"
  filter_glob: StringProperty(
    default="*.pck",
    options={'HIDDEN'}
  )

  def execute(self, context):
    from . import import_hg_pck

    keywords = self.as_keywords(ignore=("axis_forward",
                                        "axis_up",
                                        "filter_glob",
                                        "split_mode",
                                        ))

    return import_hg_pck.load(context, **keywords)

  def draw(self, context):
    pass


def menu_func_import(self, context):
    self.layout.operator(ImportHgPac.bl_idname, text="Haunting Ground PAC (.pac)")
    self.layout.operator(ImportHgPck.bl_idname, text="Haunting Ground PCK (.pck)")

classes = (
  ImportHgPac,
  ImportHgPck,
)

def register():
    for cl in classes:
        bpy.utils.register_class(cl)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
  bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
  
  for cl in classes:
    bpy.utils.unregister_class(cl)

if __name__ == "__main__":
  register()
