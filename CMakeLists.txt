cmake_minimum_required(VERSION 3.20)

project(LLVM-basic-LICM-implementation LANGUAGES CXX)

find_package(LLVM REQUIRED CONFIG)

message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "LLVM_DIR = ${LLVM_DIR}")
message(STATUS "LLVM_INCLUDE_DIRS = ${LLVM_INCLUDE_DIRS}")

list(APPEND CMAKE_MODULE_PATH "${LLVM_CMAKE_DIR}")
include(AddLLVM)

include_directories(SYSTEM ${LLVM_INCLUDE_DIRS})
add_definitions(${LLVM_DEFINITIONS})

add_llvm_pass_plugin(MyPass
        src/MyPass.cpp
)

target_compile_features(MyPass PRIVATE cxx_std_17)


# input.c -> input.ll

set(INPUT_C
        ${CMAKE_CURRENT_SOURCE_DIR}/tests/input.c
)

set(INPUT_LL
        ${CMAKE_CURRENT_SOURCE_DIR}/tests/input.ll
)

find_program(
        CLANG_EXECUTABLE
        NAMES clang clang-22
        HINTS "${LLVM_TOOLS_BINARY_DIR}"
        REQUIRED
)

add_custom_command(
        OUTPUT ${INPUT_LL}

        COMMAND
        ${CLANG_EXECUTABLE}
        -O0
        -S
        -emit-llvm
        ${INPUT_C}
        -o ${INPUT_LL}

        DEPENDS ${INPUT_C}

        COMMENT "Generating input.ll from input.c"
        VERBATIM
)

add_custom_target(
        generate-ir ALL
        DEPENDS ${INPUT_LL}
)

find_program(
        OPT_EXECUTABLE
        NAMES opt opt-22
        HINTS "${LLVM_TOOLS_BINARY_DIR}"
        REQUIRED
)

add_custom_target(
        run-pass

        COMMAND
        ${OPT_EXECUTABLE}
        -load-pass-plugin=$<TARGET_FILE:MyPass>
        -passes=MyPass
        -disable-output
        ${INPUT_LL}

        COMMENT "Running MyPass on input.ll"

        VERBATIM
)

add_dependencies(
        run-pass
        MyPass
        generate-ir
)