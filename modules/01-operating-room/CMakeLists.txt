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

# Build Applications

# PatientSensor is headless and does not use RTI Demo UI.
add_executable(PatientSensor
    "${CMAKE_CURRENT_SOURCE_DIR}/src/PatientSensor.cxx"
)
target_link_libraries(PatientSensor
    PRIVATE
    RTIConnextDDS::cpp2_api
    refArchTypes
)
target_include_directories(PatientSensor
    PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${CMAKE_CURRENT_BINARY_DIR}/src"
)
set_property(TARGET PatientSensor PROPERTY CXX_STANDARD 17)

# RTI Demo UI browser applications. Native webview support is an opt-in build
# feature so browser-only binaries do not link platform webview dependencies.
set(GRAPHICAL_APPLICATIONS ArmController Orchestrator)
foreach(application ${GRAPHICAL_APPLICATIONS})
    add_executable(${application}
        "${CMAKE_CURRENT_SOURCE_DIR}/src/${application}.cxx"
    )

    target_link_libraries(${application}
        PRIVATE
        RTIConnextDDS::cpp2_api
        refArchTypes
        rti_demo_ui::core
    )
    target_compile_definitions(${application}
        PRIVATE RTI_DEMO_UI_WEB_ROOT="${PROJECT_SOURCE_DIR}/resources/ui/web"
    )
    target_include_directories(${application}
        PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/src"
        "${CMAKE_CURRENT_BINARY_DIR}/src"
        "${PROJECT_SOURCE_DIR}/resources/ui/support"
    )
    set_property(TARGET ${application} PROPERTY CXX_STANDARD 17)

    if(RTI_DEMO_BUILD_NATIVE_WEBVIEW)
        target_link_libraries(${application} PRIVATE rti_demo_ui_native::native_webview)
        target_compile_definitions(${application} PRIVATE RTI_DEMO_UI_NATIVE_AVAILABLE)
    endif()
endforeach()

if(RTI_SECURITY_AVAILABLE)
    target_compile_definitions(Orchestrator PRIVATE RTI_SECURITY_AVAILABLE)
endif()

# Convenience target: build all Module 01 executables
set(APPLICATIONS PatientSensor ${GRAPHICAL_APPLICATIONS})
add_custom_target(module-01 DEPENDS ${APPLICATIONS})
