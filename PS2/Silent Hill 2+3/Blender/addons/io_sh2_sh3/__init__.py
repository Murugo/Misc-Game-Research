# pylint: disable=import-error

import os

bl_info = {
    "name": "Silent Hill 2/3",
    "author": "Murugo",
    "version": (0, 1, 0),
    "blender": (2, 80, 0),
    "location": "File -> Import-Export",
    "description": "Import Silent Hill 2/3 (PS2) models.",
    "category": "Import-Export"
}

from bpy.props import (
    CollectionProperty,
    IntProperty,
    StringProperty,
)
from bpy_extras.io_utils import (
    ExportHelper,
    ImportHelper,
)
import bpy


if "bpy" in locals():
  # pylint: disable=undefined-variable
  import importlib
  if "import_mdl" in locals():
    importlib.reload(import_mdl)
  if "import_anm" in locals():
    importlib.reload(import_anm)
  if "import_pack" in locals():
    importlib.reload(import_pack)
  if "import_dds" in locals():
    importlib.reload(import_dds)
  if "import_map" in locals():
    importlib.reload(import_map)
  if "export_pack" in locals():
    importlib.reload(export_pack)


class ImportMdl(bpy.types.Operator, ImportHelper):
  """Load a Silent Hill 2/3 MDL file"""
  bl_idname = "import_sh3.mdl"
  bl_label = "Import Silent Hill 2/3 (PS2) Model (MDL)"
  bl_options = {"PRESET", "UNDO"}

  filename_ext = ".mdl"
  filter_glob: StringProperty(default="*.mdl", options={'HIDDEN'})

  def execute(self, context):
    from . import import_mdl

    keywords = self.as_keywords(ignore=("filter_glob",))
    status, msg = import_mdl.load(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}

  def draw(self, context):
    pass


class ImportAnmSh2(bpy.types.Operator, ImportHelper):
  """Load a Silent Hill 2 ANM file"""
  bl_idname = "import_sh2.anm"
  bl_label = "Import Silent Hill 2 (PS2) Animation Set (ANM)"
  bl_options = {"PRESET", "UNDO"}

  filename_ext = ".anm"
  filter_glob: StringProperty(default="*.anm", options={'HIDDEN'})

  def execute(self, context):
    from . import import_anm

    keywords = self.as_keywords(ignore=("filter_glob",))
    status, msg = import_anm.load(context, is_sh2=True, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}

  def draw(self, context):
    pass


class ImportAnmSh3(bpy.types.Operator, ImportHelper):
  """Load a Silent Hill 3 ANM file"""
  bl_idname = "import_sh3.anm"
  bl_label = "Import Silent Hill 3 (PS2) Animation Set (ANM)"
  bl_options = {"PRESET", "UNDO"}

  filename_ext = ".anm"
  filter_glob: StringProperty(default="*.anm", options={'HIDDEN'})

  def execute(self, context):
    from . import import_anm

    keywords = self.as_keywords(ignore=("filter_glob",))
    status, msg = import_anm.load(context, is_sh2=False, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}

  def draw(self, context):
    pass


class PackTargetSelectorItem(bpy.types.PropertyGroup):
  """Item in a PACK target selection dialog"""
  type: IntProperty(name="Type", default=-1)
  id: IntProperty(name="Target ID", default=-1)
  id_hex: StringProperty(name="Target ID (Hex)", default="")
  alias: StringProperty(name="Alias", default="")
  filename: StringProperty(name="Filename", default="")


class PackTargetSelector_UL_List(bpy.types.UIList):
  """PACK model selection display list"""

  def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
    if self.layout_type in {'DEFAULT', 'COMPACT'}:
      icon_name = 'VIEW_CAMERA' if item.type == 0x3 else 'ANIM_DATA'
      split = layout.split(factor=0.33)
      split.label(text=item.id_hex, icon=icon_name)
      split.label(text=item.alias)
      split.label(text=item.filename)


class PackTargetSelector(bpy.types.Operator):
  """Dialog to select a target ID from a PACK file"""
  bl_idname = "import_sh3.pack_select_target"
  bl_label = "Select a target ID to import animation data."
  bl_options = {'REGISTER', 'INTERNAL', 'UNDO'}

  filepath: StringProperty(default="")
  target_list: StringProperty(default="")
  targets: CollectionProperty(type=PackTargetSelectorItem)
  target_index: IntProperty(default=0)

  @classmethod
  def poll(cls, context):
    return True

  def execute(self, context):
    from . import import_pack

    if self.target_index < 0 or self.target_index > len(self.targets):
      return {'CANCELLED'}
    target_type = self.targets[self.target_index].type
    target_id = self.targets[self.target_index].id
    status, msg = import_pack.load(context, self.filepath, target_type, target_id)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}

  def invoke(self, context, event):
    target_list_parsed = [v.split(',') for v in self.target_list.split(';')]
    for target_type, target_id in target_list_parsed:
      try:
        item = self.targets.add()
        item.type = int(target_type)
        item.id = int(target_id)
        item.id_hex = hex(item.id)

        if item.type == 0x1:
          from . import import_anm
          if item.id in import_anm.SH3_MODEL_ID_INFO:
            _, alias, filename = import_anm.SH3_MODEL_ID_INFO[item.id]
            item.alias = alias
            item.filename = filename
        elif item.type == 0x3:
          item.alias = 'Camera'
          item.filename = ''
      except ValueError:
        self.report({'ERROR'}, f'Got invalid target: type={target_type} id={target_id}')
        return {'CANCELLED'}
    return context.window_manager.invoke_props_dialog(self)

  def draw(self, context):
    row = self.layout
    row.template_list("PackTargetSelector_UL_List", "", self,
                      "targets", self, "target_index")


class ImportPackSh3(bpy.types.Operator, ImportHelper):
  """Load a Silent Hill 3 PACK file"""
  bl_idname = "import_sh3.pack"
  bl_label = "Import Silent Hill 3 (PS2) Cutscene Pack (PACK)"
  bl_options = {"PRESET", "UNDO"}

  filename_ext = ".pack"
  filter_glob: StringProperty(default="*.pack", options={'HIDDEN'})

  def execute(self, context):
    from . import import_pack

    keywords = self.as_keywords(ignore=("filter_glob",))
    targets, msg = import_pack.get_target_list(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
      return {'CANCELLED'}
    if not targets:
      self.report(
          {'ERROR'}, 'PACK file contains no animation tracks that can be imported.')
      return {'CANCELLED'}

    bpy.ops.import_sh3.pack_select_target(
        'INVOKE_DEFAULT', filepath=self.filepath, target_list=";".join([f'{x},{y}' for x, y in targets]))
    return {'FINISHED'}

  def draw(self, context):
    pass


class PackExportTargetSelector(bpy.types.Operator):
  """Dialog to select a target ID from a PACK file for export."""
  bl_idname = "export_sh3.pack_select_export_target"
  bl_label = "Select a target ID to export animation data."
  bl_options = {'REGISTER', 'INTERNAL', 'UNDO'}

  filepath: StringProperty(default="")
  target_list: StringProperty(default="")
  targets: CollectionProperty(type=PackTargetSelectorItem)
  target_index: IntProperty(default=0)

  @classmethod
  def poll(cls, context):
    return True

  def execute(self, context):
    from . import export_pack

    if self.target_index < 0 or self.target_index > len(self.targets):
      return {'CANCELLED'}
    target_type = self.targets[self.target_index].type
    target_id = self.targets[self.target_index].id
    status, msg = export_pack.patch(context, self.filepath, target_type, target_id)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}
  
  def invoke(self, context, event):
    target_list_parsed = [v.split(',') for v in self.target_list.split(';')]
    for target_type, target_id in target_list_parsed:
      try:
        item = self.targets.add()
        item.type = int(target_type)
        item.id = int(target_id)
        item.id_hex = hex(item.id)

        if item.type == 0x1:
          from . import import_anm
          if item.id in import_anm.SH3_MODEL_ID_INFO:
            _, alias, filename = import_anm.SH3_MODEL_ID_INFO[item.id]
            item.alias = alias
            item.filename = filename
        elif item.type == 0x3:
          item.alias = 'Camera'
          item.filename = ''
      except ValueError:
        self.report({'ERROR'}, f'Got invalid target: type={target_type} id={target_id}')
        return {'CANCELLED'}
    return context.window_manager.invoke_props_dialog(self)

  def draw(self, context):
    row = self.layout
    row.template_list("PackTargetSelector_UL_List", "", self,
                      "targets", self, "target_index")

class ExportPackSh3(bpy.types.Operator, ExportHelper):
  """Write animation track(s) to an existing Silent Hill 3 PACK file"""
  bl_idname = "export_sh3.pack"
  bl_label = "Export Silent Hill 3 (PS2) Cutscene Pack (PACK)"
  bl_options = {"PRESET", "UNDO"}

  filename_ext = ".pack"
  filter_glob: StringProperty(default="*.pack", options={'HIDDEN'})

  def execute(self, context):
    from . import import_pack

    if not os.path.exists(self.filepath):
      self.report({'ERROR'}, 'Please select an existing PACK file to patch the animation for the selected object.')
      return {'CANCELLED'}

    keywords = self.as_keywords(ignore=("filter_glob","check_existing"))
    targets, msg = import_pack.get_target_list(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
      return {'CANCELLED'}
    if not targets:
      self.report(
          {'ERROR'}, 'PACK file contains no animation tracks that can be imported.')
      return {'CANCELLED'}

    bpy.ops.export_sh3.pack_select_export_target(
        'INVOKE_DEFAULT', filepath=self.filepath, target_list=";".join([f'{x},{y}' for x, y in targets]))
    print('OK:', targets)
    return {'FINISHED'}

  def draw(self, context):
    pass


class DdsObjectSelectorItem(bpy.types.PropertyGroup):
  """Item in a DDS object selection dialog"""
  name: StringProperty(name="Object Name", default="")


class DdsObjectSelector_UL_List(bpy.types.UIList):
  """DDS object selection display list"""

  def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
    if self.layout_type in {'DEFAULT', 'COMPACT'}:
      layout.label(text=item.name, icon='ANIM_DATA')


class DdsObjectSelector(bpy.types.Operator):
  """Dialog to select an object from a DDS file"""
  bl_idname = "import_sh2.dds_select_object"
  bl_label = "Select a character to import animation data."
  bl_options = {'REGISTER', 'INTERNAL', 'UNDO'}

  filepath: StringProperty(default="")
  object_list: StringProperty(default="")
  objects: CollectionProperty(type=DdsObjectSelectorItem)
  object_index: IntProperty(default=0)

  @classmethod
  def poll(cls, context):
    return True

  def execute(self, context):
    from . import import_dds

    object_name = self.objects[self.object_index].name
    if not object_name:
      return {'CANCELLED'}
    status, msg = import_dds.load(context, self.filepath, object_name)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}

  def invoke(self, context, event):
    for object_name in self.object_list.split(','):
      self.objects.add().name = object_name
    return context.window_manager.invoke_props_dialog(self)

  def draw(self, context):
    row = self.layout
    row.template_list("DdsObjectSelector_UL_List", "",
                      self, "objects", self, "object_index")


class ImportDdsSh2(bpy.types.Operator, ImportHelper):
  """Load a Silent Hill 2 DDS file"""
  bl_idname = "import_sh2.dds"
  bl_label = "Import Silent Hill 2 (PS2) Drama Demo (DDS)"
  bl_options = {"PRESET", "UNDO"}

  filename_ext = ".dds"
  filter_glob: StringProperty(default="*.dds", options={'HIDDEN'})

  def execute(self, context):
    from . import import_dds

    keywords = self.as_keywords(ignore=("filter_glob",))
    names, msg = import_dds.get_object_list(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
      return {'CANCELLED'}
    if not names:
      self.report({'ERROR'}, 'DDS file contains no characters that can be imported.')
      return {'CANCELLED'}

    bpy.ops.import_sh2.dds_select_object(
        'INVOKE_DEFAULT', filepath=self.filepath, object_list=",".join(names))
    return {'FINISHED'}

  def draw(self, context):
    pass


class ImportMapSh3(bpy.types.Operator, ImportHelper):
  """Load a Silent Hill 3 MAP file"""
  bl_idname = "import_sh3.map"
  bl_label = "Import Silent Hill 3 (PS2) Map (MAP)"
  bl_options = {"PRESET", "UNDO"}

  filename_ext = ".map"
  filter_glob: StringProperty(default="*.map", options={'HIDDEN'})

  def execute(self, context):
    from . import import_map

    keywords = self.as_keywords(ignore=("filter_glob",))
    status, msg = import_map.load(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}

  def draw(self, context):
    pass


def menu_func_import(self, context):
  self.layout.operator(ImportMdl.bl_idname,
                       text="Silent Hill 2/3 Model (.mdl)")
  self.layout.operator(ImportAnmSh2.bl_idname,
                       text="Silent Hill 2 Animation Set (.anm)")
  self.layout.operator(ImportAnmSh3.bl_idname,
                       text="Silent Hill 3 Animation Set (.anm)")
  self.layout.operator(ImportPackSh3.bl_idname,
                       text="Silent Hill 3 Cutscene Pack (.pack)")
  self.layout.operator(ImportDdsSh2.bl_idname,
                       text="Silent Hill 2 Cutscene Pack (.dds)")
  self.layout.operator(ImportMapSh3.bl_idname,
                       text="Silent Hill 3 Map (.map)")


def menu_func_export(self, context):
  self.layout.operator(ExportPackSh3.bl_idname, text="Silent Hill 3 Cutscene Pack (.pack)")


classes = (ImportMdl, ImportAnmSh2, ImportAnmSh3,
           ImportPackSh3,  PackTargetSelectorItem, PackTargetSelector_UL_List, PackTargetSelector,
           ImportDdsSh2, DdsObjectSelectorItem, DdsObjectSelector_UL_List, DdsObjectSelector,
           ImportMapSh3, ExportPackSh3, PackExportTargetSelector)


def register():
  for cls in classes:
    bpy.utils.register_class(cls)
  bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
  bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
  for cls in classes:
    bpy.utils.unregister_class(cls)
  bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
  bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
  register()
