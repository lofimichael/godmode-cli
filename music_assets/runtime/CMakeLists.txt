# Godmode's console-only recipe for the separately executed GPL SEQ64 converter.
# Adapted from SEQ64 47500ab1bbf93eeaad35806ff6a13163cc11538a CMakeLists.txt.
# Original build copyright (C) 2014-2023 Sauraen; GPL-3.0-or-later.
# Changes: minimal source subset, Release build, macOS Objective-C++ correction.
cmake_minimum_required(VERSION 3.13)
project(GodmodeMusicConverter VERSION 2.4.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
add_executable(seq64_console
    vendor/seq64/Source/CommandLine.cpp
    vendor/seq64/Source/SeqFile.cpp
    vendor/seq64/Source/MainConsole.cpp
    vendor/juce/modules/juce_core/juce_core.cpp
    vendor/juce/modules/juce_events/juce_events.cpp
    vendor/juce/modules/juce_audio_basics/juce_audio_basics.cpp
    vendor/juce/modules/juce_data_structures/juce_data_structures.cpp)
target_include_directories(seq64_console PRIVATE vendor/seq64/Source vendor/juce/modules)
target_compile_definitions(seq64_console PRIVATE
    JUCE_STANDALONE_APPLICATION=1 JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0
    JUCE_APPLICATION_NAME_STRING="SEQ64 V2.4.0"
    JUCE_APPLICATION_VERSION_STRING="2.4.0" JUCE_APPLICATION_VERSION_HEX=0x020400
    JUCE_GLOBAL_MODULE_SETTINGS_INCLUDED=1 SEQ64_CONSOLE_ONLY=1)
if(APPLE)
    enable_language(OBJCXX)
    set_source_files_properties(
        vendor/juce/modules/juce_core/juce_core.cpp
        vendor/juce/modules/juce_events/juce_events.cpp PROPERTIES LANGUAGE OBJCXX)
    target_link_libraries(seq64_console PRIVATE
        "-framework Foundation" "-framework AppKit" "-framework IOKit"
        "-framework Security" "-framework CoreFoundation" "-framework Accelerate")
elseif(UNIX)
    find_package(Threads REQUIRED)
    target_link_libraries(seq64_console PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
endif()
