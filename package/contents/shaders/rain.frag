#version 440

// Matrix rain as a pure function of (cell, tick): no state, one pass, two texture lookups per
// pixel. Baked to rain.frag.qsb by `./run.sh build`. Kept to what GLSL ES 1.00 can do (floats
// only, no texelFetch) so that one source serves every backend Qt may pick.

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float tick;        // the rain's clock: rows fallen so far by the fastest drops
    float glyphCount;  // glyphs in the atlas, side by side in one row
    float hasImage;    // 0: no image, use `fallback`
    float trailFloor;  // a cell never gets darker than this, so the image stays readable in the glyphs
    float lift;        // 0: the image's own brightness; 1: every cell at full brightness in its own hue
    float glide;       // 0: a glyph is lit as a whole; 1: the light moves through it pixel by pixel
    vec2 grid;         // columns, rows
    vec4 crop;         // cell position as a fraction of the grid -> image uv: xy scale, zw offset
    vec4 fallback;
};
layout(binding = 1) uniform sampler2D imageTex;  // about one texel per cell
layout(binding = 2) uniform sampler2D atlasTex;  // one cell per glyph, one texel per pixel

// Dave Hoskins' hash12: no sin(), so it gives the same numbers on every GPU.
float hash(vec2 p) {
    vec3 q = fract(vec3(p.xyx) * 0.1031);
    q += dot(q, q.yzx + 33.33);
    return fract((q.x + q.y) * q.z);
}

// One drop falling down this cell's column, seen from `row`. x: its light here, 1 at the head and fading up the
// trail; y: how much of the head is here, 1 where the head is and gone one row behind it.
// Both change continuously with the tick, so the rain is as smooth as the frame rate.
// Speed, length and the gap before it comes round again are fixed per column and seed.
vec2 drop(vec2 cell, float row, float seed) {
    float speed = mix(0.3, 1.0, hash(vec2(cell.x, seed)));  // rows per tick
    float len = floor(mix(8.0, 0.7 * grid.y, hash(vec2(cell.x, seed + 1.0))));
    float period = floor(grid.y + len + grid.y * hash(vec2(cell.x, seed + 2.0)));
    float start = floor(period * hash(vec2(cell.x, seed + 3.0)));
    float behind = mod(tick * speed + start, period) - 1.0 - row;  // rows from the head up to here
    float arrive = clamp(behind + 1.0, 0.0, 1.0);  // the cell under the head fades in as it comes
    return arrive * vec2(max(0.0, 1.0 - max(behind, 0.0) / len), 1.0 - clamp(behind, 0.0, 1.0));
}

void main() {
    vec2 at = qt_TexCoord0 * grid;
    vec2 cell = floor(at);
    // Where this pixel is on the drop's way down: its cell's row, or with `glide` its own
    // height, so that the light front slides down the screen instead of jumping a cell.
    float row = mix(cell.y, at.y - 0.5, glide);
    vec2 drops = max(drop(cell, row, 0.0), drop(cell, row, 7.0));
    float light = max(trailFloor, drops.x);

    // Each cell swaps its glyph on its own clock. The epoch is kept small because the hash
    // loses its randomness on large inputs.
    float every = mix(4.0, 40.0, hash(cell + vec2(0.5, 0.25)));
    float epoch = mod(floor(tick / every + hash(cell + vec2(0.25, 0.75))), 512.0);
    float glyph = floor(glyphCount * hash(cell + epoch * vec2(7.0, 3.0)));
    float ink = texture(atlasTex, vec2((glyph + at.x - cell.x) / glyphCount, at.y - cell.y)).a;

    vec3 colour = mix(fallback.rgb, texture(imageTex, crop.zw + crop.xy * (cell + 0.5) / grid).rgb, hasImage);
    // Scale by value^-lift: dark cells gain the most, the hue is kept and nothing can clip.
    colour *= pow(max(max(colour.r, max(colour.g, colour.b)), 0.004), -lift);
    colour = mix(colour, vec3(1.0), 0.6 * drops.y);  // the head of a drop is nearly white
    fragColor = vec4(colour * light * ink, 1.0);
}
