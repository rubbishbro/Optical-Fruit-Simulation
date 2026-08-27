#ifndef RTWEEKEND_H
#define RTWEEKEND_H

#include <cmath>
#include <limits>
#include <memory>
#include <iostream>

// 
using std::shared_ptr;
using std::make_shared;

// 常量
const double infinity = std::numeric_limits<double>::infinity();
const double pi = 3.1415926535897932385;

// 角度转弧度
inline double degrees_to_radians(double degrees){
    return degrees * pi / 180.0;
}

// 引用
#include "ray.h"
#include "vec3.h"
#include "color.h"
#include "interval.h"

#endif