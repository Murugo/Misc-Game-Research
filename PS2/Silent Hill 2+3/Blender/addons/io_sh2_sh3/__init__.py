# pylint: disable=import-error

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


class PackModelSelectorItem(bpy.types.PropertyGroup):
  """Item in a PACK model selection dialog"""
  id: IntProperty(name="Model ID", default=-1)
  id_hex: StringProperty(name="Model ID (Hex)", default="")
  alias: StringProperty(name="Alias", default="")
  filename: StringProperty(name="Filename", default="")


class PackModelSelector_UL_List(bpy.types.UIList):
  """PACK model selection display list"""

  def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
    if self.layout_type in {'DEFAULT', 'COMPACT'}:
      split = layout.split(factor=0.33)
      split.label(text=item.id_hex, icon='ANIM_DATA')
      split.label(text=item.alias)
      split.label(text=item.filename)


class PackModelSelector(bpy.types.Operator):
  """Dialog to select a model ID from a PACK file"""
  bl_idname = "import_sh3.pack_select_model"
  bl_label = "Select a model ID to import animation data."
  bl_options = {'REGISTER', 'INTERNAL', 'UNDO'}

  filepath: StringProperty(default="")
  model_id_list: StringProperty(default="")
  model_ids: CollectionProperty(type=PackModelSelectorItem)
  model_id_index: IntProperty(default=0)

  @classmethod
  def poll(cls, context):
    return True

  def execute(self, context):
    from . import import_pack

    model_id = self.model_ids[self.model_id_index].id
    if model_id <= 0:
      return 'CANCELLED'
    status, msg = import_pack.load(context, self.filepath, model_id)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}

  def invoke(self, context, event):
    for model_id in self.model_id_list.split(','):
      try:
        item = self.model_ids.add()
        item.id = int(model_id)
        item.id_hex = hex(item.id)

        from . import import_anm
        if item.id in import_anm.SH3_MODEL_ID_INFO:
          _, alias, filename = import_anm.SH3_MODEL_ID_INFO[item.id]
          item.alias = alias
          item.filename = filename
      except ValueError:
        self.report({'ERROR'}, f'Got invalid model ID: {model_id}')
        return {'CANCELLED'}
    return context.window_manager.invoke_props_dialog(self)

  def draw(self, context):
    row = self.layout
    row.template_list("PackModelSelector_UL_List", "", self,
                      "model_ids", self, "model_id_index")


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
    model_ids, msg = import_pack.get_model_list(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
      return {'CANCELLED'}
    if not model_ids:
      self.report(
          {'ERROR'}, 'PACK file contains no animation tracks that can be imported.')
      return {'CANCELLED'}

    bpy.ops.import_sh3.pack_select_model(
        'INVOKE_DEFAULT', filepath=self.filepath, model_id_list=",".join([str(x) for x in model_ids]))
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


classes = (ImportMdl, ImportAnmSh2, ImportAnmSh3,
           ImportPackSh3,  PackModelSelectorItem, PackModelSelector_UL_List, PackModelSelector,
           ImportDdsSh2, DdsObjectSelectorItem, DdsObjectSelector_UL_List, DdsObjectSelector)


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
