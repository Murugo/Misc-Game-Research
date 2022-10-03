# Xenosaga Episode III: Also sprach Zarathustra (PS2, 2006)

* **io_xeno3** - A Blender add-on for importing Jesus Christ. (It could also be used to import other .CHR model files, I suppose...) Compatible with Blender 2.8.x only. To install:
  * Build `PS2/Common/gsutil` by configuring and building `cmake` from the root directory of this repository (requires [SWIG](https://swig.org)). When compiling, ensure you are using the same Python version that comes with Blender. Otherwise, the compiled library will fail to import. You can check the Python version you need by viewing the console in the Scripting workspace in Blender.
  * Pack the contents of `Blender/addons/io_xeno3/` in a ZIP file. Ensure that the contents of folders `gsutil/` and `readutil/` are included in the ZIP as well.
  * Import the add-on using `Edit -> Preferences -> Add-ons -> Install`.

## Known Issues:
* Does not yet support models with separate .PXY and .TXY files.
* Some models fail to import correctly, such as `mdl/ene/C3telos00.chr`.

<img src="img/jesus.gif" title="Body of Christ">
