Shader "Fruitsim/RigSurface"
{
    Properties
    {
        _Color ("Color", Color) = (0.22, 0.24, 0.28, 1)
        _Roughness ("Roughness", Range(0, 1)) = 0.5
        _Metallic ("Metallic", Range(0, 1)) = 0
        _CoatWeight ("Coat Weight", Range(0, 1)) = 0
        _EmissionColor ("Emission Color", Color) = (0, 0, 0, 1)
        _EmissionStrength ("Emission Strength", Range(0, 12)) = 0
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" "Queue"="Geometry" }
        LOD 100
        ZWrite On
        Pass
        {
            Tags { "LightMode"="ForwardBase" }
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"
            #include "Lighting.cginc"
            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; };
            struct v2f { float4 vertex : SV_POSITION; float3 normal : TEXCOORD0; float3 worldPos : TEXCOORD1; };
            fixed4 _Color;
            fixed4 _EmissionColor;
            half _Roughness;
            half _Metallic;
            half _CoatWeight;
            half _EmissionStrength;
            v2f vert(appdata input)
            {
                v2f output;
                output.vertex = UnityObjectToClipPos(input.vertex);
                output.normal = UnityObjectToWorldNormal(input.normal);
                output.worldPos = mul(unity_ObjectToWorld, input.vertex).xyz;
                return output;
            }
            fixed4 frag(v2f input) : SV_Target
            {
                float3 n = normalize(input.normal);
                float3 l = normalize(_WorldSpaceLightPos0.xyz - input.worldPos * _WorldSpaceLightPos0.w);
                float3 v = normalize(_WorldSpaceCameraPos.xyz - input.worldPos);
                float3 h = normalize(l + v);
                float diffuse = saturate(dot(n, l));
                float specular = pow(saturate(dot(n, h)), lerp(96.0, 5.0, _Roughness));
                float3 ambient = max(ShadeSH9(float4(n, 1.0)), float3(0.12, 0.12, 0.12));
                float3 lit = _Color.rgb * (ambient + _LightColor0.rgb * diffuse * (1.0 - _Metallic));
                lit += _LightColor0.rgb * specular * lerp(0.03.xxx, _Color.rgb, _Metallic) * (0.2 + _CoatWeight * 0.8);
                lit += _EmissionColor.rgb * _EmissionStrength;
                return fixed4(lit, 1.0);
            }
            ENDCG
        }
    }
    Fallback "Diffuse"
}
