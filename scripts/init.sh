#!/usr/bin/env bash
# Install video-use and style-explainer for the current folder.
# Works on bash 3.2 (macOS /bin/bash) and newer.
#
#   curl -fsSL https://raw.githubusercontent.com/dan-tech-academy/video-use/main/scripts/init.sh | bash
#   ~/Developer/video-use/scripts/init.sh
#   video-use-init
set -euo pipefail

REPO_URL="https://github.com/dan-tech-academy/video-use"
REPO_DIR="${VIDEO_USE_HOME:-$HOME/Developer/video-use}"
TARGET="$(pwd)"
DO_REMOVE=0
DO_GLOBAL=0
DO_INSTALL_CMD=0
DO_HELP=0
SKILL_DIRS=()

usage() {
  cat <<'EOF'
Usage: init.sh [--global] [--remove] [--install-cmd] [--help]

Install video-use and style-explainer into the current folder
(.claude/skills and .agents/skills).

  --global       Link into ~/.claude/skills and ~/.agents/skills instead.
                 Also link ${CODEX_HOME:-~/.codex}/skills when that directory
                 already exists.
  --remove       Remove those links. With --global, remove the home links.
  --install-cmd  Symlink this script to ~/.local/bin/video-use-init.
  --help         Show this help.

Environment:
  VIDEO_USE_HOME       Clone location (default: ~/Developer/video-use).
  VIDEO_USE_SKIP_SYNC  Set to 1 to skip clone, pull, and dependency install.

The script does not read a key from you and does not print secrets.
If ELEVENLABS_API_KEY is missing, it prints the command that appends it to
the repo .env. An existing .env is never overwritten.
EOF
}

warn() {
  printf '! %s\n' "$1" >&2
}

expand_tilde() {
  local tilde_home tilde_prefix
  # A quoted VIDEO_USE_HOME can still contain a literal tilde.
  tilde_home=$(printf '\176')
  tilde_prefix="${tilde_home}/"
  case "$REPO_DIR" in
    "$tilde_home") REPO_DIR="$HOME" ;;
    "$tilde_prefix"*) REPO_DIR="$HOME/${REPO_DIR#"$tilde_prefix"}" ;;
  esac
  case "$REPO_DIR" in
    /*) ;;
    *) REPO_DIR="$TARGET/$REPO_DIR" ;;
  esac
  REPO_DIR="${REPO_DIR%/}"
}

collect_skill_dirs() {
  local codex_skills
  SKILL_DIRS=()
  if [[ "$DO_GLOBAL" -eq 1 ]]; then
    SKILL_DIRS+=("$HOME/.claude/skills")
    SKILL_DIRS+=("$HOME/.agents/skills")
    codex_skills="${CODEX_HOME:-$HOME/.codex}/skills"
    if [[ -d "$codex_skills" ]]; then
      SKILL_DIRS+=("$codex_skills")
    fi
  else
    SKILL_DIRS+=("$TARGET/.claude/skills")
    SKILL_DIRS+=("$TARGET/.agents/skills")
  fi
}

unlink_one() {
  local dest="$1"
  if [[ -L "$dest" ]]; then
    rm -f "$dest"
    return 0
  fi
  if [[ -e "$dest" ]]; then
    warn "$dest exists and is not a symlink; leaving it in place"
  fi
}

remove_links() {
  local dir parent base
  collect_skill_dirs
  for dir in "${SKILL_DIRS[@]}"; do
    unlink_one "$dir/video-use"
    unlink_one "$dir/style-explainer"
    rmdir "$dir" 2>/dev/null || true
    parent="$(dirname "$dir")"
    base="$(basename "$parent")"
    if [[ "$base" == ".claude" || "$base" == ".agents" ]]; then
      rmdir "$parent" 2>/dev/null || true
    fi
  done
}

ensure_repo() {
  if [[ -d "$REPO_DIR/.git" ]]; then
    if [[ "${VIDEO_USE_SKIP_SYNC:-}" == "1" ]]; then
      return 0
    fi
    if ! command -v git >/dev/null 2>&1; then
      warn "git is missing; using the current copy"
      return 0
    fi
    git -C "$REPO_DIR" pull --ff-only || warn "git pull failed, using the current copy"
    return 0
  fi
  if [[ -e "$REPO_DIR" ]]; then
    warn "$REPO_DIR exists and is not a git checkout"
    exit 1
  fi
  if [[ "${VIDEO_USE_SKIP_SYNC:-}" == "1" ]]; then
    warn "VIDEO_USE_HOME is not a git checkout: $REPO_DIR"
    exit 1
  fi
  if ! command -v git >/dev/null 2>&1; then
    warn "git is missing"
    exit 1
  fi
  mkdir -p "$(dirname "$REPO_DIR")"
  git clone "$REPO_URL" "$REPO_DIR"
}

require_checkout() {
  if [[ -d "$REPO_DIR" ]]; then
    REPO_DIR="$(cd "$REPO_DIR" && pwd)"
  fi
  if [[ ! -f "$REPO_DIR/SKILL.md" || ! -f "$REPO_DIR/skills/style-explainer/SKILL.md" ]]; then
    warn "$REPO_DIR does not look like video-use (missing SKILL.md)"
    exit 1
  fi
}

python_required() {
  local spec major minor
  major=3
  minor=10
  if [[ -f "$REPO_DIR/pyproject.toml" ]]; then
    spec="$(sed -n 's/^requires-python *= *"\([^"]*\)".*/\1/p' "$REPO_DIR/pyproject.toml" | head -n 1)"
    if [[ "$spec" =~ ^\>=([0-9]+)\.([0-9]+) ]]; then
      major="${BASH_REMATCH[1]}"
      minor="${BASH_REMATCH[2]}"
    fi
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    warn "python3 is missing (need >=${major}.${minor})"
    return 1
  fi
  if ! PY_MAJOR="$major" PY_MINOR="$minor" python3 -c 'import os, sys
need = (int(os.environ["PY_MAJOR"]), int(os.environ["PY_MINOR"]))
raise SystemExit(0 if sys.version_info[:2] >= need else 1)'; then
    warn "python3 is older than ${major}.${minor}"
    return 1
  fi
}

install_deps() {
  if [[ "${VIDEO_USE_SKIP_SYNC:-}" == "1" ]]; then
    return 0
  fi
  if [[ -f "$REPO_DIR/.deps-installed" ]]; then
    return 0
  fi
  if (
    cd "$REPO_DIR"
    if command -v uv >/dev/null 2>&1; then
      uv sync
    elif command -v pip3 >/dev/null 2>&1; then
      pip3 install -e .
    elif command -v pip >/dev/null 2>&1; then
      pip install -e .
    else
      python3 -m pip install -e .
    fi
  ); then
    touch "$REPO_DIR/.deps-installed"
    return 0
  fi
  warn "dependency install failed; skill links will still be created"
  return 1
}

link_one() {
  local dir="$1" name="$2" src="$3" dest
  dest="$dir/$name"
  mkdir -p "$dir"
  if [[ -L "$dest" ]]; then
    ln -sfn "$src" "$dest"
    return 0
  fi
  if [[ -e "$dest" ]]; then
    warn "$dest exists and is not a symlink; leaving it in place"
    return 0
  fi
  ln -sfn "$src" "$dest"
}

link_skills() {
  local dir
  collect_skill_dirs
  for dir in "${SKILL_DIRS[@]}"; do
    link_one "$dir" "video-use" "$REPO_DIR"
    link_one "$dir" "style-explainer" "$REPO_DIR/skills/style-explainer"
  done
}

path_has() {
  case ":$PATH:" in
    *":$1:"*) return 0 ;;
    *) return 1 ;;
  esac
}

install_command() {
  local bin_dir dest src shell_name rc
  bin_dir="$HOME/.local/bin"
  dest="$bin_dir/video-use-init"
  src="$REPO_DIR/scripts/init.sh"
  if [[ ! -f "$src" ]]; then
    warn "cannot find $src"
    return 1
  fi
  mkdir -p "$bin_dir"
  if [[ -L "$dest" || ! -e "$dest" ]]; then
    ln -sfn "$src" "$dest"
    printf 'Command: %s\n' "$dest"
  else
    warn "$dest exists and is not a symlink; leaving it in place"
  fi
  if path_has "$bin_dir"; then
    return 0
  fi
  shell_name="$(basename "${SHELL:-bash}")"
  case "$shell_name" in
    zsh) rc="$HOME/.zshrc" ;;
    bash) rc="$HOME/.bashrc" ;;
    *) rc="$HOME/.profile" ;;
  esac
  warn "$bin_dir is not on PATH"
  printf '  For %s, add this line to %s:\n' "$shell_name" "$rc"
  # Dollars are expanded by the user's login shell, not by this script.
  # shellcheck disable=SC2016
  printf '    export PATH="%s/.local/bin:%s"\n' '$HOME' '$PATH'
}

warn_ffmpeg() {
  local reply
  if command -v ffmpeg >/dev/null 2>&1; then
    return 0
  fi
  warn "ffmpeg is missing"
  case "$(uname -s)" in
    Darwin)
      if command -v brew >/dev/null 2>&1; then
        if [[ -t 1 && -r /dev/tty ]]; then
          printf 'Install ffmpeg with Homebrew now? [y/N] '
          reply=""
          IFS= read -r reply </dev/tty || reply=""
          case "$reply" in
            y|Y|yes|YES)
              brew install ffmpeg || warn "brew install ffmpeg failed"
              ;;
            *)
              printf '  brew install ffmpeg\n'
              ;;
          esac
        else
          printf '  brew install ffmpeg\n'
        fi
      else
        printf '  Install Homebrew, then: brew install ffmpeg\n'
      fi
      ;;
    Linux)
      if command -v apt-get >/dev/null 2>&1; then
        printf '  sudo apt-get update && sudo apt-get install -y ffmpeg\n'
      elif command -v dnf >/dev/null 2>&1; then
        printf '  sudo dnf install -y ffmpeg\n'
      elif command -v yum >/dev/null 2>&1; then
        printf '  sudo yum install -y ffmpeg\n'
      elif command -v pacman >/dev/null 2>&1; then
        printf '  sudo pacman -S ffmpeg\n'
      else
        printf '  Install ffmpeg with your package manager\n'
      fi
      ;;
    *)
      printf '  Install ffmpeg and make sure it is on PATH\n'
      ;;
  esac
}

key_is_set() {
  if [[ -n "${ELEVENLABS_API_KEY:-}" ]]; then
    return 0
  fi
  if [[ -f "$REPO_DIR/.env" && -r "$REPO_DIR/.env" ]] && grep -qE '^ELEVENLABS_API_KEY=.+' "$REPO_DIR/.env"; then
    return 0
  fi
  return 1
}

print_key_hint() {
  if key_is_set; then
    return 0
  fi
  printf 'ElevenLabs API key is not set. Transcription needs it.\n'
  printf 'Add it with this command (an existing .env is appended to, not replaced):\n'
  printf '  printf '\''ELEVENLABS_API_KEY=%%s\\n'\'' '\''YOUR_KEY'\'' >> %q && chmod 600 %q\n' \
    "$REPO_DIR/.env" "$REPO_DIR/.env"
  printf 'Get a key at https://elevenlabs.io/app/settings/api-keys\n'
}

print_gitignore_hint() {
  if [[ "$DO_GLOBAL" -eq 1 ]]; then
    return 0
  fi
  if ! command -v git >/dev/null 2>&1; then
    return 0
  fi
  if ! git -C "$TARGET" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return 0
  fi
  cat <<'EOF'
This folder is a git repo. The script did not change .gitignore.
Add these lines if the skill links should stay untracked:

  .claude/skills/video-use
  .claude/skills/style-explainer
  .agents/skills/video-use
  .agents/skills/style-explainer
EOF
}

print_installed() {
  local dir
  printf 'Installed video-use and style-explainer into:\n'
  for dir in "${SKILL_DIRS[@]}"; do
    printf '  %s\n' "$dir"
  done
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remove) DO_REMOVE=1 ;;
    --global) DO_GLOBAL=1 ;;
    --install-cmd) DO_INSTALL_CMD=1 ;;
    --help|-h) DO_HELP=1 ;;
    *)
      warn "unknown option: $1"
      printf 'Run with --help for usage.\n' >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "$DO_HELP" -eq 1 ]]; then
  usage
  exit 0
fi

expand_tilde

if [[ "$DO_REMOVE" -eq 1 ]]; then
  remove_links
  if [[ "$DO_GLOBAL" -eq 1 ]]; then
    printf 'Removed video-use skills from %s\n' "$HOME"
  else
    printf 'Removed video-use skills from %s\n' "$TARGET"
  fi
  if [[ "$DO_INSTALL_CMD" -eq 1 ]]; then
    ensure_repo
    require_checkout
    install_command
  fi
  exit 0
fi

if ! command -v git >/dev/null 2>&1; then
  if [[ "${VIDEO_USE_SKIP_SYNC:-}" == "1" && -d "$REPO_DIR/.git" ]]; then
    warn "git is missing; using the current copy"
  else
    warn "git is missing"
    exit 1
  fi
fi

ensure_repo
require_checkout

if python_required; then
  install_deps || true
fi

link_skills

if [[ "$DO_INSTALL_CMD" -eq 1 ]]; then
  install_command
fi

warn_ffmpeg
print_key_hint
print_gitignore_hint
print_installed
