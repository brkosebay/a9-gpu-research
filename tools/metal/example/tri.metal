#include <metal_stdlib>
using namespace metal;
struct V { float4 pos [[position]]; };
vertex V v_tri(uint vid [[vertex_id]]) {
  float2 p[3] = { float2(-1,-1), float2(1,-1), float2(0,1) };
  V o; o.pos = float4(p[vid], 0, 1); return o;
}
fragment half4 f_red() { return half4(1,0,0,1); }
kernel void k_fill(device uint *o [[buffer(0)]], uint i [[thread_position_in_grid]]) { o[i] = 3*i + 7; }
