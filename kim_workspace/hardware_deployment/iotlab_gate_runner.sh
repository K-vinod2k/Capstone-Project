#!/usr/bin/env bash
# iotlab_gate_runner.sh
#
# Interactive runner for the four `rt/arm_sdk` hardware gates on the G1 EDU.
# Stops at every gate and waits for operator confirmation that:
#   1. the gate has run without anomaly, AND
#   2. you want to proceed to the next gate.
#
# See: arm_sdk_first_run_guide.md for the full procedure, pass/fail criteria,
# and abort conditions. This script is only an ordering/pause convenience; it
# does not encode the safety protocol.
#
# Usage (on the iotlab dev computer, direct Ethernet to the G1):
#     cd /path/to/Capstone
#     bash kim_workspace/hardware_deployment/iotlab_gate_runner.sh
#
# Options via env:
#     IFACE=enp0s31f6         # DDS interface (default)
#     PKL=kim_workspace/movements/wave_kinematics.pkl   # Gate D PKL
#     SPEED=0.5               # Gate D user speed
#     PYTHON=python           # python executable
#     JOG_AMP=0.2             # Gate B amplitude (rad)
#     ENGAGE_WEIGHT=0.1       # Gate C max weight (0..1)
#
# Prerequisites validated by the OPERATOR before starting:
#     [ ] Gantry/harness weight-bearing
#     [ ] Controller/pendant in hand, L1+L2 ready
#     [ ] Robot in BalanceStand (not damping)
#     [ ] Clear ~1.5 m radius around the robot
#     [ ] Laptop dry-runs (--dry-run-map, --dry-run-limits) already reviewed

set -u
set -o pipefail

IFACE="${IFACE:-enp0s31f6}"
PKL="${PKL:-kim_workspace/movements/wave_kinematics.pkl}"
SPEED="${SPEED:-0.5}"
PYTHON="${PYTHON:-python}"
JOG_AMP="${JOG_AMP:-0.2}"
ENGAGE_WEIGHT="${ENGAGE_WEIGHT:-0.1}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

GUIDE="kim_workspace/hardware_deployment/arm_sdk_first_run_guide.md"

banner() {
    echo ""
    echo "================================================================"
    echo " $1"
    echo "================================================================"
}

confirm() {
    # $1 = prompt, returns 0 on YES, non-zero on anything else
    echo ""
    echo ">>> $1"
    echo -n ">>> Type 'YES' to continue, anything else to abort: "
    read -r reply
    if [ "$reply" != "YES" ]; then
        echo "[ABORT] Operator did not confirm. Exiting."
        exit 2
    fi
}

check_env() {
    banner "Pre-flight environment check"
    echo "Repo root   : $ROOT"
    echo "Interface   : $IFACE"
    echo "PKL (Gate D): $PKL"
    echo "Speed (D)   : $SPEED"
    echo "Jog amp (B) : $JOG_AMP rad"
    echo "Engage wt   : $ENGAGE_WEIGHT"
    echo "Python      : $($PYTHON --version 2>&1)"
    if [ ! -f "$PKL" ]; then
        echo "[ERROR] PKL not found: $PKL"
        exit 1
    fi
    if [ ! -f "$GUIDE" ]; then
        echo "[WARN] Guide not found: $GUIDE (continuing anyway)"
    fi
}

gate_A() {
    banner "Gate A — DDS readback (read-only, no actuation)"
    echo "Expect: encoder stream within 2s, Joint 13 = L_SHOULDER_PITCH, mode_machine non-zero."
    echo "Run in a separate shell; watch the encoder output for ~5 seconds, then Ctrl-C."
    confirm "Launch g1_encoder_monitor on iface $IFACE?"
    $PYTHON kim_workspace/hardware_deployment/g1_encoder_monitor.py --iface "$IFACE" || true
    confirm "Gate A PASSED (encoder stream looked healthy)?"
}

gate_B() {
    banner "Gate B — single-joint physical identity jog"
    echo "Three sub-steps (B.1 shoulder_pitch L, B.2 shoulder_pitch R, B.3 L_WRIST_ROLL≡L_ELBOW_ROLL)."
    echo "After each sub-step you MUST visually confirm the correct joint moved."

    for idx in 15 22 19; do
        case $idx in
            15) expect="LEFT shoulder pitch  (arm rotates forward/back)" ;;
            22) expect="RIGHT shoulder pitch (arm rotates forward/back)" ;;
            19) expect="L motor BETWEEN elbow and hand (labelled L_WRIST_ROLL, is physically L_ELBOW_ROLL on 23-DOF)" ;;
        esac
        echo ""
        echo "--- Gate B sub-step --jog-test $idx (amp $JOG_AMP rad) ---"
        echo "Expect to see: $expect"
        confirm "Ready to jog arm-SDK idx $idx?"
        $PYTHON vinod_workspace/g1_arm_replay_loco.py \
            --jog-test "$idx" --jog-amp "$JOG_AMP" --iface "$IFACE"
        rc=$?
        if [ $rc -ne 0 ]; then
            echo "[ERROR] Jog-test idx=$idx exited rc=$rc"
            echo "        If this was a velocity-abort, the loco controller is fighting the command."
            echo "        Re-read arm_sdk_first_run_guide.md section 'Gate B' → 'Fail → STOP before Gate C'."
            exit $rc
        fi
        confirm "Did the EXPECTED joint (and only that joint) move?"
    done

    echo ""
    echo "All three Gate B sub-steps PASSED."
}

gate_C() {
    banner "Gate C — engage-only protocol test (no arm motion)"
    echo "Weight ramps 0 → $ENGAGE_WEIGHT → 0. Arms echo current encoder q each tick."
    echo "Expect: robot stays balanced, arms show no perceptible motion."
    confirm "Ready to run engage-only with max weight $ENGAGE_WEIGHT?"
    $PYTHON vinod_workspace/g1_arm_replay_loco.py \
        --engage-only --engage-weight "$ENGAGE_WEIGHT" --iface "$IFACE"
    rc=$?
    if [ $rc -ne 0 ]; then
        echo "[ERROR] Engage-only exited rc=$rc"
        echo "        Gate C failed — do NOT proceed to Gate D."
        exit $rc
    fi
    confirm "Gate C PASSED (no arm jerk, no velocity abort, robot balanced)?"
}

gate_D() {
    banner "Gate D — full PKL playback: $(basename "$PKL")"
    echo "Speed = $SPEED (T2 loco-aware limits will further slow if needed)."
    echo "PKL   = $PKL"
    echo ""
    echo "Pre-flight (auto): dry-run-map and dry-run-limits one more time."
    $PYTHON vinod_workspace/g1_arm_replay_loco.py --pkl "$PKL" --dry-run-map || exit 1
    $PYTHON vinod_workspace/g1_arm_replay_loco.py --pkl "$PKL" --dry-run-limits --speed "$SPEED" || exit 1
    confirm "Dry-runs look clean — proceed to LIVE playback of $(basename "$PKL")?"

    $PYTHON vinod_workspace/g1_arm_replay_loco.py \
        --pkl "$PKL" --iface "$IFACE" --speed "$SPEED"
    rc=$?
    if [ $rc -ne 0 ]; then
        echo "[ERROR] Gate D playback exited rc=$rc"
        exit $rc
    fi
    confirm "Gate D PASSED (robot balanced, arms followed, ease-out smooth)?"
}

main() {
    check_env
    confirm "All operator prerequisites satisfied (gantry, E-stop, BalanceStand)?"
    gate_A
    gate_B
    gate_C
    gate_D

    banner "ALL FOUR GATES PASSED"
    echo "Post-run checklist lives at the bottom of: $GUIDE"
    echo ""
    echo "Suggested next updates:"
    echo "  - _kpop/exp_log_g1_stabilization_models.md  (C8-VALIDATED → CONFIRMED)"
    echo "  - CLAUDE.md  (remove 'open research question' note)"
    echo "  - session_logs/2026-04-20_session.md  (close open items)"
}

main "$@"
