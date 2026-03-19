#!/usr/bin/env bash
set -euo pipefail
set -E

INIT_DIR=${INIT_DIR:-/etc/cont-init.d}

log() {
    echo "**** (entrypoint) $*"
}

on_error() {
    local line_no=$1
    local cmd=$2
    local exit_code=$3
    local source_file=${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}
    log "Initialization failed in ${source_file}:${line_no}: ${cmd} (exit ${exit_code})"
    log "Sleeping 5 seconds before exiting to avoid rapid restarts"
    sleep 5
    exit 1
}
trap 'on_error ${LINENO} "${BASH_COMMAND}" $?' ERR

run_init_scripts() {
    if [[ ! -d "${INIT_DIR}" ]]; then
        log "Init directory ${INIT_DIR} not found; skipping init scripts"
        return
    fi

    shopt -s nullglob
    for script in "${INIT_DIR}"/*; do
        [[ -f "${script}" ]] || continue
        log "Sourcing ${script}"
        source "${script}"
    done
    shopt -u nullglob
}

sqlite_maintenance() {
    local db_path="${COMPRESSO_DB_PATH:-/config/.compresso/config/compresso.db}"
    local maintenance_mode="${COMPRESSO_SQLITE_MAINTENANCE:-basic}"

    if [[ "${maintenance_mode}" == "off" ]]; then
        return
    fi

    if [[ ! -f "${db_path}" ]]; then
        log "SQLite maintenance skipped (db not found at ${db_path})"
        return
    fi

    if ! command -v sqlite3 >/dev/null 2>&1; then
        log "SQLite maintenance skipped (sqlite3 not installed)"
        return
    fi

    log "SQLite maintenance (${maintenance_mode}) on ${db_path}"
    case "${maintenance_mode}" in
    basic)
        sqlite3 "${db_path}" "PRAGMA wal_checkpoint(TRUNCATE); PRAGMA optimize;"
        ;;
    full)
        sqlite3 "${db_path}" "PRAGMA wal_checkpoint(TRUNCATE); PRAGMA optimize; VACUUM;"
        ;;
    *)
        log "Unknown COMPRESSO_SQLITE_MAINTENANCE mode '${maintenance_mode}', skipping"
        ;;
    esac
}

ensure_runtime_paths() {
    mkdir -p \
        /config \
        /config/.compresso \
        /tmp/compresso

    if [[ "${EUID}" -eq 0 ]]; then
        chown -R "${PUID:-1000}:${PGID:-1000}" /config /tmp/compresso || true
    fi
}

activate_venv() {
    local venv="${VIRTUAL_ENV:-/opt/venv}"

    if [[ ! -d "${venv}" ]]; then
        log "Creating virtualenv at ${venv}"
        python3 -m venv "${venv}" --clear
    fi

    if [[ -f "${venv}/bin/activate" ]]; then
        export VIRTUAL_ENV="${venv}"
        log "Activating virtualenv at ${VIRTUAL_ENV}"
        source "${VIRTUAL_ENV}/bin/activate"
    else
        log "No virtualenv found at ${venv}"
    fi
}

update_source_symlink() {
    if [[ ! -e /app/compresso/service.py ]]; then
        return
    fi

    if [[ "${EUID}" -ne 0 ]]; then
        log "Not running as root, skipping source install symlink update"
        return
    fi

    log "Update container to running Compresso from source"
    local venv="${VIRTUAL_ENV:-/opt/venv}"
    local python_version=$("${venv}/bin/python3" --version 2>&1 | grep -oP 'Python \K\d+\.\d+')
    local target="${venv}/lib/python${python_version:?}/site-packages/compresso"
    if [[ -e "${target}" && ! -L "${target}" ]]; then
        log "Move container compresso install"
        mv "${target}" "${target}-installed"
    fi
    ln -sf /app/compresso "${target}"
    log "Source symlink set: ${target} -> $(readlink -f "${target}")"
}

install_custom_venv_requirements() {
    local venv="${VIRTUAL_ENV:-/opt/venv}"

    if [[ -e /app/requirements.txt ]]; then
        log "Installing /app/requirements.txt into ${venv}"
        "${venv}/bin/python3" -m pip install -r /app/requirements.txt
    fi

    if [[ -e /app/requirements-dev.txt ]]; then
        log "Installing /app/requirements-dev.txt into ${venv}"
        "${venv}/bin/python3" -m pip install -r /app/requirements-dev.txt
    fi
}

main() {
    ensure_runtime_paths
    activate_venv
    install_custom_venv_requirements
    run_init_scripts
    sqlite_maintenance

    update_source_symlink

    if [[ "$1" == "/usr/bin/compresso" || "$1" == "compresso" ]]; then
        compresso_params=()
        if [[ "${DEBUGGING:-}" == 'true' ]]; then
            compresso_params+=(--dev)
        fi
        case "${USE_CUSTOM_SUPPORT_API:-}" in
        test)
            compresso_params+=(--dev-api=https://support-api.test.streamingtech.co.nz)
            ;;
        dev)
            compresso_params+=(--dev-api=http://api.compresso.localhost)
            ;;
        esac
        compresso_cmd=("$1" "${compresso_params[@]}" "${@:2}")
        if [[ -n "${COMPRESSO_RUN_COMMAND:-}" ]]; then
            compresso_cmd_str=$(printf '%q ' "${compresso_cmd[@]}")
            compresso_cmd_str=${compresso_cmd_str% }
            run_cmd="${COMPRESSO_RUN_COMMAND//\{cmd\}/${compresso_cmd_str}}"
            log "Using custom run command: ${run_cmd}"
            if [[ "${EUID}" -eq 0 ]]; then
                if command -v gosu >/dev/null 2>&1; then
                    if [[ -n "${PUID:-}" && -n "${PGID:-}" ]]; then
                        exec gosu "${PUID}:${PGID}" /bin/bash -lc "${run_cmd}"
                    fi
                    exec gosu "${RUN_USER:-ubuntu}" /bin/bash -lc "${run_cmd}"
                fi
            fi
            exec /bin/bash -lc "${run_cmd}"
        fi
        set -- "${compresso_cmd[@]}"
    fi

    log "Starting: $*"
    exec "$@"
}

main "$@"
