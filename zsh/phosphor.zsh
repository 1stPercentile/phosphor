# Phosphor for zsh: prompt, output colours, completion menu, and input highlighting.
# Source it from ~/.zshrc (install.sh adds the line):
#   export PHOSPHOR_HOME="$HOME/.phosphor"; . "$PHOSPHOR_HOME/zsh/phosphor.zsh"
# Optional: PHOSPHOR_BANNER=0 turns off the two-line greeting.

: "${PHOSPHOR_HOME:=${${(%):-%x}:A:h:h}}"
: "${PHOSPHOR_CACHE:=$HOME/.cache/phosphor}"

# ─── phosphor: the colour language ─────────────────────────────────────
# Five brightnesses of one green, plus amber. Amber only ever means
# something went wrong — it is the second phosphor, not a decoration.
P_RULE='#0C2A17'   # structure, comments, anything you are meant to skip
P_META='#1F8F4E'   # chrome, operators, metadata
P_LIVE='#41FF8D'   # the working brightness — machine output sits here
P_WARM='#B9FFD6'   # quoted text, keywords
P_HOT='#EAFFF3'    # what YOU typed, and the command you are about to run
P_ALARM='#FFB000'  # errors, failures, sudo, an unknown command

# ─── prompt ────────────────────────────────────────────────────────────
# The mark carries state, so the prompt is a readout rather than a
# decoration: › ready, ✗ the last command failed, ⌥ you are in a repo,
# ● the repo is dirty. Right side holds the clock and the failing exit code.
setopt PROMPT_SUBST

phosphor_git() {
  local b
  b=$(git symbolic-ref --quiet --short HEAD 2>/dev/null) || return
  local dirty=""
  git diff --quiet --ignore-submodules HEAD 2>/dev/null || dirty="%F{$P_ALARM}●%f"
  print -rn -- " %F{$P_RULE}⌥%f %F{$P_META}${b}%f${dirty}"
}

PROMPT='%F{'$P_META'}%1~%f$(phosphor_git) %(?.%F{'$P_LIVE'}.%F{'$P_ALARM'})›%f %F{'$P_HOT'}'
RPROMPT='%(?..%F{'$P_ALARM'}✗ %?%f  )%F{'$P_RULE'}%*%f'

# Input glows hotter than output. The prompt ends mid-colour so what you
# type is P_HOT; preexec drops back to the working brightness the instant
# you hit return, so everything the machine says is visibly cooler.
autoload -Uz add-zsh-hook
phosphor_preexec() {
  print -rn -- $'\033[38;2;65;255;141m'
  print -rn -- $'\033]112\a'          # cursor back to normal while it runs
}
phosphor_precmd() {
  local code=$?
  print -rn -- $'\033[0m'
  # OSC 12 sets the cursor colour. The shader watches that colour and flares
  # the tube amber when it goes warm — so a failed command is felt, not read.
  if (( code )); then
    print -rn -- $'\033]12;#FFB000\a'
  else
    print -rn -- $'\033]112\a'
  fi
}
add-zsh-hook preexec phosphor_preexec
add-zsh-hook precmd  phosphor_precmd

# ─── output, coded by type ─────────────────────────────────────────────
export CLICOLOR=1
# directory, symlink, socket, pipe, block, char, setuid, setgid, sticky…
export LSCOLORS='CxGxFxDxCxDxDxHbHdAcAd'
export LS_COLORS='di=1;38;2;185;255;214:ln=38;2;107;255;176:ex=1;38;2;234;255;243:so=38;2;31;143;78:pi=38;2;31;143;78:bd=38;2;255;176;0:cd=38;2;255;176;0:or=1;38;2;255;176;0:mi=1;38;2;255;176;0:*.md=38;2;155;255;201:*.json=38;2;155;255;201:*.zip=38;2;255;208;138:*.tar=38;2;255;208;138:*.gz=38;2;255;208;138:*.png=38;2;124;255;184:*.jpg=38;2;124;255;184:*.mp4=38;2;124;255;184'

# grep: the match is the hottest thing on screen, the line number is chrome
export GREP_COLORS='mt=1;38;2;234;255;243:ln=38;2;12;42;23:fn=38;2;31;143;78:se=38;2;12;42;23'

# man pages: headings hot, emphasis amber, everything else the working green
export LESS_TERMCAP_md=$'\033[1;38;2;234;255;243m'
export LESS_TERMCAP_me=$'\033[0m'
export LESS_TERMCAP_us=$'\033[4;38;2;255;176;0m'
export LESS_TERMCAP_ue=$'\033[0m'
export LESS_TERMCAP_so=$'\033[38;2;2;7;3;48;2;65;255;141m'
export LESS_TERMCAP_se=$'\033[0m'

# ─── the completion menu ───────────────────────────────────────────────
# Every Tab press was stock zsh until now. Group headings are structure,
# the selected row inverts into the live green, no match is amber.
zmodload -i zsh/complist
autoload -Uz compinit && compinit -C

zstyle ':completion:*' menu select
zstyle ':completion:*' group-name ''
zstyle ':completion:*' verbose yes
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}' 'r:|=*' 'l:|=* r:|=*'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}" "ma=48;2;31;143;78;38;2;2;7;3"
zstyle ':completion:*:descriptions' format "%F{$P_RULE}── %F{$P_META}%d%F{$P_RULE} ──%f"
zstyle ':completion:*:messages'     format "%F{$P_META}%d%f"
zstyle ':completion:*:warnings'     format "%F{$P_ALARM}✗ nothing matches%f"
zstyle ':completion:*:corrections'  format "%F{$P_ALARM}✗ %d%f"

# ─── when there is no such command ─────────────────────────────────────
# An amber ✗ and the thing you typed, unedited.
command_not_found_handler() {
  print -u2 -rP "%F{$P_ALARM}✗%f %F{$P_META}no such command%f %F{$P_RULE}·%f %F{$P_WARM}$1%f"
  return 127
}

# ─── input, coded by type ──────────────────────────────────────────────
# Colours the command line as you type it. A command that does not exist
# turns amber before you press return, which is the whole point.
if [ -r "$HOME/.local/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" ]; then
  ZSH_HIGHLIGHT_HIGHLIGHTERS=(main brackets)
  typeset -gA ZSH_HIGHLIGHT_STYLES
  ZSH_HIGHLIGHT_STYLES[unknown-token]="fg=$P_ALARM,bold"
  ZSH_HIGHLIGHT_STYLES[command]="fg=$P_HOT,bold"
  ZSH_HIGHLIGHT_STYLES[builtin]="fg=$P_HOT,bold"
  ZSH_HIGHLIGHT_STYLES[function]="fg=$P_HOT,bold"
  ZSH_HIGHLIGHT_STYLES[alias]="fg=$P_HOT,bold"
  ZSH_HIGHLIGHT_STYLES[precommand]="fg=$P_ALARM,bold"
  ZSH_HIGHLIGHT_STYLES[reserved-word]="fg=$P_WARM"
  ZSH_HIGHLIGHT_STYLES[path]="fg=$P_LIVE"
  ZSH_HIGHLIGHT_STYLES[path_prefix]="fg=$P_META"
  ZSH_HIGHLIGHT_STYLES[globbing]="fg=$P_WARM"
  ZSH_HIGHLIGHT_STYLES[single-quoted-argument]="fg=$P_WARM"
  ZSH_HIGHLIGHT_STYLES[double-quoted-argument]="fg=$P_WARM"
  ZSH_HIGHLIGHT_STYLES[dollar-quoted-argument]="fg=$P_WARM"
  ZSH_HIGHLIGHT_STYLES[dollar-double-quoted-argument]="fg=$P_LIVE"
  ZSH_HIGHLIGHT_STYLES[back-quoted-argument]="fg=$P_LIVE"
  ZSH_HIGHLIGHT_STYLES[single-hyphen-option]="fg=$P_META"
  ZSH_HIGHLIGHT_STYLES[double-hyphen-option]="fg=$P_META"
  ZSH_HIGHLIGHT_STYLES[redirection]="fg=$P_META"
  ZSH_HIGHLIGHT_STYLES[commandseparator]="fg=$P_META"
  ZSH_HIGHLIGHT_STYLES[comment]="fg=$P_RULE"
  ZSH_HIGHLIGHT_STYLES[bracket-level-1]="fg=$P_LIVE"
  ZSH_HIGHLIGHT_STYLES[bracket-level-2]="fg=$P_WARM"
  ZSH_HIGHLIGHT_STYLES[bracket-level-3]="fg=$P_META"
  ZSH_HIGHLIGHT_STYLES[bracket-error]="fg=$P_ALARM,bold"
  . "$HOME/.local/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
fi

# ─── warm-up ───────────────────────────────────────────────────────────
# Two lines, no delay. Prices are pre-rendered by the minute tick into a
# file, so opening a terminal costs a `cat` and never waits on a network.
phosphor_boot() {
  local dim=$'\033[38;2;12;42;23m' mid=$'\033[38;2;31;143;78m' off=$'\033[0m'
  print -r -- "${dim}▖${off} ${mid}PHOSPHOR${off} ${dim}· $(date '+%H:%M')${off}"
  [ -r "$PHOSPHOR_CACHE/ticker.line" ] \
    && print -r -- "  $(<"$PHOSPHOR_CACHE/ticker.line")"
}
[[ -o interactive && "${PHOSPHOR_BANNER:-1}" != 0 ]] && phosphor_boot

# `market`: the board, live, wherever you are
market() { python3 "$PHOSPHOR_HOME/engine/board.py"; }
# `prices`: one line, refreshed now rather than up to a minute stale
prices() { python3 "$PHOSPHOR_HOME/engine/tick.py" >/dev/null 2>&1; cat "$PHOSPHOR_CACHE/ticker.line"; }
