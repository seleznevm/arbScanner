# Минимальная версия CMake
cmake_minimum_required(VERSION 3.10)

# Название проекта
project(TopKWords VERSION 1.0)

# Устанавливаем стандарт C++
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)

# Добавляем исполняемый файл
add_executable(topk_words main.cpp)

# Включаем поддержку многопоточности
find_package(Threads REQUIRED)
target_link_libraries(topk_words Threads::Threads)

# Настраиваем опции компиляции
if(MSVC)
    target_compile_options(topk_words PRIVATE /W4 /WX)
else()
    target_compile_options(topk_words PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

# Включаем тестирование
enable_testing()

