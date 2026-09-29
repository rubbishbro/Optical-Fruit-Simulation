Shader "Fruitsim/SensorGlass"
{
    Properties
    {
        _Color ("Glass Tint", Color) = (0.78, 0.90, 1.0, 1)
        _Roughness ("Roughness", Range(0, 1)) = 0.0753
        _IOR ("IOR", Range(1, 3)) = 1.5
        _Transmission ("Transmission", Range(0, 1)) = 1
        _Thickness ("Visual Thickness", Range(0, 1)) = 0.24
    }
    SubShader
    {
        Tags { "RenderType"="Transparent" "Queue"="Transparent" }
        LOD 120
        Blend SrcAlpha OneMinusSrcAlpha
        ZWrite Off
        Cull Off
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
            half _Roughness;
            half _IOR;
            half _Transmission;
            half _Thickness;
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
                float3 normal = normalize(input.normal);
                float3 viewDirection = normalize(_WorldSpaceCameraPos.xyz - input.worldPos);
                float facing = abs(dot(normal, viewDirection));
                float f0 = pow((_IOR - 1.0) / (_IOR + 1.0), 2.0);
                float fresnel = f0 + (1.0 - f0) * pow(1.0 - facing, 5.0);
                float3 lightDirection = normalize(_WorldSpaceLightPos0.xyz - input.worldPos * _WorldSpaceLightPos0.w);
                float3 halfDirection = normalize(lightDirection + viewDirection);
                float highlight = pow(saturate(dot(normal, halfDirection)), lerp(140.0, 12.0, _Roughness));
                float3 color = _Color.rgb * (0.18 + fresnel * 0.82) + _LightColor0.rgb * highlight * 0.8;
                // This WebGL-safe Fresnel/transmission approximation changes
                // only presentation; detector optics still use the contract.
                float alpha = saturate(lerp(0.62, 0.10, _Transmission) + fresnel * 0.48 + _Thickness * 0.10);
                return fixed4(color, alpha);
            }
            ENDCG
        }
    }
    Fallback "Transparent/VertexLit"
}
