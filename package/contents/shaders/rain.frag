#version 440

// Matrix rain as a pure function of (cell, time): no state, one pass, two texture lookups per
// pixel. Baked to rain.frag.qsb by `./run.sh build`. Kept to what GLSL ES 1.00 can do (floats
// only, no texelFetch) so that one source serves every backend Qt may pick.

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float tickHigh;    // the rain's clock, rows fallen by the fastest drops: whole 128s of rows
    float tickLow;     // and the rest, 0 to 128 rows with the fraction (see elapsed())
    float glyphCount;  // glyphs in the atlas, side by side in one row
    float hasImage;    // 0: no image, use `fallback`
    float trailFloor;  // a cell never gets darker than this, so the image stays readable in the glyphs
    float lift;        // 0: the image's own brightness; 1: every cell at full brightness in its own hue
    float glide;       // 0: a glyph is lit as a whole; 1: the light moves through it pixel by pixel
    float dropCount;   // drops per column, 1 to 4
    float trailLength; // trail lengths scaled by this (1: 8 rows up to 70 % of the screen)
    float trailCurve;  // the trail fades as (1 - distance from the head)^trailCurve: 1 evenly, more quickly
    float glow;        // brightness of the halo around each head, 0 for none
    float glowSize;    // its radius, in glyph heights
    float cellAspect;  // a cell's width over its height
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

// The clock modulo m (a whole number up to 65535), exact however long it has run. A single
// 32-bit float clock loses its fraction as it grows: after five hours the rain moved in whole
// pixel steps. In two parts, and with everything below repeating after a whole number of rows,
// the shader only ever works with small numbers.
float elapsed(float m) {
    float whole = floor(tickLow);
    return mod(mod(tickHigh, m) * 128.0 + whole, m) + (tickLow - whole);
}

// Where drop `seed` of column `col` is: x its head's place along the column, in rows (it is on
// screen while between 0 and the rows on screen plus its trail), y the length of its trail.
// Speed, length and the gap before it comes round again are fixed per column and seed. The
// speed is a whole number of 32nds of a row per tick, so the drop's place repeats exactly every
// 32 periods of the clock.
vec2 dropAt(float col, float seed) {
    float speed = floor(mix(10.0, 33.0, hash(vec2(col, seed)))) / 32.0;  // 0.31 to 1 row per tick
    float len = max(2.0, floor(mix(8.0, 0.7 * grid.y, hash(vec2(col, seed + 1.0))) * trailLength));
    float period = floor(grid.y + len + grid.y * hash(vec2(col, seed + 2.0)));
    float start = floor(period * hash(vec2(col, seed + 3.0)));
    return vec2(mod(elapsed(32.0 * period) * speed + start, period), len);
}

// The light a drop puts on `row` of its own column. x: its trail, 1 at the head and fading
// towards the end; y: the head itself, 1 there and gone one row behind it. Both move
// continuously with the clock, so the rain is as smooth as the frame rate.
vec2 lightAt(vec2 drop, float row) {
    float behind = drop.x - 1.0 - row;  // rows from the head up to here
    float arrive = clamp(behind + 1.0, 0.0, 1.0);  // the cell under the head fades in as it comes
    float trail = pow(max(0.0, 1.0 - max(behind, 0.0) / drop.y), trailCurve);
    return arrive * vec2(trail, 1.0 - clamp(behind, 0.0, 1.0));
}

void main() {
    vec2 at = qt_TexCoord0 * grid;
    vec2 cell = floor(at);
    // Where this pixel is on the drop's way down: its cell's row, or with `glide` its own
    // height, so that the light front slides down the screen instead of jumping a cell.
    float row = mix(cell.y, at.y - 0.5, glide);

    // This column's drops light its glyphs. With a glow, the heads of the two columns either
    // side are looked at too: each throws a halo that falls to exactly zero at its radius, so no
    // seam shows where the columns it reaches end. The radius is held to what two columns cover.
    vec2 drops = vec2(0.0);
    float halo = 0.0;
    float radius = min(glowSize, 2.5 * cellAspect);
    float reach = glow > 0.0 ? 2.0 : 0.0;
    for (float dc = -2.0; dc < 2.5; dc += 1.0) {
        if (abs(dc) > reach) continue;
        for (float i = 0.0; i < 4.0; i += 1.0) {
            if (i >= dropCount) break;
            vec2 drop = dropAt(cell.x + dc, 7.0 * i);
            if (dc == 0.0) drops = max(drops, lightAt(drop, row));
            vec2 off = vec2((at.x - cell.x - dc - 0.5) * cellAspect, at.y - drop.x + 1.0) / radius;
            float q = max(0.0, 1.0 - dot(off, off));
            halo = max(halo, q * q);
        }
    }
    float light = max(trailFloor, drops.x);

    // Each cell swaps its glyph on its own clock, every 4 to 40 ticks. The epoch is kept small
    // because the hash loses its randomness on large inputs; it repeats after 512 swaps.
    float every = floor(mix(4.0, 41.0, hash(cell + vec2(0.5, 0.25))));
    float epoch = mod(floor(elapsed(512.0 * every) / every + hash(cell + vec2(0.25, 0.75))), 512.0);
    float glyph = floor(glyphCount * hash(cell + epoch * vec2(7.0, 3.0)));
    float ink = texture(atlasTex, vec2((glyph + at.x - cell.x) / glyphCount, at.y - cell.y)).a;

    vec3 colour = mix(fallback.rgb, texture(imageTex, crop.zw + crop.xy * (cell + 0.5) / grid).rgb, hasImage);
    // Scale by value^-lift: dark cells gain the most, the hue is kept and nothing can clip.
    colour *= pow(max(max(colour.r, max(colour.g, colour.b)), 0.004), -lift);
    vec3 glowColour = mix(colour, vec3(1.0), 0.3) * glow * halo;  // in the gaps between glyphs too
    colour = mix(colour, vec3(1.0), 0.6 * drops.y);  // the head of a drop is nearly white
    fragColor = vec4(min(colour * light * ink + glowColour, vec3(1.0)), 1.0);
}
