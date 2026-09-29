Shader "Fruitsim/AppleSkin"
{
    Properties
    {
        _Color ("Skin Color", Color) = (0.58, 0.025, 0.012, 1)
        _Roughness ("Roughness", Range(0, 1)) = 0.46
        _Metallic ("Metallic", Range(0, 1)) = 0
        _SpecularIORLevel ("Specular IOR Level", Range(0, 1)) = 0.5
        _IOR ("IOR", Range(1, 3)) = 1.45
        _SpotDensity ("Lenticel Density", Range(0, 1)) = 0.06
        _NormalStrength ("Micro Normal Strength", Range(0, 1)) = 0.025
        _SkinTransmission ("Skin Light Transmission", Range(0, 1)) = 0.16
        _SpotSeed ("Skin Seed", Range(0, 1)) = 0.5
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" "Queue"="Geometry" }
        LOD 150
        ZWrite On

        Pass
        {
            Tags { "LightMode"="ForwardBase" }
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fwdbase
            #include "UnityCG.cginc"
            #include "Lighting.cginc"

            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; };
            struct v2f
            {
                float4 vertex : SV_POSITION;
                float3 worldNormal : TEXCOORD0;
                float3 worldPosition : TEXCOORD1;
                float3 objectPosition : TEXCOORD2;
            };

            fixed4 _Color;
            half _Roughness;
            half _Metallic;
            half _SpecularIORLevel;
            half _IOR;
            half _SpotDensity;
            half _NormalStrength;
            half _SkinTransmission;
            half _SpotSeed;

            float hash31(float3 p)
            {
                p = frac(p * 0.1031);
                p += dot(p, p.yzx + 33.33);
                return frac((p.x + p.y) * p.z);
            }

            float valueNoise(float3 p)
            {
                float3 cell = floor(p);
                float3 f = frac(p);
                f = f * f * (3.0 - 2.0 * f);
                float n000 = hash31(cell + float3(0, 0, 0));
                float n100 = hash31(cell + float3(1, 0, 0));
                float n010 = hash31(cell + float3(0, 1, 0));
                float n110 = hash31(cell + float3(1, 1, 0));
                float n001 = hash31(cell + float3(0, 0, 1));
                float n101 = hash31(cell + float3(1, 0, 1));
                float n011 = hash31(cell + float3(0, 1, 1));
                float n111 = hash31(cell + float3(1, 1, 1));
                float nx00 = lerp(n000, n100, f.x);
                float nx10 = lerp(n010, n110, f.x);
                float nx01 = lerp(n001, n101, f.x);
                float nx11 = lerp(n011, n111, f.x);
                return lerp(lerp(nx00, nx10, f.y), lerp(nx01, nx11, f.y), f.z);
            }

            v2f vert(appdata input)
            {
                v2f output;
                output.vertex = UnityObjectToClipPos(input.vertex);
                output.worldNormal = UnityObjectToWorldNormal(input.normal);
                output.worldPosition = mul(unity_ObjectToWorld, input.vertex).xyz;
                // Object-space coordinates make skin detail follow the fruit
                // when students rotate, move, or scale the generated sample.
                output.objectPosition = input.vertex.xyz;
                return output;
            }

            fixed4 frag(v2f input) : SV_Target
            {
                float3 seedOffset = float3(_SpotSeed * 41.0, _SpotSeed * 17.0, _SpotSeed * 29.0);
                // The authored mesh is in millimetre-like Blender units.
                // These frequencies produce broad blush variation plus a few
                // dozen lenticel cells across the fruit, not pixel noise.
                float3 skinP = input.objectPosition * 0.055 + seedOffset;
                float broad = valueNoise(skinP);
                float3 microP = input.objectPosition * 0.58 + seedOffset * 3.1;
                float micro = valueNoise(microP);
                float epsilon = 0.035;
                float3 gradient = float3(
                    valueNoise(microP + float3(epsilon, 0, 0)) - micro,
                    valueNoise(microP + float3(0, epsilon, 0)) - micro,
                    valueNoise(microP + float3(0, 0, epsilon)) - micro);
                float3 normal = normalize(input.worldNormal + UnityObjectToWorldDir(gradient) * _NormalStrength * 1.4);

                float threshold = lerp(1.01, 0.82, saturate(_SpotDensity));
                float lenticel = smoothstep(threshold, min(0.995, threshold + 0.08), micro);
                float3 blush = _Color.rgb * lerp(0.88, 1.06, broad);
                float3 warmVariation = lerp(blush * float3(0.96, 1.02, 0.86), blush, saturate(broad * 1.35));
                float3 lenticelColor = lerp(float3(0.24, 0.08, 0.025), float3(0.78, 0.57, 0.24), broad);
                float3 baseColor = lerp(warmVariation, lenticelColor, lenticel * 0.26);

                float3 lightVector = _WorldSpaceLightPos0.xyz - input.worldPosition * _WorldSpaceLightPos0.w;
                float3 lightDirection = normalize(lightVector);
                float diffuse = saturate(dot(normal, lightDirection));
                float3 viewDirection = normalize(_WorldSpaceCameraPos.xyz - input.worldPosition);
                float3 halfDirection = normalize(lightDirection + viewDirection);
                float iorF0 = pow((_IOR - 1.0) / (_IOR + 1.0), 2.0) * _SpecularIORLevel;
                float specularPower = lerp(96.0, 5.0, _Roughness);
                float specular = pow(saturate(dot(normal, halfDirection)), specularPower);
                float3 specularColor = lerp(iorF0.xxx, baseColor, _Metallic);
                float3 ambient = max(ShadeSH9(float4(normal, 1.0)), float3(0.24, 0.24, 0.24));
                float3 lit = baseColor * (ambient + _LightColor0.rgb * diffuse * (1.0 - _Metallic));
                lit += _LightColor0.rgb * specularColor * specular * lerp(0.8, 0.12, _Roughness);
                float backScatter = pow(saturate(dot(-normal, lightDirection)), 2.0);
                float rimLight = pow(1.0 - saturate(dot(normal, viewDirection)), 2.0);
                lit += baseColor * (backScatter * 0.20 + rimLight * 0.10) * _SkinTransmission;
                return fixed4(lit, 1.0);
            }
            ENDCG
        }
    }
    Fallback "Diffuse"
}
