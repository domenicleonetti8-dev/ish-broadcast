#!/bin/sh
set -eu

broadcast_cc=${CC:-cc}
broadcast_python=${PYTHON:-python3}
broadcast_tmp=$(mktemp -d)
trap 'rm -rf "$broadcast_tmp"' EXIT HUP INT TERM

broadcast_flags="-std=c11 -Wall -Wextra -Werror -pedantic -I."

run_test() {
    output=$1
    shift
    "$broadcast_cc" $broadcast_flags "$@" -o "$broadcast_tmp/$output"
    "$broadcast_tmp/$output"
}

run_test string_registry \
    app/BroadcastFingerTable.c \
    tests/broadcast_finger_table_test.c
run_test fanout \
    app/BroadcastFanout.c \
    tests/broadcast_fanout_test.c
run_test pcm \
    app/BroadcastPCM.c \
    tests/broadcast_pcm_test.c \
    -lm
run_test health \
    app/BroadcastHealth.c \
    tests/broadcast_health_test.c
run_test probe_contract \
    app/BroadcastProbeContract.c \
    tests/broadcast_probe_contract_test.c
run_test string_stress \
    app/BroadcastFingerTable.c \
    app/BroadcastFanout.c \
    tests/broadcast_stress_test.c
"$broadcast_python" tests/validate_broadcast_project.py

if "$broadcast_cc" -fsanitize=address,undefined -x c -o \
    "$broadcast_tmp/sanitizer_probe" - >/dev/null 2>&1 <<'PROBE'
int main(void) { return 0; }
PROBE
then
    broadcast_flags="$broadcast_flags -fsanitize=address,undefined -fno-omit-frame-pointer"
    ASAN_OPTIONS=detect_leaks=0
    export ASAN_OPTIONS
    run_test string_registry_sanitized \
        app/BroadcastFingerTable.c \
        tests/broadcast_finger_table_test.c
    run_test fanout_sanitized \
        app/BroadcastFanout.c \
        tests/broadcast_fanout_test.c
    run_test pcm_sanitized \
        app/BroadcastPCM.c \
        tests/broadcast_pcm_test.c \
        -lm
    run_test health_sanitized \
        app/BroadcastHealth.c \
        tests/broadcast_health_test.c
    run_test probe_contract_sanitized \
        app/BroadcastProbeContract.c \
        tests/broadcast_probe_contract_test.c
    run_test string_stress_sanitized \
        app/BroadcastFingerTable.c \
        app/BroadcastFanout.c \
        tests/broadcast_stress_test.c
fi
