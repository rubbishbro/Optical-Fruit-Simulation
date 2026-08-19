cmake_minimum_required(VERSION 3.16)

project(fruitsim
    VERSION 0.1.0
    DESCRIPTION "A small C++17 ray tracing simulation platform"
    LANGUAGES CXX
)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(FRUITSIM_BUILD_TESTS "Build fruitsim tests" ON)

add_library(fruitsim_core
    src/random.cpp
)

add_library(fruitsim::core ALIAS fruitsim_core)

target_compile_features(fruitsim_core PUBLIC cxx_std_17)

target_include_directories(fruitsim_core
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
)

if(MSVC)
    target_compile_options(fruitsim_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(fruitsim_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_subdirectory(apps/fruitsim_cli)

add_executable(raytracing_practice
    prac-raytracing/main.cpp
    prac-raytracing/rtweekend.h
    prac-raytracing/interval.h
)

target_compile_features(raytracing_practice PRIVATE cxx_std_17)

target_include_directories(raytracing_practice
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/prac-raytracing
)

if(FRUITSIM_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
