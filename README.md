# fruitsim

`fruitsim` is a small C++17 ray tracing simulation platform starter. The first kernel layer contains:

- `Vec3`: vector math for geometry and color-like quantities
- `Ray`: origin, direction, and parametric evaluation with `at(t)`
- `Random`: simple uniform random sampling utilities
- `fruitsim_cli`: a tiny executable that creates and prints a ray
- `fruitsim_tests`: minimal core tests without external dependencies

## Build

```bash
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

## Run

```bash
./build/apps/fruitsim_cli/fruitsim_cli
```

## Project Tree

```text
.
├── CMakeLists.txt
├── GUIDE.md
├── README.md
├── apps
│   └── fruitsim_cli
│       ├── CMakeLists.txt
│       └── main.cpp
├── include
│   └── fruitsim
│       ├── random.hpp
│       ├── ray.hpp
│       └── vec3.hpp
├── src
│   └── random.cpp
└── tests
    ├── CMakeLists.txt
    └── test_core.cpp
```

## Next Kernel Steps

The next natural modules are `HitRecord`, `Hittable`, `Sphere`, `Camera`, and a first image writer such as PPM output.
