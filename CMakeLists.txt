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
    GIT_TAG        main
)
FetchContent_MakeAvailable(rticonnextdds-cmake-utils)

list(APPEND CMAKE_MODULE_PATH
    "${rticonnextdds-cmake-utils_SOURCE_DIR}/cmake/Modules"
)

# RTI Demo UI v0.4.1 with the native GTK sizing fix, pinned so C++ and Python
# use the same SDK revision.
option(RTI_DEMO_BUILD_NATIVE_WEBVIEW
    "Build the optional native webview companion"
    OFF
)
FetchContent_Declare(
    rti_demo_ui
    GIT_REPOSITORY https://github.com/wcoleman-rti/rti-demo-ui.git
    GIT_TAG        4e4b0f229e4968a2245fa6f09b9a720b11d47eb8
)
FetchContent_MakeAvailable(rti_demo_ui)

# --- Find RTI Connext DDS ---
message(STATUS "Looking for RTI Connext DDS version ${RTICONNEXTDDS_VERSION}...")
find_package(RTIConnextDDS ${RTICONNEXTDDS_VERSION} REQUIRED
    COMPONENTS messaging_api
)

# --- Modules with C++ code ---
add_subdirectory(modules/01-operating-room)
add_subdirectory(modules/02-record-playback)
add_subdirectory(modules/03-remote-teleoperation)
add_subdirectory(modules/04-security-threat)

# Convenience target: build all module targets at once
add_custom_target(all-modules DEPENDS module-01 module-02 module-03 module-04)
