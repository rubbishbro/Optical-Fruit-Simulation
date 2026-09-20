Shader "Fruitsim/SolidColor"
{
    Properties
    {
        _Color ("Color", Color) = (1, 1, 1, 1)
        _Roughness ("Roughness", Range(0, 1)) = 0.68
        _SpotDensity ("Spot Density", Range(0, 1)) = 0
        _NormalStrength ("Normal Strength", Range(0, 1)) = 0
        _SpotSeed ("Spot Seed", Range(0, 1)) = 0.5
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" "Queue"="Geometry" }
        LOD 100

        Pass
        {
            Tags { "LightMode"="ForwardBase" }
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            struct appdata
            {
                float4 vertex : POSITION;
                float3 normal : NORMAL;
            };

            struct v2f
            {
                float4 vertex : SV_POSITION;
                float3 worldNormal : TEXCOORD0;
                float3 worldPosition : TEXCOORD1;
            };

            fixed4 _Color;
            half _Roughness;
            half _SpotDensity;
            half _NormalStrength;
            half _SpotSeed;

            float hash31(float3 value)
            {
                value = frac(value * 0.1031);
                value += dot(value, value.yzx + 33.33);
                return frac((value.x + value.y) * value.z);
            }

            v2f vert(appdata input)
            {
                v2f output;
                output.vertex = UnityObjectToClipPos(input.vertex);
                output.worldNormal = UnityObjectToWorldNormal(input.normal);
                output.worldPosition = mul(unity_ObjectToWorld, input.vertex).xyz;
                return output;
            }

            fixed4 frag(v2f input) : SV_Target
            {
                float3 normal = normalize(input.worldNormal);
                float3 lightDirection = normalize(_WorldSpaceLightPos0.xyz);
                float frequency = 6.0 + _SpotDensity * 42.0;
                float3 noisePosition = input.worldPosition * frequency + _SpotSeed * 37.0;
                float noise = hash31(noisePosition);
                float spots = smoothstep(0.74, 0.96, noise) * saturate(_SpotDensity * 7.0);
                float noiseX = hash31(noisePosition + float3(0.035, 0.0, 0.0));
                float noiseY = hash31(noisePosition + float3(0.0, 0.035, 0.0));
                float noiseZ = hash31(noisePosition + float3(0.0, 0.0, 0.035));
                normal = normalize(normal + (float3(noiseX, noiseY, noiseZ) - noise) * _NormalStrength * 1.8);
                float diffuse = saturate(dot(normal, lightDirection));
                float3 viewDirection = normalize(_WorldSpaceCameraPos.xyz - input.worldPosition);
                float rim = pow(1.0 - saturate(dot(normal, viewDirection)), 3.0) * 0.16;
                float3 halfDirection = normalize(lightDirection + viewDirection);
                float specularPower = lerp(64.0, 4.0, _Roughness);
                float specular = pow(saturate(dot(normal, halfDirection)), specularPower);
                specular *= lerp(0.24, 0.035, _Roughness);
                float3 baseColor = lerp(_Color.rgb, _Color.rgb * 0.62, spots);
                float illumination = 0.34 + 0.66 * diffuse + rim;
                return fixed4(baseColor * illumination + specular, _Color.a);
            }
            ENDCG
        }
    }
    Fallback "Unlit/Color"
}
