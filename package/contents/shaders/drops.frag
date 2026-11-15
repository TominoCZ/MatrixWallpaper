#version 440

// Every drop's place, worked out once per frame for the whole screen. Texel (column + 2, drop i)
// holds (x) the head's place along its column in rows and (y) its trail's length; two extra
// columns either side cover what the glow reaches past the screen's edges. rain.frag looks them
// up. Rendered into a 32-bit float layer: positions keep their fractions (a 16-bit one lost them
// above 256 rows).

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float tickHigh;    // the rain's clock, as in rain.frag
    float tickLow;
    float trailLength; // trail lengths scaled by this (1: 8 rows up to 70 % of the screen)
    vec2 grid;         // columns, rows
};

// Dave Hoskins' hash12: no sin(), so it gives the same numbers on every GPU.
float hash(vec2 p) {
    vec3 q = fract(vec3(p.xyx) * 0.1031);
    q += dot(q, q.yzx + 33.33);
    return fract((q.x + q.y) * q.z);
}

// The clock modulo m (a whole number up to 65535), exact however long it has run. A single
// 32-bit float clock loses its fraction as it grows: after five hours the rain moved in whole
// pixel steps. In two parts, and with everything below repeating after a whole number of rows,
// the shader only ever works with small numbers.
float elapsed(float m) {
    float whole = floor(tickLow);
    return mod(mod(tickHigh, m) * 128.0 + whole, m) + (tickLow - whole);
}

// The trail's length follows the speed, as if each glyph faded over time once the head had
// passed: a faster drop leaves a longer trail (the fastest about 1.5 times the drawn length, the
// slowest about half; on average as before). Drawn independently, a fast drop with a short tail
// looked wrong.
vec4 dropShape(float col, float seed) {  // speed, trail length, period, start
    float speed = floor(mix(10.0, 33.0, hash(vec2(col, seed)))) / 32.0;  // 0.31 to 1 row per tick
    float len = max(2.0, floor(mix(8.0, 0.7 * grid.y, hash(vec2(col, seed + 1.0))) * trailLength * speed * 1.5));
    float period = floor(grid.y + len + grid.y * hash(vec2(col, seed + 2.0)));
    return vec4(speed, len, period, floor(period * hash(vec2(col, seed + 3.0))));
}
vec2 dropAt(float col, float seed) {
    vec4 s = dropShape(col, seed);
    return vec2(mod(elapsed(32.0 * s.z) * s.x + s.w, s.z), s.y);
}

void main() {
    float col = floor(qt_TexCoord0.x * (grid.x + 4.0)) - 2.0;
    float i = floor(qt_TexCoord0.y * 4.0);
    fragColor = vec4(dropAt(col, 7.0 * i), 0.0, 1.0);
}
