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

# Probe for OpenSSL first — FindRTIConnextDDS uses REQUIRED internally for
# security_plugins, so we only request that component when OpenSSL is available.
# Check for RTI-bundled OpenSSL under the Connext installation's third_party
# directory, which is the typical setup for Connext users with security.
if(NOT OPENSSL_ROOT_DIR AND NOT CONNEXTDDS_OPENSSL_DIR)
    # Resolve the Connext installation directory
    if(CONNEXTDDS_DIR)
        set(_connext_dir "${CONNEXTDDS_DIR}")
    elseif(DEFINED ENV{NDDSHOME})
        set(_connext_dir "$ENV{NDDSHOME}")
    endif()
    if(_connext_dir)
        file(GLOB _openssl_dirs "${_connext_dir}/third_party/openssl-*")
        foreach(_ossl_dir ${_openssl_dirs})
            # Look for <arch>/release/ inside the openssl directory
            file(GLOB _arch_dirs "${_ossl_dir}/*")
            foreach(_arch_dir ${_arch_dirs})
                if(IS_DIRECTORY "${_arch_dir}/release"
                    AND EXISTS "${_arch_dir}/release/include"
                    AND EXISTS "${_arch_dir}/release/lib")
                    set(OPENSSL_ROOT_DIR "${_arch_dir}/release")
                    message(STATUS "Found RTI-bundled OpenSSL: ${OPENSSL_ROOT_DIR}")
                    break()
                endif()
            endforeach()
            if(OPENSSL_ROOT_DIR)
                break()
            endif()
        endforeach()
        unset(_connext_dir)
        unset(_openssl_dirs)
        unset(_arch_dirs)
        unset(_ossl_dir)
        unset(_arch_dir)
    endif()
elseif(CONNEXTDDS_OPENSSL_DIR)
    set(OPENSSL_ROOT_DIR "${CONNEXTDDS_OPENSSL_DIR}")
endif()

find_package(OpenSSL QUIET)
if(OPENSSL_FOUND)
    message(STATUS "OpenSSL found — requesting security_plugins component")
    find_package(
        RTIConnextDDS "7.3.0"
        REQUIRED
        COMPONENTS
        core
        OPTIONAL_COMPONENTS
        security_plugins
    )
else()
    message(STATUS "OpenSSL not found — building without security_plugins")
    find_package(
        RTIConnextDDS "7.3.0"
        REQUIRED
        COMPONENTS
        core
    )
    set(RTIConnextDDS_security_plugins_FOUND FALSE)
endif()

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

if(RTIConnextDDS_security_plugins_FOUND)
    # Generate C++ types for DDS Security builtin logging topic.
    set(BUILTIN_LOGGING_IDL "${CONNEXTDDS_DIR}/resource/idl/builtin_logging_type.idl")
    connextdds_rtiddsgen_run(
        IDL_FILE
        "${BUILTIN_LOGGING_IDL}"
        OUTPUT_DIRECTORY
        "${CMAKE_CURRENT_BINARY_DIR}/src/"
        LANG C++11
        UNBOUNDED
    )

    # Generate Python types for DDS Security builtin logging topic (used by module 04
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
if(RTIConnextDDS_security_plugins_FOUND)
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
    PRIVATE
    RTIConnextDDS::cpp2_api
)

# Build Applications
set(APPLICATIONS ArmController Orchestrator PatientSensor)

foreach(application ${APPLICATIONS})
    add_executable(${application}
        "${CMAKE_CURRENT_SOURCE_DIR}/src/${application}.cxx"
    )

    target_link_libraries(${application}
        PRIVATE
        ${GTKMM_LIBRARIES}
        RTIConnextDDS::cpp2_api
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

if(RTIConnextDDS_security_plugins_FOUND)
    target_compile_definitions(Orchestrator PRIVATE RTI_SECURITY_AVAILABLE)
endif()