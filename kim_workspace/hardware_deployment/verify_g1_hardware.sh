#!/usr/bin/env bash
# G1 Hardware Verification Suite
# --------------------------------
# Run this on the Linux machine before deploying to the G1.
# Activate your conda env first, then:
#
#   conda activate <your-env>
#   bash verify_g1_hardware.sh
#
# Each step prints [PASS] or [FAIL] with a fix hint on failure.

ROBOT_IP="192.168.123.164"
INTERFACE="eth0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; EXIT_CODE=1; }
info() { echo "       $1"; }
sep()  { echo ""; echo "--- STEP $1: $2 ---"; }

EXIT_CODE=0

echo "========================================"
echo " G1 Hardware Verification Suite"
echo " Robot IP : $ROBOT_IP"
echo " Interface: $INTERFACE"
echo "========================================"

# ── STEP 1: Ping ─────────────────────────────────────────────────────────────
sep 1 "Network connectivity"
if ping -c 3 -W 2 "$ROBOT_IP" > /dev/null 2>&1; then
    pass "Robot responds to ping at $ROBOT_IP"
else
    fail "Cannot ping $ROBOT_IP"
    info "Fix: check Ethernet cable and robot is powered on"
    echo ""
    echo "ABORT: cannot continue without network connectivity."
    exit 1
fi

# ── STEP 2: Subnet ───────────────────────────────────────────────────────────
sep 2 "Interface subnet (192.168.123.x)"
if ip addr show "$INTERFACE" 2>/dev/null | grep -q "192.168.123"; then
    MYIP=$(ip addr show "$INTERFACE" | awk '/192\.168\.123/{print $2}')
    pass "$INTERFACE has address $MYIP"
else
    fail "$INTERFACE does not have a 192.168.123.x address"
    info "Fix: sudo ip addr add 192.168.123.99/24 dev $INTERFACE"
    info "     sudo ip link set $INTERFACE up"
fi

# ── STEP 3: CYCLONEDDS_HOME ──────────────────────────────────────────────────
sep 3 "CYCLONEDDS_HOME env var"
if [ -n "${CYCLONEDDS_HOME:-}" ]; then
    if [ -d "$CYCLONEDDS_HOME" ]; then
        pass "CYCLONEDDS_HOME=$CYCLONEDDS_HOME"
    else
        fail "CYCLONEDDS_HOME is set but directory does not exist: $CYCLONEDDS_HOME"
        info "Fix: rebuild CycloneDDS and update CYCLONEDDS_HOME in ~/.bashrc"
    fi
else
    fail "CYCLONEDDS_HOME is not set"
    info "Fix: export CYCLONEDDS_HOME=/path/to/cyclonedds/install"
    info "     Add this to ~/.bashrc to make it permanent"
fi

# ── STEP 4: unitree_sdk2py ───────────────────────────────────────────────────
sep 4 "unitree_sdk2py importable"
if python3 -c "import unitree_sdk2py" 2>/dev/null; then
    pass "unitree_sdk2py is importable"
else
    fail "Cannot import unitree_sdk2py"
    info "Fix: conda activate <your-env>"
    info "     pip install -e /path/to/unitree_sdk2_python"
fi

# ── STEP 5: DDS connection test ──────────────────────────────────────────────
sep 5 "DDS connection to robot (10s timeout)"
if python3 "$SCRIPT_DIR/check_dds_connection.py" \
       --interface "$INTERFACE" \
       --peer "$ROBOT_IP" \
       --domain 0; then
    pass "DDS live — robot is publishing rt/lowstate"
else
    fail "No DDS messages received"
    info "Check: is robot in DAMPING mode (L2+B on controller)?"
    info "       Is CYCLONEDDS_HOME pointing to the correct install?"
    info "       Try rebooting the robot and re-entering DAMPING mode."
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
if [ "$EXIT_CODE" -eq 0 ]; then
    echo " ALL STEPS PASSED — safe to run encoder monitor:"
    echo ""
    echo "   python g1_encoder_monitor.py --interface $INTERFACE --peer $ROBOT_IP"
else
    echo " ONE OR MORE STEPS FAILED — fix above before deploying."
fi
echo "========================================"
exit "$EXIT_CODE"
