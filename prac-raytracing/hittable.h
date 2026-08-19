#ifndef HITTABLE_H
#define HITTABLE_H

class hit_record{
    public:
        point3 p; // 交点
        vec3 normal; // 法线
        double t; // 交点距离
        bool front_face; // 是否为正面

        // 设置法线方向，使其总是指向射线的外侧
        void set_face_normal(const ray& r, const vec3& outward_normal){
            // 判断射线是否与法线同向
            front_face = dot(r.direction(), outward_normal) < 0;
            normal = front_face ? outward_normal : -outward_normal;
        }
};

class hittable{
    public:
        virtual ~hittable() = default;
        virtual bool hit(const ray& r, interval ray_t, hit_record& rec) const = 0;
};

#endif
