//!HOOK OUTPUT
//!BIND HOOKED
//!DESC Convert absolute PQ output to extended sRGB without clipping HDR
vec4 hook() {
    vec4 colour = HOOKED_tex(HOOKED_pos);
    // ST 2084 encodes absolute luminance; 203 cd/m2 is SDR reference white.
    vec3 pq = pow(max(colour.rgb, vec3(0.0)), vec3(32.0 / 2523.0));
    vec3 linear = pow(max(pq - 3424.0 / 4096.0, vec3(0.0)) /
                      (2413.0 / 128.0 - 2392.0 / 128.0 * pq),
                      vec3(16384.0 / 2610.0)) * (10000.0 / 203.0);
    colour.rgb = mix(1.055 * pow(linear, vec3(1.0 / 2.4)) - 0.055,
                     12.92 * linear, lessThanEqual(linear, vec3(0.0031308)));
    return colour;
}
