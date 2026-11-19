#
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software solely in combination with RTI Connext DDS. Licensee
# may redistribute copies of the Software provided that all such copies are
# subject to this License. The Software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the Software. RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the Software. For purposes of clarity, nothing in this
# License prevents Licensee from using alternate versions of DDS, provided
# that Licensee may not combine or link such alternate versions of DDS with
# the Software.
#

cmake_minimum_required(VERSION 3.18)
project(MedTechRefArch LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type (default: Release)")
set(BUILD_SHARED_LIBS ON CACHE BOOL "Build shared libraries (default: ON)")

# --- RTI CMake Utilities (fetched from GitHub) ---
include(FetchContent)
FetchContent_Declare(
    rticonnextdds-cmake-utils
    GIT_REPOSITORY https://github.com/rticommunity/rticonnextdds-cmake-utils.git
    GIT_TAG        c00c88e12948d472d2ebd1b70b3c219a92cd0d01
)
FetchContent_MakeAvailable(rticonnextdds-cmake-utils)

list(APPEND CMAKE_MODULE_PATH
    "${rticonnextdds-cmake-utils_SOURCE_DIR}/cmake/Modules"
)

# RTI Demo UI with Scene3D material/preset controls. Keep the C++, Python, and
# native companion on the same release commit.
option(RTI_DEMO_BUILD_NATIVE_WEBVIEW
    "Build the optional native webview companion"
    OFF
)
FetchContent_Declare(
    rti_demo_ui
    GIT_REPOSITORY https://github.com/wcoleman-rti/rti-demo-ui.git
    GIT_TAG        e31e8981d625f9d6bbc00797d7e38caf8a165659 # v0.5.1
)

# The SDK marks itself as a top-level build when consumed through FetchContent.
# Disable only its examples/tests while adding it; restore this project's
# caller-provided test setting immediately afterward.
if(DEFINED RTI_DEMO_BUILD_EXAMPLES)
    set(_MEDTECH_UI_EXAMPLES_WAS_DEFINED TRUE)
    set(_MEDTECH_UI_EXAMPLES_VALUE "${RTI_DEMO_BUILD_EXAMPLES}")
else()
    set(_MEDTECH_UI_EXAMPLES_WAS_DEFINED FALSE)
endif()
if(DEFINED BUILD_TESTING)
    set(_MEDTECH_BUILD_TESTING_WAS_DEFINED TRUE)
    set(_MEDTECH_BUILD_TESTING_VALUE "${BUILD_TESTING}")
else()
    set(_MEDTECH_BUILD_TESTING_WAS_DEFINED FALSE)
endif()
if(DEFINED RTI_DEMO_NATIVE_BUILD_EXAMPLES)
    set(_MEDTECH_NATIVE_EXAMPLES_WAS_DEFINED TRUE)
    set(_MEDTECH_NATIVE_EXAMPLES_VALUE "${RTI_DEMO_NATIVE_BUILD_EXAMPLES}")
else()
    set(_MEDTECH_NATIVE_EXAMPLES_WAS_DEFINED FALSE)
endif()
set(RTI_DEMO_BUILD_EXAMPLES OFF)
set(RTI_DEMO_NATIVE_BUILD_EXAMPLES OFF)
set(BUILD_TESTING OFF)
FetchContent_MakeAvailable(rti_demo_ui)
if(_MEDTECH_UI_EXAMPLES_WAS_DEFINED)
    set(RTI_DEMO_BUILD_EXAMPLES "${_MEDTECH_UI_EXAMPLES_VALUE}")
else()
    unset(RTI_DEMO_BUILD_EXAMPLES)
endif()
if(_MEDTECH_BUILD_TESTING_WAS_DEFINED)
    set(BUILD_TESTING "${_MEDTECH_BUILD_TESTING_VALUE}")
else()
    unset(BUILD_TESTING)
endif()
if(_MEDTECH_NATIVE_EXAMPLES_WAS_DEFINED)
    set(RTI_DEMO_NATIVE_BUILD_EXAMPLES "${_MEDTECH_NATIVE_EXAMPLES_VALUE}")
else()
    unset(RTI_DEMO_NATIVE_BUILD_EXAMPLES)
endif()
unset(_MEDTECH_UI_EXAMPLES_WAS_DEFINED)
unset(_MEDTECH_UI_EXAMPLES_VALUE)
unset(_MEDTECH_BUILD_TESTING_WAS_DEFINED)
unset(_MEDTECH_BUILD_TESTING_VALUE)
unset(_MEDTECH_NATIVE_EXAMPLES_WAS_DEFINED)
unset(_MEDTECH_NATIVE_EXAMPLES_VALUE)

# --- Find RTI Connext DDS ---
message(STATUS "Looking for RTI Connext DDS version ${RTICONNEXTDDS_VERSION}...")
find_package(RTIConnextDDS ${RTICONNEXTDDS_VERSION} REQUIRED
    COMPONENTS messaging_api
)

# --- Modules with C++ code ---
add_subdirectory(system)
add_subdirectory(modules/01-operating-room)
add_subdirectory(modules/02-record-playback)
add_subdirectory(modules/03-remote-teleoperation)
add_subdirectory(modules/04-security-threat)

# Convenience target: build all module targets at once
add_custom_target(all-modules DEPENDS module-01 module-02 module-03 module-04)
