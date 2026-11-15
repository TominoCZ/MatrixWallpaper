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
    float headCount;   // the first this many may be a falling head (the rest: digits and signs)
    float hasImage;    // 0: no image, use `fallback`
    float trailFloor;  // a cell never gets darker than this, so the image stays readable in the glyphs
    float lift;        // 0: the image's own brightness; 1: every cell at full brightness in its own hue
    float glide;       // motion: 0 steps cell by cell; 1 smooth light over the fixed glyphs; 2 the head falls as a glyph of its own
    float dropCount;   // drops per column, 1 to 4
    float trailCurve;  // the trail fades as (1 - distance from the head)^trailCurve: 1 evenly, more quickly
    float glow;        // brightness of the halo around each head, 0 for none
    float glowSize;    // its radius, in glyph heights
    float cellAspect;  // a cell's width over its height
    float headWidth;   // motion 1: the head's highlight is a bump of light this many rows wide (standard deviation)
    float cellPixels;  // a cell's height on screen, in pixels
    float atlasRows;   // the glyph texture's height in texels (the nominal cell height)
    float headFade;    // motion 2: 0 the head's glyph crossfades evenly from cell to cell; up to 0.5 the change is quicker, in the middle
    vec2 grid;         // columns, rows
    vec4 crop;         // cell position as a fraction of the grid -> image uv: xy scale, zw offset
    vec4 fallback;
};
layout(binding = 1) uniform sampler2D imageTex;  // about one texel per cell
layout(binding = 2) uniform sampler2D atlasTex;  // one cell per glyph, one texel per pixel
layout(binding = 3) uniform sampler2D dropTex;   // drops.frag: per column (and two either side) and drop, (head, trail length)

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
// Where drop i of column `col` is: x its head's place along the column, in rows (on screen while
// between 0 and the rows on screen plus its trail), y the length of its trail. Worked out once per
// frame for all columns by drops.frag; computing them here took up to 20 drops per pixel with the
// glow, which cost about a third of the GPU on a 5120×1440 screen at 240 fps.
vec2 dropAt(float col, float i) {
    return texture(dropTex, vec2((col + 2.5) / (grid.x + 4.0), (i + 0.5) / 4.0)).xy;
}

// The glyph a cell shows now. Each cell swaps its glyph on its own clock, every 4 to 40 ticks.
// The epoch is kept small because the hash loses its randomness on large inputs; it repeats
// after 512 swaps. Even rows take the glyphs at even places in the set, odd rows those at odd
// places, so a glyph never repeats the one above it, whenever either swaps; a falling head,
// which crossfades from one cell's glyph to the next, always changes.
float cellGlyph(vec2 cell) {
    float every = floor(mix(4.0, 41.0, hash(cell + vec2(0.5, 0.25))));
    float epoch = mod(floor(elapsed(512.0 * every) / every + hash(cell + vec2(0.25, 0.75))), 512.0);
    float parity = glyphCount > 1.0 ? mod(cell.y, 2.0) : 0.0;  // a set of one glyph has to repeat
    float choices = floor((glyphCount - parity + 1.0) / 2.0);  // glyphs at this row's places
    return parity + 2.0 * floor(choices * hash(cell + epoch * vec2(7.0, 3.0)));
}

// The glyph a falling head shows for a cell: the cell's own, unless that may not be a head (a
// digit or a sign, see MatrixRain.notHeads); then a stand-in, its own per cell, from the same
// half of the set, so the head still never repeats or resembles the cell above's.
float headGlyph(vec2 cell) {
    float g = cellGlyph(cell);
    if (g < headCount) return g;
    float parity = mod(g, 2.0);
    float choices = floor((headCount - parity + 1.0) / 2.0);  // head glyphs at this row's places
    return choices < 1.0 ? g : parity + 2.0 * floor(choices * hash(cell + vec2(3.1, 1.7)));
}

// Ink of glyph g at (x, y) within a cell, y in rows from its top, read between two texel rows
// and mixed by how far between them it is: a glyph drawn a fraction of a pixel lower each frame
// moves by that fraction instead of jumping whole pixels.
float inkBetween(float g, float x, float y) {
    float v = y * atlasRows - 0.5;
    float v0 = floor(v);
    float u = (g + x) / glyphCount;
    float a0 = texture(atlasTex, vec2(u, clamp((v0 + 0.5) / atlasRows, 0.0, 1.0))).a;
    float a1 = texture(atlasTex, vec2(u, clamp((v0 + 1.5) / atlasRows, 0.0, 1.0))).a;
    return mix(a0, a1, v - v0);
}

// The light a drop puts on `row` of its own column. x: on the fixed glyph there, 1 at the head
// and fading towards the end of the trail; y: the head there.
//   Motion 0: the light steps cell by cell; the head is the glyph it is on, turned white.
//   Motion 1: both move smoothly over the fixed glyphs. The head's highlight is a symmetric bump
//   of light, `headWidth` rows wide, and the trail's front a soft ramp. A highlight about one
//   glyph tall with a hard front made the white ink an eye follows stall at each gap between
//   glyph rows and jump to the next: judder at 8 to 17 rows a second with 20 to 30 px glyphs.
//   Spread a little wider it crossfades from glyph to glyph; with glyphs fixed on the grid the
//   white still wanders a little with their shapes.
//   Motion 2: the head is a glyph of its own falling smoothly over rows behind 0 to 1 (drawn in
//   main(), over the fixed glyphs); those light up across its height. The smoothest by
//   measurement, but the head is no longer on the grid.
vec2 lightAt(vec2 drop, float row) {
    float behind = drop.x - 1.0 - row;  // rows from the head's front up to here
    float trail = pow(max(0.0, 1.0 - max(behind, 0.0) / drop.y), trailCurve);
    if (glide > 1.5) {
        float px = cellPixels;  // the head's edges are smoothed over one pixel
        return vec2(clamp(behind, 0.0, 1.0) * trail, clamp(behind * px + 0.5, 0.0, 1.0) * clamp((1.0 - behind) * px + 0.5, 0.0, 1.0));
    }
    if (glide > 0.5) {
        float d = (behind - 0.5) / headWidth;  // the highlight's middle is half a row behind the front
        return vec2(smoothstep(-0.5, 0.5, behind) * trail, exp(-0.5 * d * d));
    }
    float arrive = clamp(behind + 1.0, 0.0, 1.0);  // the cell under the head fades in as it comes
    return arrive * vec2(trail, 1.0 - clamp(behind, 0.0, 1.0));
}

void main() {
    vec2 at = qt_TexCoord0 * grid;
    vec2 cell = floor(at);
    // Where this pixel is on the drop's way down: its cell's row, or with `glide` its own
    // height, so that the light front slides down the screen instead of jumping a cell.
    float row = glide > 0.5 ? at.y - 0.5 : cell.y;  // (glide is a mode, 0 to 2, not a weight)

    // This column's drops light its glyphs. With a glow, the heads of the two columns either
    // side are looked at too: each throws a halo that falls to exactly zero at its radius, so no
    // seam shows where the columns it reaches end. The radius is held to what two columns cover.
    vec2 drops = vec2(0.0);
    float headInk = 0.0;  // motion 2: ink of a falling head glyph over this pixel
    float halo = 0.0;
    float radius = min(glowSize, 2.5 * cellAspect);
    float reach = glow > 0.0 ? 2.0 : 0.0;
    for (float dc = -2.0; dc < 2.5; dc += 1.0) {
        if (abs(dc) > reach) continue;
        for (float i = 0.0; i < 4.0; i += 1.0) {
            if (i >= dropCount) break;
            vec2 drop = dropAt(cell.x + dc, i);
            if (dc == 0.0) {
                vec2 lit = lightAt(drop, row);
                drops = max(drops, lit);
                if (glide > 1.5 && lit.y > 0.0) {
                    // The falling head shows the character of the grid cell it is passing: lined
                    // up with a cell it is that cell's glyph, on top of it; between two cells it
                    // crossfades from the one to the next. A head that switched shape at once
                    // jolted an eye following it.
                    float top = drop.x - 1.5;  // the head glyph's top edge, in rows (lined up when whole)
                    float upper = floor(top);
                    float f = smoothstep(headFade, 1.0 - headFade, top - upper);
                    float y = 1.0 - (drop.x - 1.0 - row);  // within the head glyph, rows from its top
                    float x = at.x - cell.x;
                    float ink2 = mix(inkBetween(headGlyph(vec2(cell.x, upper)), x, y),
                                     inkBetween(headGlyph(vec2(cell.x, upper + 1.0)), x, y), f);
                    headInk = max(headInk, lit.y * ink2);
                }
            }
            vec2 off = vec2((at.x - cell.x - dc - 0.5) * cellAspect, at.y - drop.x + 1.0) / radius;
            float q = max(0.0, 1.0 - dot(off, off));
            halo = max(halo, q * q);
        }
    }
    float light = max(trailFloor, drops.x);

    float glyph = cellGlyph(cell);
    float ink = texture(atlasTex, vec2((glyph + at.x - cell.x) / glyphCount, at.y - cell.y)).a;

    vec3 colour = mix(fallback.rgb, texture(imageTex, crop.zw + crop.xy * (cell + 0.5) / grid).rgb, hasImage);
    // Scale by value^-lift: dark cells gain the most, the hue is kept and nothing can clip.
    colour *= pow(max(max(colour.r, max(colour.g, colour.b)), 0.004), -lift);
    vec3 glowColour = mix(colour, vec3(1.0), 0.3) * glow * halo;  // in the gaps between glyphs too
    vec3 headColour = mix(colour, vec3(1.0), 0.6);  // the head of a drop is nearly white
    vec3 lit;
    if (glide > 1.5)  // the falling head is drawn over the fixed glyphs: only its strokes cover them
        lit = colour * light * ink * (1.0 - headInk) + headColour * headInk;
    else if (glide > 0.5)  // the highlight is not dimmed by the soft front: it stays a symmetric bump
        lit = mix(colour * light, headColour, drops.y) * ink;
    else
        lit = mix(colour, headColour, drops.y) * light * ink;
    fragColor = vec4(min(lit + glowColour, vec3(1.0)), 1.0);
}
