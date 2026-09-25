// ─────────────────────────────────────────────────────────────────────
// PHOSPHOR — a CRT for your terminal.
//
// This shader does physics, not colour. The green comes from the Ghostty
// palette; everything here is what a real phosphor tube does to it:
// glass curvature, aperture grille, scanlines, bloom, mains hum, and a
// beam that reacts to the cursor and to focus.
//
// Runs on the GPU every frame. Three things animate off real events:
//   iTimeCursorChange — the beam blooms when the cursor moves (typing)
//   iTimeFocus        — the tube warms up when a pane takes focus
//   iFocus            — unfocused panes fall back and dim
// ─────────────────────────────────────────────────────────────────────

#define GLASS        12.7     // barrel curvature; higher = flatter.
                                 // Displacement falls off as 1/GLASS^2, so
                                 // each step of x1.41 halves the bulge:
                                 // 6.4 -> 9.0 -> 12.7.
#define SCANLINE     0.13    // scanline depth
#define GRILLE       0.10    // aperture-grille depth
#define BLOOM        0.70    // glow strength
#define HUM          0.016   // mains-hum bar
#define VIGNETTE     0.22
#define ABERRATION   0.0030
#define BOOT         0.42    // seconds of warm-up on focus
#define DEGAUSS      0.55    // seconds of degauss wobble on focus
#define ALARM        0.9     // amber flare when a command fails
#define TRAIL        0.11    // seconds the beam smears behind the cursor
#define GAIN         1.20    // scanlines and vignette cost brightness; buy it back

float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

// Bend the flat text plane onto tube glass.
vec2 curve(vec2 uv) {
    uv = uv * 2.0 - 1.0;
    vec2 off = abs(uv.yx) / vec2(GLASS, GLASS * 0.72);
    uv += uv * off * off;
    return uv * 0.5 + 0.5;
}

// Ring-tap bloom. Cheap, and the only thing that sells "this is glowing
// rather than printed".
vec3 bloom(vec2 uv, float radius) {
    vec3 sum = vec3(0.0);
    const int TAPS = 12;
    for (int i = 0; i < TAPS; i++) {
        float a = 6.28318 * (float(i) / float(TAPS));
        vec2 o = vec2(cos(a), sin(a)) * radius / iResolution.xy;
        sum += texture(iChannel0, uv + o).rgb;
        sum += texture(iChannel0, uv + o * 0.5).rgb * 0.6;
    }
    return sum / (float(TAPS) * 1.6);
}

// Distance from a point to the segment the beam sweeps between two cursor
// positions. This is what makes typing feel like a beam rather than a redraw.
float sdSegment(vec2 p, vec2 a, vec2 b) {
    vec2 pa = p - a;
    vec2 ba = b - a;
    float h = clamp(dot(pa, ba) / max(dot(ba, ba), 0.0001), 0.0, 1.0);
    return length(pa - ba * h);
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv  = fragCoord / iResolution.xy;
    vec2 cuv = curve(uv);

    // Beyond the glass is bezel, not screen.
    if (cuv.x < 0.0 || cuv.x > 1.0 || cuv.y < 0.0 || cuv.y > 1.0) {
        fragColor = vec4(iBackgroundColor * 0.25, 1.0);
        return;
    }

    float focused  = iFocus > 0 ? 1.0 : 0.0;
    float sinceCur = iTime - iTimeCursorChange;
    float sinceFoc = iTime - iTimeFocus;

    // ── warm-up: a bright band sweeps the tube when a pane takes focus
    float boot = clamp(1.0 - sinceFoc / BOOT, 0.0, 1.0);
    float bootEase = boot * boot;
    float sweepY = 1.0 - boot;
    float sweep = exp(-pow((cuv.y - sweepY) * 9.0, 2.0)) * bootEase;

    // ── the beam blooms while you type, then settles
    float strike = exp(-sinceCur * 7.0);

    // ── degauss: a real tube shakes its picture when it powers up. The
    //    wobble runs down the screen and dies out in about half a second.
    float dg = exp(-sinceFoc * 6.5) * (sinceFoc < DEGAUSS ? 1.0 : 0.0);
    cuv.x += sin(cuv.y * 34.0 + sinceFoc * 46.0) * 0.0075 * dg;
    cuv.y += cos(cuv.x * 21.0 + sinceFoc * 38.0) * 0.0026 * dg;
    cuv = clamp(cuv, 0.0, 1.0);

    // ── chromatic aberration, stronger toward the corners
    vec2  d  = cuv - 0.5;
    float ab = dot(d, d) * ABERRATION * (1.0 + strike * 0.8);
    vec3  col;
    col.r = texture(iChannel0, cuv + d * ab).r;
    col.g = texture(iChannel0, cuv).g;
    col.b = texture(iChannel0, cuv - d * ab).b;

    // ── glow
    float glow = BLOOM * (0.85 + strike * 0.55 + bootEase * 0.9);
    col += bloom(cuv, 2.2) * glow * 0.55;
    col += bloom(cuv, 5.5) * glow * 0.30;

    // ── cursor halo: the beam is hottest where it rests
    vec2 curPx = vec2(iCurrentCursor.x + iCurrentCursor.z * 0.5,
                      iCurrentCursor.y - iCurrentCursor.w * 0.5);
    float cdist = length((fragCoord - curPx) / iResolution.y);
    float halo  = exp(-cdist * 26.0) * (0.16 + strike * 0.42) * focused;
    col += iCursorColor * halo;

    // ── beam smear: the phosphor behind the cursor has not decayed yet, so
    //    a bright streak hangs between where the cursor was and where it is
    vec2 prevPx = vec2(iPreviousCursor.x + iPreviousCursor.z * 0.5,
                       iPreviousCursor.y - iPreviousCursor.w * 0.5);
    float width = max(iCurrentCursor.z, 2.0) * 0.62;
    float seg   = sdSegment(fragCoord, prevPx, curPx);
    float trail = (1.0 - smoothstep(0.0, width, seg))
                * exp(-sinceCur / TRAIL) * focused;
    col += iCurrentCursorColor.rgb * trail * 0.85;

    // ── aperture grille + scanlines, in screen space so they stay crisp
    float grille = 1.0 - GRILLE * (0.5 + 0.5 * cos(fragCoord.x * 3.14159));
    float scan   = 1.0 - SCANLINE * (0.5 + 0.5 * sin(fragCoord.y * 3.14159
                                     + iTime * 0.6));
    col *= grille * scan;

    // ── mains hum: a faint bar drifting down the tube, forever
    float hum = 1.0 + HUM * sin((cuv.y + iTime * 0.09) * 6.28318);
    col *= hum;

    // ── interlace flicker, small enough to feel rather than see
    col *= 1.0 + 0.010 * sin(iTime * 62.0);

    // ── the warm-up band itself
    col += iForegroundColor * sweep * 0.75;
    col *= 1.0 + bootEase * 0.35 + dg * 0.10;

    // ── unfocused panes recede: dimmer, flatter, heavier scanlines
    col = mix(col * 0.52 * (1.0 - SCANLINE * 0.35), col, 0.35 + 0.65 * focused);

    col *= GAIN;

    // ── alarm. The shell sets the cursor amber on a failed command, which
    //    also stamps iTimeCursorChange — so the tube flares at the exact
    //    moment something goes wrong, and settles on its own.
    float amber = clamp((iCurrentCursorColor.r - iCurrentCursorColor.g) * 3.0,
                        0.0, 1.0);
    float flare = amber * exp(-sinceCur * 3.2) * ALARM;
    col += vec3(1.0, 0.62, 0.0) * flare * (0.05 + dot(d, d) * 0.85);
    col *= 1.0 + flare * 0.12;

    // ── vignette
    float vig = 1.0 - VIGNETTE * dot(d, d) * 3.4;
    col *= clamp(vig, 0.0, 1.0);

    // ── phosphor never goes truly black; the glass always has a little
    //    ambient green sitting in it
    col = max(col, iBackgroundColor * 0.85);

    fragColor = vec4(col, 1.0);
}
