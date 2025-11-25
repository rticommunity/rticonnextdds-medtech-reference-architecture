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

cmake_minimum_required(VERSION 3.7)
project(MedicalRefArch)

# Set the C++ standard to C++17
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Use the package PkgConfig to detect GTK+ headers/library files
find_package(PkgConfig REQUIRED)
pkg_check_modules(GTKMM REQUIRED gtkmm-3.0)

# link GTK UI libraries
link_directories(
    ${GTKMM_LIBRARY_DIRS})

include_directories(
    ${GTKMM_INCLUDE_DIRS})

# Find RTI Connext dependencies
set(CMAKE_MODULE_PATH
    ${CMAKE_MODULE_PATH}
    ${CMAKE_CURRENT_SOURCE_DIR}/../../resource/cmake/rticonnextdds-cmake-utils/cmake/Modules
)

find_package(
    RTIConnextDDS "7.3.0"
    REQUIRED
    COMPONENTS
    core
)

# Run Codegen to generate the C++11 source code files for the types
include(ConnextDdsCodegen)
connextdds_rtiddsgen_run(
    IDL_FILE
    "${CMAKE_CURRENT_SOURCE_DIR}/../../system_arch/Types.xml"
    OUTPUT_DIRECTORY
    "${CMAKE_CURRENT_BINARY_DIR}/src/"
    LANG C++11
    DISABLE_PREPROCESSOR
)

# Use command line to manually generate Python types
execute_process(
    COMMAND bash -c "rtiddsgen ../../system_arch/Types.xml -ppDisable -d src -language python -create typefiles"
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
)

# Build object library with types
add_library(refArchTypes OBJECT
    ${Types_CXX11_GENERATED_SOURCES}
)
target_link_libraries(refArchTypes
    PRIVATE
    RTIConnextDDS::cpp2_api
)

# Build Applications
set(APPLICATIONS ArmController Orchestrator PatientSensor)

foreach(application ${APPLICATIONS})
    add_executable(${application}
        "${CMAKE_CURRENT_SOURCE_DIR}/src/${application}.cxx"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/DdsUtils.hpp"
    )

    target_link_libraries(${application}
        PRIVATE
        ${GTKMM_LIBRARIES}
        RTIConnextDDS::cpp2_api
        refArchTypes
    )
    target_include_directories(${application}
        PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/src"
        "${CMAKE_CURRENT_BINARY_DIR}/src"
    )
    set_property(TARGET ${application}
        PROPERTY
        CXX_STANDARD 17)
endforeach()