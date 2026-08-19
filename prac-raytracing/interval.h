#ifndef INTERVAL_H
#define INTERVAL_H

class interval{
    public:
        double min, max;

        interval(double min = 0, double max = 0): min(min), max(max){}
        
        double size() const{
            return max - min;
        }

        // 闭区间
        bool contains(double x) const{
            return min <= x && x <= max;
        }
        
        /// 开区间
        bool surrounds(double x) const{
            return min < x && x < max;
        }
        
        static const interval empty, universe;
};

const interval interval::empty = interval(+infinity, -infinity);
const interval interval::universe = interval(-infinity, +infinity); 

#endif