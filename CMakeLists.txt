cmake_minimum_required(VERSION 3.20)

project(fruitsim VERSION 0.5.0 LANGUAGES CXX)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(FRUITSIM_BUILD_TESTS "Build fruitsim tests" ON)
option(FRUITSIM_BUILD_GUI "Build the Dear ImGui research GUI" OFF)
option(FRUITSIM_ENABLE_CUDA "Build the CUDA transport backend" OFF)

include(FetchContent)
find_package(nlohmann_json 3.11 QUIET)
if(NOT nlohmann_json_FOUND)
    FetchContent_Declare(
        nlohmann_json
        URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
        DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    )
    FetchContent_MakeAvailable(nlohmann_json)
endif()

function(fruitsim_set_warnings target)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4 /permissive-)
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endfunction()

add_subdirectory(src/core)
add_subdirectory(src/geometry)
add_subdirectory(src/optics)
add_subdirectory(src/transport)
add_subdirectory(src/runtime)
add_subdirectory(src/io)

if(FRUITSIM_ENABLE_CUDA)
    enable_language(CUDA)
    add_subdirectory(src/cuda)
endif()

add_subdirectory(apps/fruitsim_cli)

if(FRUITSIM_BUILD_GUI)
    add_subdirectory(apps/fruitsim_gui)
endif()

if(FRUITSIM_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
