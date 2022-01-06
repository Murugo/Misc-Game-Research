# Kingdom Hearts II Final Mix (PS2, 2007)

* **io_kh2fm** - A *super-experimental* Blender add-on capable of importing MDLX (model) and ANB/MSET (animation) files. Compatible with Blender 2.8.x only. To install:
  * Build `PS2/Common/gsutil` by configuring and building `cmake` from the root directory of this repository (requires [SWIG](https://swig.org)). Ensure you are using the same Python version that comes with Blender. Otherwise, the compiled library will fail to import. You can check the Python version you need in the Scripting workspace in Blender.
  * Pack the contents of `Blender/addons/io_kh2fm/` in a ZIP file. Ensure that the contents of folders `gsutil/` and `readutil/` are included in the ZIP as well.
  * Import the add-on using `Edit -> Preferences -> Add-ons -> Install`.

<img src="img/silence_traitor_720.png" alt="Silence, traitor." width="75%">
