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

set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type (default: Release)")
set(BUILD_SHARED_LIBS ON CACHE BOOL "Build shared libraries (default: ON)")

if(NOT CONNEXTDDS_DIR)
    set(CONNEXTDDS_DIR "$ENV{NDDSHOME}" CACHE PATH "RTI Connext DDS installation")
endif()
if(NOT EXISTS "${CONNEXTDDS_DIR}/resource/cmake/FindRTIConnextDDS.cmake")
    message(FATAL_ERROR
        "Set NDDSHOME or CONNEXTDDS_DIR to a Connext DDS installation with resource/cmake utilities."
    )
endif()
list(PREPEND CMAKE_MODULE_PATH "${CONNEXTDDS_DIR}/resource/cmake")

include(FetchContent)
if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()

set(JSON_BuildTests OFF CACHE BOOL "Build JSON tests" FORCE)
FetchContent_Declare(
    nlohmann_json
    URL https://codeload.github.com/nlohmann/json/tar.gz/refs/tags/v3.12.0
    URL_HASH SHA256=4b92eb0c06d10683f7447ce9406cb97cd4b453be18d7279320f7b2f025c10187
)
FetchContent_MakeAvailable(nlohmann_json)

# --- Find RTI Connext DDS ---
set(RTICONNEXTDDS_VERSION "7.7.0" CACHE STRING "Supported Connext DDS version")
message(STATUS "Looking for RTI Connext DDS version ${RTICONNEXTDDS_VERSION}...")
find_package(RTIConnextDDS ${RTICONNEXTDDS_VERSION} REQUIRED
    COMPONENTS messaging_api
)

# --- Modules with C++ code ---
add_subdirectory(modules/01-operating-room)

# Convenience target: build all module targets at once
add_custom_target(all-modules DEPENDS module-01)
