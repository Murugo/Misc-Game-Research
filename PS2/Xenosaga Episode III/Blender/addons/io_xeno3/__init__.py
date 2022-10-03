''' Blender add-on for Xenosaga Episode III (PS2) '''

import os
import bpy
from bpy.props import (
    StringProperty,
)
from bpy_extras.io_utils import (
    ImportHelper,
)


if 'bpy' in locals():
  # pylint:disable=undefined-variable
  import importlib
  if 'import_chr' in locals():
    importlib.reload(import_chr)


bl_info = {  # pylint:disable=invalid-name
    'name': 'Xenosaga Episode III',
    'author': 'Murugo',
    'version': (0, 1, 0),
    'blender': (2, 80, 0),
    'location': 'File -> Import-Export',
    'description': 'Import Xenosaga Episode III (PS2) models.',
    'category': 'Import-Export'
}


class ImportChr(bpy.types.Operator, ImportHelper):
  '''Load a Xenosaga Episode III CHR file'''
  bl_idname = 'import_xeno3.chr'
  bl_label = 'Import Xenosaga Episode III (PS2) Model (CHR)'
  bl_options = {'PRESET', 'UNDO'}

  filename_ext = '.chr'
  filter_glob: StringProperty(default='*.chr', options={'HIDDEN'})

  def execute(self, context):
    from . import import_chr

    keywords = self.as_keywords(ignore=('filter_glob',))
    status, msg = import_chr.load(context, **keywords)
    if msg:
      self.report({'ERROR'}, msg)
    return {status}

  def draw(self, context):
    pass


def menu_func_import(self, _):
  '''Adds import operators. '''
  self.layout.operator(ImportChr.bl_idname,
                       text='Xenosaga Episode III Model (.chr)')


CLASSES = (ImportChr,)


def register():
  '''Regsters all classes.'''
  for cls in CLASSES:
    bpy.utils.register_class(cls)
  bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
  '''Unregisters all classes.'''
  for cls in CLASSES:
    bpy.utils.unregister_class(cls)
  bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)


if __name__ == '__main__':
  register()
