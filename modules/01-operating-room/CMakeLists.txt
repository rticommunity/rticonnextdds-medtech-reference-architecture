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

# Use the package PkgConfig to detect GTK headers/library files.
# gtkmm-3.0 is optional: when not found the C++ GUI applications
# (ArmController, Orchestrator) are skipped; PatientSensor and the
# Python GUIs still build/run normally.
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
    pkg_check_modules(GTKMM gtkmm-3.0)
endif()

if(GTKMM_FOUND)
    link_directories(${GTKMM_LIBRARY_DIRS})
    include_directories(${GTKMM_INCLUDE_DIRS})
    message(STATUS "gtkmm-3.0 found — ArmController and Orchestrator will be built")
else()
    message(STATUS "gtkmm-3.0 not found — skipping ArmController and Orchestrator (Python GUIs still available)")
endif()

# RTI Connext DDS is found by the project-level CMakeLists.txt.

# Run Codegen to generate the C++11 source code files for the types
include(ConnextDdsCodegen)
connextdds_rtiddsgen_run(
    IDL_FILE
    "${CMAKE_CURRENT_SOURCE_DIR}/../../system_arch/Types.xml"
    OUTPUT_DIRECTORY
    "${CMAKE_CURRENT_BINARY_DIR}/src/"
    LANG C++11
    UNBOUNDED
)

# Generate Python types for application use (output alongside source files so
# DdsUtils.py in this module and module 04 can import them directly)
connextdds_rtiddsgen_run(
    IDL_FILE
    "${CMAKE_CURRENT_SOURCE_DIR}/../../system_arch/Types.xml"
    OUTPUT_DIRECTORY
    "${CMAKE_CURRENT_SOURCE_DIR}/src/"
    LANG Python
)

# If RTI Security Plugins are installed, builtin_logging_type.idl exists
# under the Connext installation. Generate C++ and Python types from it.
set(BUILTIN_LOGGING_IDL "${CONNEXTDDS_DIR}/resource/idl/builtin_logging_type.idl")
set(RTI_SECURITY_AVAILABLE FALSE)

if(EXISTS "${BUILTIN_LOGGING_IDL}")
    set(RTI_SECURITY_AVAILABLE TRUE)
    message(STATUS "Security Plugins IDL found — generating builtin_logging_type types")

    connextdds_rtiddsgen_run(
        IDL_FILE
        "${BUILTIN_LOGGING_IDL}"
        OUTPUT_DIRECTORY
        "${CMAKE_CURRENT_BINARY_DIR}/src/"
        LANG C++11
        UNBOUNDED
    )

    # Python types for DDS Security builtin logging topic (used by module 04
    # SecureLogUtils.py via the same _OR_SRC import path as Types.py)
    connextdds_rtiddsgen_run(
        IDL_FILE
        "${BUILTIN_LOGGING_IDL}"
        OUTPUT_DIRECTORY
        "${CMAKE_CURRENT_SOURCE_DIR}/src/"
        LANG Python
    )
endif()

set(SECURITY_PYTHON_SOURCES "")
set(SECURITY_CXX_SOURCES "")
if(RTI_SECURITY_AVAILABLE)
    set(SECURITY_PYTHON_SOURCES ${builtin_logging_type_PYTHON_SOURCES})
    set(SECURITY_CXX_SOURCES ${builtin_logging_type_CXX11_GENERATED_SOURCES})
endif()

add_custom_target(refArchTypesPy ALL
    DEPENDS
        ${Types_PYTHON_SOURCES}
        ${SECURITY_PYTHON_SOURCES}
)

# Build object library with types
add_library(refArchTypes OBJECT 
    ${Types_CXX11_GENERATED_SOURCES}
    ${SECURITY_CXX_SOURCES}
)
target_link_libraries(refArchTypes
    PUBLIC
    RTIConnextDDS::cpp2_api
)

# Build Applications

# PatientSensor is headless (no GTK dependency)
add_executable(PatientSensor
    "${CMAKE_CURRENT_SOURCE_DIR}/src/PatientSensor.cxx"
)
target_link_libraries(PatientSensor
    PRIVATE
    refArchTypes
)
target_include_directories(PatientSensor
    PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${CMAKE_CURRENT_BINARY_DIR}/src"
)
set_property(TARGET PatientSensor PROPERTY CXX_STANDARD 17)

# GTK applications (ArmController, Orchestrator) require gtkmm
set(GTK_APPLICATIONS "")

if(GTKMM_FOUND)
    set(GTK_APPLICATIONS ArmController Orchestrator)

    foreach(application ${GTK_APPLICATIONS})
        add_executable(${application}
            "${CMAKE_CURRENT_SOURCE_DIR}/src/${application}.cxx"
        )

        target_link_libraries(${application}
            PRIVATE
            ${GTKMM_LIBRARIES}
            refArchTypes
        )
        if(APPLE)
            target_link_libraries(${application} PRIVATE "-framework AppKit")
        endif()
        target_include_directories(${application}
            PRIVATE
            "${CMAKE_CURRENT_SOURCE_DIR}/src"
            "${CMAKE_CURRENT_BINARY_DIR}/src"
        )
        set_property(TARGET ${application}
            PROPERTY
            CXX_STANDARD 17)
    endforeach()

    if(RTI_SECURITY_AVAILABLE)
        target_compile_definitions(Orchestrator PRIVATE RTI_SECURITY_AVAILABLE)
    endif()
endif()

# Convenience target: build all Module 01 executables
set(APPLICATIONS PatientSensor ${GTK_APPLICATIONS})
add_custom_target(module-01 DEPENDS ${APPLICATIONS})
