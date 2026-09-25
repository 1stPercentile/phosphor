#!/usr/bin/env python3
"""Install Phosphor: Ghostty + zsh + cmux sidebar + Claude Code status line (+ Obsidian).

    ./install.sh                     everything except Obsidian
    ./install.sh --vault ~/Notes     ...and theme that Obsidian vault
    ./install.sh --dry-run           say what would change, change nothing
    ./install.sh --uninstall         take it back out

Every file it edits is backed up first (<file>.phosphor-bak-<time>). It adds to your
config; it never replaces a file you wrote. Anything it can't merge safely, it
prints for you to paste instead. Each step is read back, not assumed.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME_DIR = Path(__file__).resolve().parent            # the clone: PHOSPHOR_HOME
H = Path.home()
STAMP = time.strftime("%Y%m%d-%H%M%S")
MARK_START, MARK_END = "# >>> phosphor >>>", "# <<< phosphor <<<"
CMUX_CLI = next((p for p in (shutil.which("cmux"), "/Applications/cmux.app/Contents/Resources/bin/cmux")
                 if p and os.path.exists(p)), None)
GHOSTTY_CLI = next((p for p in (shutil.which("ghostty"),
                                "/Applications/cmux.app/Contents/Resources/bin/ghostty",
                                "/Applications/Ghostty.app/Contents/MacOS/ghostty")
                    if p and os.path.exists(p)), None)
SIDEBAR_ID = "cmux.sidebar.custom.phosphor"

G, D, A, O = "\033[38;2;65;255;141m", "\033[38;2;31;143;78m", "\033[38;2;255;176;0m", "\033[0m"
DRY = False
SKIP_SYSTEM = bool(os.environ.get("PHOSPHOR_SKIP_SYSTEM"))


def ok(msg):
    print(f"  {G}✓{O} {msg}")


def warn(msg):
    print(f"  {A}✗{O} {msg}")


def note(msg):
    print(f"  {D}·{O} {msg}")


def step(msg):
    print(f"\n{D}▖{O} {msg}")


def backup(path):
    if path.exists() and not DRY:
        b = path.with_name(f"{path.name}.phosphor-bak-{STAMP}")
        shutil.copy2(path, b, follow_symlinks=True)
        return b
    return None


def write(path, text):
    if DRY:
        note(f"would write {short(path)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".phosphor-tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path.resolve() if path.is_symlink() else path)


def short(p):
    return str(p).replace(str(H), "~", 1)


def run(cmd, **kw):
    if DRY:
        note("would run: " + " ".join(map(str, cmd)))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def block(text):
    return f"{MARK_START}\n{text.rstrip()}\n{MARK_END}\n"


def add_block(path, text):
    """Append a marked block once; replace it if it is already there."""
    cur = path.read_text(encoding="utf-8") if path.exists() else ""
    if MARK_START in cur:
        head, rest = cur.split(MARK_START, 1)
        tail = rest.split(MARK_END, 1)[1] if MARK_END in rest else ""
        new = head + block(text) + tail.lstrip("\n")
    else:
        new = cur + ("" if cur.endswith("\n") or not cur else "\n") + block(text)
    if new != cur:
        backup(path)
        write(path, new)
    return new


def drop_block(path):
    if not path.exists():
        return False
    cur = path.read_text(encoding="utf-8")
    if MARK_START not in cur:
        return False
    head, rest = cur.split(MARK_START, 1)
    tail = rest.split(MARK_END, 1)[1] if MARK_END in rest else ""
    backup(path)
    write(path, head.rstrip("\n") + "\n" + tail.lstrip("\n"))
    return True


def load_json(path):
    """(data, None) or (None, reason). A file we can't parse is left alone."""
    if not path.exists():
        return {}, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except ValueError as e:
        return None, f"{short(path)} isn't plain JSON ({e.msg}), so it was left alone"


def dump_json(path, data):
    backup(path)
    write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


# ── layers ────────────────────────────────────────────────────────────
def ghostty():
    step("Ghostty: palette, font, CRT shader")
    conf = H / ".config/ghostty/phosphor.conf"
    main = H / ".config/ghostty/config"
    body = (HOME_DIR / "ghostty/config").read_text(encoding="utf-8").replace(
        "custom-shader = shaders/phosphor.glsl",
        f"custom-shader = {HOME_DIR / 'ghostty/shaders/phosphor.glsl'}")
    write(conf, body)
    add_block(main, f"config-file = {conf}")
    if GHOSTTY_CLI and not DRY:
        r = run([GHOSTTY_CLI, "+validate-config", f"--config-file={main}"])
        if r.returncode == 0:
            ok(f"{short(main)} includes {short(conf)} (validated)")
        else:
            drop_block(main)
            warn("Ghostty rejected the config, so the include was taken back out:\n    "
                 + (r.stdout + r.stderr).strip().replace("\n", "\n    "))
    else:
        ok(f"{short(main)} includes {short(conf)}")


def zsh():
    step("zsh: prompt, colours, highlighting")
    rc = H / ".zshrc"
    add_block(rc, f'export PHOSPHOR_HOME="{HOME_DIR}"\n'
                  '[ -r "$PHOSPHOR_HOME/zsh/phosphor.zsh" ] && . "$PHOSPHOR_HOME/zsh/phosphor.zsh"')
    ok(f"{short(rc)} sources zsh/phosphor.zsh")
    hl = H / ".local/share/zsh-syntax-highlighting"
    if hl.exists():
        note("zsh-syntax-highlighting already present")
    elif SKIP_SYSTEM:
        note("skipped cloning zsh-syntax-highlighting")
    else:
        r = run(["git", "clone", "-q", "--depth", "1",
                 "https://github.com/zsh-users/zsh-syntax-highlighting.git", str(hl)])
        (ok if r.returncode == 0 else warn)("zsh-syntax-highlighting "
                                            + ("cloned" if r.returncode == 0 else "could not be cloned; input won't colour"))


def font():
    step("Font: JetBrainsMono Nerd Font")
    have = any(any(Path(d).glob("JetBrainsMonoNerdFont-*.ttf")) for d in (H / "Library/Fonts", "/Library/Fonts"))
    if have:
        note("already installed")
        return
    if SKIP_SYSTEM or DRY:
        note("skipped the font download")
        return
    tmp = Path(subprocess.check_output(["mktemp", "-d"], text=True).strip())
    url = "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.tar.xz"
    r = run(["sh", "-c", f'curl -fsSL -o "{tmp}/f.tar.xz" {url} && tar -xJf "{tmp}/f.tar.xz" -C "{tmp}"'])
    if r.returncode:
        warn("couldn't download it; the terminal falls back to another monospace")
        return
    (H / "Library/Fonts").mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("JetBrainsMonoNerdFont-*.ttf"):
        shutil.copy2(f, H / "Library/Fonts" / f.name)
    shutil.rmtree(tmp, ignore_errors=True)
    ok("installed")


def config():
    step("Config: ~/.config/phosphor")
    cdir = H / ".config/phosphor"
    tokens = cdir / "tokens.txt"
    if tokens.exists():
        note(f"{short(tokens)} kept")
    else:
        write(tokens, (HOME_DIR / "config/tokens.txt").read_text(encoding="utf-8"))
        ok(f"{short(tokens)}: BTC, ETH, SOL. Edit it to watch anything else")


def launch_agent(label, args, interval, log):
    plist = H / f"Library/LaunchAgents/{label}.plist"
    arg_xml = "".join(f"\n    <string>{a}</string>" for a in args)
    write(plist, f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>{arg_xml}
  </array>
  <key>StartInterval</key><integer>{interval}</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
""")
    if SKIP_SYSTEM:
        note(f"skipped loading {label}")
        return
    uid = os.getuid()
    run(["launchctl", "bootout", f"gui/{uid}/{label}"])
    run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)])
    r = run(["launchctl", "print", f"gui/{uid}/{label}"])
    (ok if r.returncode == 0 else warn)(f"{label} " + ("loaded" if r.returncode == 0 else "did NOT load"))


def cmux():
    step("cmux: sidebar, borders, sound, market dock")
    py = sys.executable or "/usr/bin/python3"
    launch_agent("com.phosphor.tick", [py, str(HOME_DIR / "engine/tick.py")], 60,
                 str(H / "Library/Logs/phosphor-tick.log"))
    if not DRY:
        r = run([py, str(HOME_DIR / "engine/tick.py")])
        side = H / ".config/cmux/sidebars/phosphor.swift"
        (ok if side.exists() else warn)(f"{short(side)} " + ("baked" if side.exists() else "was not written: " + r.stderr.strip()[:200]))

    cfg = H / ".config/cmux/cmux.json"
    data, why = load_json(cfg)
    theme = json.loads((HOME_DIR / "cmux/cmux.phosphor.json").read_text(encoding="utf-8")
                       .replace("{{PHOSPHOR_HOME}}", str(HOME_DIR)))
    if data is None:
        warn(why + ". Merge cmux/cmux.phosphor.json into it by hand.")
    else:
        for k, v in theme.items():
            if isinstance(v, dict):
                data.setdefault(k, {})
                if isinstance(data[k], dict):
                    data[k].update(v)
                    continue
            data[k] = v
        dump_json(cfg, data)
        ok(f"{short(cfg)}: Phosphor borders, sidebar tint, pane flash, sound")

    dock = H / ".config/cmux/dock.json"
    data, why = load_json(dock)
    if data is None:
        warn(why)
    else:
        ctl = data.setdefault("controls", [])
        if not any(c.get("id") == "phosphor-market" for c in ctl):
            ctl.append({"id": "phosphor-market", "title": "Market",
                        "command": f"python3 {HOME_DIR / 'engine/board.py'}", "cwd": "~", "height": 320})
            dump_json(dock, data)
        ok(f"{short(dock)}: Market board in the Dock")

    if SKIP_SYSTEM:
        note("skipped pinning the sidebar")
        return
    if CMUX_CLI:
        r = run([CMUX_CLI, "sidebar", "validate", "phosphor"])
        (ok if r.returncode == 0 else warn)("cmux validates the sidebar" if r.returncode == 0
                                            else "cmux rejected the sidebar: " + (r.stdout + r.stderr).strip()[:300])
    # cmux remembers the showing sidebar in its defaults, not in cmux.json, and falls back to
    # the built-in list without a word if that is wrong. So set it, then read it back.
    run(["defaults", "write", "com.cmuxterm.app", "cmuxExtensionSidebar.providerId", "-string", SIDEBAR_ID])
    r = run(["defaults", "read", "com.cmuxterm.app", "cmuxExtensionSidebar.providerId"])
    (ok if r.stdout.strip() == SIDEBAR_ID or DRY else warn)(
        "sidebar pinned to Phosphor" if r.stdout.strip() == SIDEBAR_ID or DRY
        else "sidebar NOT pinned; pick Phosphor from cmux's sidebar menu")
    if CMUX_CLI:
        run([CMUX_CLI, "reload-config"])


def claude():
    step("Claude Code: status line, and Pip watching Claude work")
    path = H / ".claude/settings.json"
    data, why = load_json(path)
    if data is None:
        warn(why + ". See README for the lines to add.")
        return
    changed = False
    line = {"type": "command", "command": f"python3 {HOME_DIR / 'claude-code/statusline.py'}",
            "padding": 0, "refreshInterval": 1}
    if not data.get("statusLine"):
        data["statusLine"] = line
        changed = True
        ok("status line set")
    elif "phosphor" in json.dumps(data["statusLine"]) or "statusline.py" in json.dumps(data["statusLine"]):
        data["statusLine"] = line
        changed = True
        ok("status line updated")
    else:
        note("you already have a status line, so it was kept. To use Phosphor's:\n"
             f"    \"statusLine\": {json.dumps(line)}")
    hooks = data.setdefault("hooks", {})
    for event, word in (("UserPromptSubmit", "work"), ("Stop", "idle"), ("Notification", "needs")):
        cmd = f"python3 {HOME_DIR / 'engine/mode.py'} {word}"
        groups = hooks.setdefault(event, [])
        if not any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
            groups.append({"hooks": [{"type": "command", "command": cmd, "timeout": 10}]})
            changed = True
    ok("hooks: Pip works when Claude works, and waves when it needs you")
    if changed:
        dump_json(path, data)


def obsidian(vault):
    step(f"Obsidian: {short(vault)}")
    ob = vault / ".obsidian"
    if not ob.is_dir():
        warn(f"{short(vault)} has no .obsidian folder; open it in Obsidian once, then re-run")
        return
    if not DRY:
        shutil.copytree(HOME_DIR / "obsidian/themes/Phosphor", ob / "themes/Phosphor", dirs_exist_ok=True)
        (ob / "snippets").mkdir(exist_ok=True)
        shutil.copy2(HOME_DIR / "obsidian/snippets/phosphor-workbench.css", ob / "snippets")
    ok("theme and snippets copied")
    app = ob / "appearance.json"
    data, why = load_json(app)
    if data is None:
        warn(why)
    else:
        data["cssTheme"] = "Phosphor"
        data["theme"] = "obsidian"
        data.setdefault("accentColor", "#41FF8D")
        for k in ("interfaceFontFamily", "textFontFamily", "monospaceFontFamily"):
            if not data.get(k):
                data[k] = "JetBrainsMono Nerd Font"
        snips = data.setdefault("enabledCssSnippets", [])
        for s in ("phosphor-workbench", "phosphor-graph"):
            if s not in snips:
                snips.append(s)
        dump_json(app, data)
        ok("Phosphor selected, snippets on")
    write(H / ".config/phosphor/vault", f"{vault}\n")
    py = sys.executable or "/usr/bin/python3"
    if not DRY:
        r = run([py, str(HOME_DIR / "obsidian/graph_hud.py"), str(vault)])
        hud = ob / "snippets/phosphor-graph.css"
        (ok if hud.exists() else warn)("graph HUD " + ("drawn" if hud.exists()
                                                       else "failed: " + (r.stdout + r.stderr).strip()[:200]))
    launch_agent("com.phosphor.graph", [py, str(HOME_DIR / "obsidian/graph_hud.py"), str(vault)], 300,
                 str(H / "Library/Logs/phosphor-graph.log"))
    note("reload Obsidian (cmd+R) to see it")


def uninstall():
    step("Removing Phosphor")
    uid = os.getuid()
    for label in ("com.phosphor.tick", "com.phosphor.graph"):
        if not SKIP_SYSTEM:
            run(["launchctl", "bootout", f"gui/{uid}/{label}"])
        p = H / f"Library/LaunchAgents/{label}.plist"
        if p.exists() and not DRY:
            p.unlink()
    ok("launch agents removed")
    for p in (H / ".zshrc", H / ".config/ghostty/config"):
        if drop_block(p):
            ok(f"{short(p)}: Phosphor lines removed")
    for p in (H / ".config/ghostty/phosphor.conf", H / ".config/cmux/sidebars/phosphor.swift"):
        if p.exists() and not DRY:
            p.unlink()
    if not SKIP_SYSTEM:
        run(["defaults", "delete", "com.cmuxterm.app", "cmuxExtensionSidebar.providerId"])
    path = H / ".claude/settings.json"
    data, _ = load_json(path)
    if data:
        before = json.dumps(data)
        if HOME_DIR.as_posix() in json.dumps(data.get("statusLine", "")):
            data.pop("statusLine")
        for event, groups in list(data.get("hooks", {}).items()):
            keep = [g for g in groups
                    if not any(str(HOME_DIR / "engine/mode.py") in h.get("command", "")
                               for h in g.get("hooks", []))]
            if keep:
                data["hooks"][event] = keep
            else:
                data["hooks"].pop(event)
        if data.get("hooks") == {}:
            data.pop("hooks")
        if json.dumps(data) != before:
            dump_json(path, data)
            ok("Claude Code status line and hooks removed")
    note("cmux.json, dock.json and Obsidian keep Phosphor's colours; their backups sit beside them "
         "as *.phosphor-bak-*")


def main():
    global DRY
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vault", type=Path, help="an Obsidian vault to theme")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--no-zsh", action="store_true")
    ap.add_argument("--no-claude", action="store_true")
    a = ap.parse_args()
    DRY = a.dry_run
    print(f"{D}▖{O} {G}PHOSPHOR{O} {D}· {short(HOME_DIR)}{' · dry run' if DRY else ''}{O}")
    if a.uninstall:
        uninstall()
        return 0
    config()
    ghostty()
    if not a.no_zsh:
        zsh()
    font()
    cmux()
    if not a.no_claude:
        claude()
    if a.vault:
        obsidian(a.vault.expanduser().resolve())
    print(f"\n{G}done.{O} {D}open a new cmux tab; the sidebar updates within a minute.{O}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
