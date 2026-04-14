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

# RTI Connext DDS is found by the project-level CMakeLists.txt.

# Run Codegen to generate the C++11 source code files for the types
include(ConnextDdsCodegen)
connextdds_rtiddsgen_run(
    IDL_FILE
    "${CMAKE_CURRENT_SOURCE_DIR}/xml_config/ThreatTypes.xml"
    OUTPUT_DIRECTORY
    "${CMAKE_CURRENT_BINARY_DIR}/src/"
    LANG C++11
    UNBOUNDED
)

# Generate Python types for application use (output alongside source files so
# DdsUtils.py in this module and module 04 can import them directly)
connextdds_rtiddsgen_run(
    IDL_FILE
    "${CMAKE_CURRENT_SOURCE_DIR}/xml_config/ThreatTypes.xml"
    OUTPUT_DIRECTORY
    "${CMAKE_CURRENT_SOURCE_DIR}/src/"
    LANG Python
)

add_custom_target(threatTypesPy ALL
    DEPENDS
        ${ThreatTypes_PYTHON_SOURCES}
)

# Build object library with types
add_library(threatTypes OBJECT 
    ${ThreatTypes_CXX11_GENERATED_SOURCES}
)
target_link_libraries(threatTypes
    PRIVATE
    RTIConnextDDS::cpp2_api
)

# Build Applications
add_custom_target(module-04 DEPENDS)