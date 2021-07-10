cmake_minimum_required(VERSION 3.0.0)
project(miscresearch)

# include(CTest)
# enable_testing()

set(CPACK_PROJECT_NAME ${PROJECT_NAME})
set(CPACK_PROJECT_VERSION ${PROJECT_VERSION})
include(CPack)

add_subdirectory("PS2/Kingdom Hearts II Final Mix/Blender/addons/io_kh2fm")
