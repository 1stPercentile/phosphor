// Phosphor: a cmux sidebar. Market board, the sky, and Pip.
//
// TEMPLATE: engine/render_sidebar.py bakes this into
// ~/.config/cmux/sidebars/phosphor.swift every minute and cmux hot-reloads it
// on save. Edit THIS file, never that one. Baking the numbers into the source
// is how prices get in at all: the sidebar runtime has no network and no
// filesystem.
//
// Colours are written out in full on purpose. The interpreter does NOT resolve
// a `let` constant inside a modifier: it silently falls back to the default
// colour.
//
//   #020703 ground   #050D08 board   #0C2A17 rule
//   #1F8F4E chrome   #41FF8D live    #EAFFF3 hot   #FFB000 amber (down / wrong)

// A 48-stop wheel. The sidebar redraws about once a second and that is a hard
// ceiling — Claude Code's own max-effort shimmer is smooth because it runs
// inside Claude's render loop at many frames a second, which nothing here can
// reach. So the smoothness has to live in SPACE: a fine gradient laid across
// many narrow segments, crawling slowly, reads as shimmer instead of strobe.
func hue(_ i: Int) -> String {
    let n = ((i % 48) + 48) % 48
    return n == 0 ? "#FF2626" : n == 1 ? "#FF4126" : n == 2 ? "#FF5C26" : n == 3 ? "#FF7726" : n == 4 ? "#FF9226" : n == 5 ? "#FFAD26" : n == 6 ? "#FFC826" : n == 7 ? "#FFE326" : n == 8 ? "#FFFF26" : n == 9 ? "#E3FF26" : n == 10 ? "#C8FF26" : n == 11 ? "#ADFF26" : n == 12 ? "#92FF26" : n == 13 ? "#77FF26" : n == 14 ? "#5CFF26" : n == 15 ? "#41FF26" : n == 16 ? "#26FF26" : n == 17 ? "#26FF41" : n == 18 ? "#26FF5C" : n == 19 ? "#26FF77" : n == 20 ? "#26FF92" : n == 21 ? "#26FFAD" : n == 22 ? "#26FFC8" : n == 23 ? "#26FFE3" : n == 24 ? "#26FFFF" : n == 25 ? "#26E3FF" : n == 26 ? "#26C8FF" : n == 27 ? "#26ADFF" : n == 28 ? "#2692FF" : n == 29 ? "#2677FF" : n == 30 ? "#265CFF" : n == 31 ? "#2641FF" : n == 32 ? "#2626FF" : n == 33 ? "#4126FF" : n == 34 ? "#5C26FF" : n == 35 ? "#7726FF" : n == 36 ? "#9226FF" : n == 37 ? "#AD26FF" : n == 38 ? "#C826FF" : n == 39 ? "#E326FF" : n == 40 ? "#FF26FF" : n == 41 ? "#FF26E3" : n == 42 ? "#FF26C8" : n == 43 ? "#FF26AD" : n == 44 ? "#FF2692" : n == 45 ? "#FF2677" : n == 46 ? "#FF265C" : "#FF2641"
}

// ── the panel ─────────────────────────────────────────────────────────
VStack(alignment: .leading, spacing: 0) {

    // ═══ the board ════════════════════════════════════════════════════
    // Big, high contrast, arrows carrying the sign — a wall, not a table.
    VStack(alignment: .leading, spacing: 4) {
        // The wordmark cycles through the spectrum a step a second — the
        // one place on the whole tube that is allowed to be more than green.
        HStack(spacing: 6) {
            HStack(spacing: 0) {
                Text("M").foregroundColor(hue(clock.second * 2))
                Text("A").foregroundColor(hue(clock.second * 2 + 1 * 2))
                Text("R").foregroundColor(hue(clock.second * 2 + 2 * 2))
                Text("K").foregroundColor(hue(clock.second * 2 + 3 * 2))
                Text("E").foregroundColor(hue(clock.second * 2 + 4 * 2))
                Text("T").foregroundColor(hue(clock.second * 2 + 5 * 2))
            }
            .font(.system(size: 11, design: .monospaced))
            .bold()
            Spacer()
            Text("24H").foregroundColor("#1F8F4E")
                .font(.system(size: 9, design: .monospaced))
            Text(clock.time).foregroundColor("#0C2A17")
                .font(.system(size: 10, design: .monospaced))
                .monospacedDigit()
        }

        // An LED strip under the heading, drifting the other way.
        HStack(spacing: 0) {
            ForEach(0..<40) { i in
                Rectangle().fill(hue(i - clock.second * 2)).frame(height: 2)
            }
        }
        .padding(.top, 3)

// {{TICKER}}
    }
    .padding(10)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background("#050D08")

    // ═══ the sky ══════════════════════════════════════════════════════
// {{SKY}}

// {{PIP}}
}
.font(.system(size: 11, design: .monospaced))
.frame(maxWidth: .infinity, alignment: .topLeading)
.background("#020703")
