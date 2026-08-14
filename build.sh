cmake --build build --parallel 4
clang \
    -O0 \
    -S \
    -emit-llvm \
    tests/input.c \
    -o tests/input.ll
opt \
    -load-pass-plugin=build/MyPass.so \
    -passes=MyPass \
    -disable-output \
    tests/input.ll
