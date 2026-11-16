#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software. RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

include(ConnextDdsCodegen)

set(MEDTECH_IDL_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/idl")
set(MEDTECH_GENERATED "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(GLOB_RECURSE MEDTECH_IDLS CONFIGURE_DEPENDS "${MEDTECH_IDL_ROOT}/*.idl")
# ConnextDdsCodegen tracks the primary IDL for each run; declare the shared
# IDL set as prerequisites so changes to included files regenerate all outputs.
set(MEDTECH_IDL_DEPENDS ${MEDTECH_IDLS})
set(MEDTECH_CXX_SOURCES)
set(MEDTECH_XML_FILES)
foreach(idl IN LISTS MEDTECH_IDLS)
    file(RELATIVE_PATH relative_idl "${MEDTECH_IDL_ROOT}" "${idl}")
    get_filename_component(relative_dir "${relative_idl}" DIRECTORY)
    connextdds_rtiddsgen_run(
        IDL_FILE "${idl}"
        OUTPUT_DIRECTORY "${MEDTECH_GENERATED}/cpp/${relative_dir}"
        LANG C++11 VAR model
        INCLUDE_DIRS "${MEDTECH_IDL_ROOT}"
        EXTRA_ARGS -standard IDL4_CPP
    )
    list(APPEND MEDTECH_CXX_SOURCES ${model_CXX11_GENERATED_SOURCES})
    list(GET model_CXX11_SOURCES 0 first_output)
    add_custom_command(OUTPUT "${first_output}" APPEND DEPENDS ${MEDTECH_IDL_DEPENDS})
    connextdds_rtiddsgen_convert(
        INPUT "${idl}" FROM IDL TO XML
        OUTPUT_DIRECTORY "${MEDTECH_GENERATED}/xml/${relative_dir}"
        INCLUDE_DIRS "${MEDTECH_IDL_ROOT}"
        DEPENDS ${MEDTECH_IDL_DEPENDS}
        VAR xml_output
    )
    list(APPEND MEDTECH_XML_FILES "${xml_output}")
endforeach()

connextdds_rtiddsgen_run(
    IDL_FILE "${MEDTECH_IDL_ROOT}/MedTech.idl"
    OUTPUT_DIRECTORY "${MEDTECH_GENERATED}/python"
    LANG Python
    INCLUDE_DIRS "${MEDTECH_IDL_ROOT}"
    EXTRA_ARGS -joinInputFiles -joinedFilesOutputName MedTech
)
add_custom_command(
    OUTPUT "${MEDTECH_GENERATED}/python/MedTech.py"
    APPEND DEPENDS ${MEDTECH_IDL_DEPENDS}
)

set(BUILTIN_LOGGING_IDL "${CONNEXTDDS_DIR}/resource/idl/builtin_logging_type.idl")
set(RTI_SECURITY_AVAILABLE FALSE)
if(EXISTS "${BUILTIN_LOGGING_IDL}")
    set(RTI_SECURITY_AVAILABLE TRUE)
    connextdds_rtiddsgen_run(
        IDL_FILE "${BUILTIN_LOGGING_IDL}"
        OUTPUT_DIRECTORY "${MEDTECH_GENERATED}/cpp"
        LANG C++11 UNBOUNDED EXTRA_ARGS -standard IDL4_CPP
    )
    connextdds_rtiddsgen_run(
        IDL_FILE "${BUILTIN_LOGGING_IDL}"
        OUTPUT_DIRECTORY "${MEDTECH_GENERATED}/python"
        LANG Python
    )
    list(APPEND MEDTECH_CXX_SOURCES ${builtin_logging_type_CXX11_GENERATED_SOURCES})
endif()
set(RTI_SECURITY_AVAILABLE "${RTI_SECURITY_AVAILABLE}" PARENT_SCOPE)

add_custom_target(refArchTypesPy ALL
    DEPENDS ${MedTech_PYTHON_SOURCES} ${builtin_logging_type_PYTHON_SOURCES}
)
add_custom_target(refArchTypesXml ALL DEPENDS ${MEDTECH_XML_FILES})
add_library(refArchTypes OBJECT ${MEDTECH_CXX_SOURCES})
target_include_directories(refArchTypes PUBLIC "${MEDTECH_GENERATED}/cpp")
target_link_libraries(refArchTypes PUBLIC RTIConnextDDS::cpp2_api)
add_dependencies(refArchTypes refArchTypesPy refArchTypesXml)
