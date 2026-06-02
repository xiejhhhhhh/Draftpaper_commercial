#!/usr/bin/env bash
# Shared implementation for host-specific static skill installers.

PF_REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PF_SKILL_NAME="${PF_SKILL_NAME:-paper-fetch-skill}"
PF_MCP_NAME="${PF_MCP_NAME:-paper-fetch}"
PF_SCOPE="user"
PF_UNINSTALL=0
PF_REGISTER_MCP=0
PF_MCP_ENV_FILE=""
PF_MCP_SCOPE=""

pf_skill_log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
pf_skill_warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
pf_skill_die() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

pf_skill_abspath() {
    local path="$1"
    case "$path" in
        "~") printf '%s\n' "$HOME" ;;
        "~/"*) printf '%s\n' "$HOME/${path#~/}" ;;
        /*) printf '%s\n' "$path" ;;
        *) printf '%s\n' "$PF_REPO_DIR/$path" ;;
    esac
}

pf_skill_user_base() {
    case "$PF_HOST" in
        claude) printf '%s\n' "$HOME/.claude" ;;
        codex) printf '%s\n' "${CODEX_HOME:-$HOME/.codex}" ;;
        *) pf_skill_die "Unsupported skill host: $PF_HOST" ;;
    esac
}

pf_skill_compute_dir() {
    if [ "$PF_SCOPE" = "user" ]; then
        printf '%s/skills/%s\n' "$(pf_skill_user_base)" "$PF_SKILL_NAME"
    else
        printf '%s/.%s/skills/%s\n' "$PF_REPO_DIR" "$PF_HOST" "$PF_SKILL_NAME"
    fi
}

pf_skill_parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --project)
                PF_SCOPE="project"
                ;;
            --user)
                PF_SCOPE="user"
                ;;
            --register-mcp)
                PF_REGISTER_MCP=1
                ;;
            --env-file)
                shift
                [ "$#" -gt 0 ] || pf_skill_die "--env-file requires a path"
                PF_MCP_ENV_FILE="$1"
                ;;
            --mcp-name)
                shift
                [ "$#" -gt 0 ] || pf_skill_die "--mcp-name requires a value"
                PF_MCP_NAME="$1"
                ;;
            --mcp-scope)
                [ "${PF_SUPPORTS_MCP_SCOPE:-0}" = "1" ] || pf_skill_die "--mcp-scope is only supported by the Claude installer"
                shift
                [ "$#" -gt 0 ] || pf_skill_die "--mcp-scope requires one of: local, user, project"
                PF_MCP_SCOPE="$1"
                ;;
            --uninstall)
                PF_UNINSTALL=1
                ;;
            -h|--help)
                sed -n '2,9p' "$0"
                exit 0
                ;;
            *)
                echo "Unknown option: $1" >&2
                exit 2
                ;;
        esac
        shift
    done
}

pf_skill_validate_args() {
    PF_SKILL_DIR="$(pf_skill_compute_dir)"
    PF_SOURCE_SKILL_DIR="$PF_REPO_DIR/skills/$PF_SKILL_NAME"

    if [ "${PF_SUPPORTS_MCP_SCOPE:-0}" = "1" ]; then
        if [ -z "$PF_MCP_SCOPE" ]; then
            if [ "$PF_SCOPE" = "project" ]; then
                PF_MCP_SCOPE="project"
            else
                PF_MCP_SCOPE="user"
            fi
        fi
        case "$PF_MCP_SCOPE" in
            local|user|project) ;;
            *) pf_skill_die "Unsupported --mcp-scope '$PF_MCP_SCOPE' (expected: local, user, project)" ;;
        esac
    fi

    if [ -n "$PF_MCP_ENV_FILE" ]; then
        PF_MCP_ENV_FILE="$(pf_skill_abspath "$PF_MCP_ENV_FILE")"
    fi
}

pf_skill_install_package() {
    command -v python3 >/dev/null 2>&1 || pf_skill_die "python3 not found on PATH"
    [ -f "$PF_SOURCE_SKILL_DIR/SKILL.md" ] || pf_skill_die "Missing static skill source at $PF_SOURCE_SKILL_DIR/SKILL.md"

    pf_skill_log "Installing package into the current python3 environment"
    cd "$PF_REPO_DIR"
    if ! python3 -m pip install --quiet .; then
        pf_skill_die "python3 -m pip install . failed. Activate a writable virtual environment or run scripts/dev-bootstrap.sh first."
    fi
}

pf_skill_write_codex_agent_manifest() {
    mkdir -p "$PF_SKILL_DIR/agents"
    cat > "$PF_SKILL_DIR/agents/openai.yaml" <<'EOF'
interface:
  display_name: "Paper Fetch Skill"
  short_description: "Fetch AI-friendly paper text by DOI, URL, or title"
  default_prompt: "Use $paper-fetch-skill whenever you need the text, readability, or full-text availability of a specific paper or a citation list of identifiable papers."
EOF
}

pf_skill_copy_static_skill() {
    pf_skill_log "Copying static skill to $PF_SKILL_DIR"
    mkdir -p "$PF_SKILL_DIR"
    rm -f "$PF_SKILL_DIR/SKILL.md"
    rm -rf "$PF_SKILL_DIR/references"
    cp "$PF_SOURCE_SKILL_DIR/SKILL.md" "$PF_SKILL_DIR/SKILL.md"
    if [ -d "$PF_SOURCE_SKILL_DIR/references" ]; then
        cp -R "$PF_SOURCE_SKILL_DIR/references" "$PF_SKILL_DIR/references"
    fi
    if [ "$PF_HOST" = "codex" ]; then
        pf_skill_write_codex_agent_manifest
    fi
}

pf_skill_unregister_if_requested() {
    rm -rf "$PF_SKILL_DIR"
    pf_skill_log "Removed $PF_SKILL_DIR"
    if [ "$PF_REGISTER_MCP" = "1" ]; then
        pf_host_unregister_mcp
    fi
}

pf_skill_print_next_steps() {
    echo
    echo "Next steps:"
    echo "  1. Restart $PF_RESTART_NAME so it rescans installed skills."
    if [ "$PF_REGISTER_MCP" = "1" ]; then
        pf_host_print_registered_note
    else
        echo "  2. If you want MCP tools too, rerun with --register-mcp or register a stdio server that runs 'paper-fetch-mcp'."
    fi
    echo "  3. If you fetch Elsevier papers, request a key at https://dev.elsevier.com/ and set ELSEVIER_API_KEY in ~/.config/paper-fetch/.env or pass --env-file when registering MCP."
    echo "  4. Re-run this installer after upgrading the repo to install the new package build."
}

pf_skill_main() {
    pf_skill_parse_args "$@"
    pf_skill_validate_args

    if [ "$PF_UNINSTALL" = "1" ]; then
        pf_skill_unregister_if_requested
        exit 0
    fi

    pf_skill_install_package
    pf_skill_copy_static_skill

    if [ "$PF_REGISTER_MCP" = "1" ]; then
        pf_host_register_mcp
    fi

    pf_skill_print_next_steps
}
