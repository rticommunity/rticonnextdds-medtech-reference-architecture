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

cmake_minimum_required(VERSION 3.17)
project(MedTechRefArch LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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

# --- Find RTI Connext DDS ---
find_package(RTIConnextDDS "7.3.0" REQUIRED
    COMPONENTS core
)

# --- Modules with C++ code ---
add_subdirectory(modules/01-operating-room)

# Convenience target: build all module targets at once
add_custom_target(all-modules DEPENDS module-01)
