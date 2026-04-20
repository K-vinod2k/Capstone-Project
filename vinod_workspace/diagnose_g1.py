"""diagnose_g1.py - Diagnose G1 connectivity when LocoClient gives
'client send request error'.

Runs a layered health check from 'python imports work' up through 'LocoClient
accepts a safe command', stopping at the first failure. The output is meant
to be pasted back verbatim so we can identify where the pipeline is broken.

Usage:
    python vinod_workspace/diagnose_g1.py <iface>

    # Example on iotlab Linux:
    python vinod_workspace/diagnose_g1.py enp0s31f6

    # If you don't know the interface name, run without arg to just auto-detect:
    python vinod_workspace/diagnose_g1.py

Writes full log to /tmp/g1_diagnose_<timestamp>.log in addition to stdout.
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


LOG_PATH = Path(f"/tmp/g1_diagnose_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
_fh = open(LOG_PATH, "w")


def _line(s: str = "") -> None:
    print(s, flush=True)
    _fh.write(s + "\n")
    _fh.flush()


def banner(title: str) -> None:
    _line("")
    _line("=" * 72)
    _line(f"  {title}")
    _line("=" * 72)


def ok(msg: str) -> None:
    _line(f"  [PASS] {msg}")


def fail(msg: str) -> None:
    _line(f"  [FAIL] {msg}")


def warn(msg: str) -> None:
    _line(f"  [WARN] {msg}")


def info(msg: str) -> None:
    _line(f"         {msg}")


def run_cmd(cmd: list[str], timeout: float = 5.0) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return -1, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, f"timeout after {timeout}s"
    except Exception as e:
        return -3, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Check 1: Environment
# ---------------------------------------------------------------------------

def check_environment() -> None:
    banner("1. ENVIRONMENT")
    info(f"Python executable: {sys.executable}")
    info(f"Python version   : {sys.version.split()[0]}")
    info(f"Platform         : {platform.platform()}")
    info(f"Uname            : {platform.uname()}")
    info(f"CWD              : {os.getcwd()}")


# ---------------------------------------------------------------------------
# Check 2: Unitree SDK import
# ---------------------------------------------------------------------------

def check_sdk_import() -> bool:
    banner("2. UNITREE SDK IMPORT")
    try:
        import unitree_sdk2py   # type: ignore
        info(f"unitree_sdk2py loaded from: {unitree_sdk2py.__file__}")
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize  # noqa
        from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient  # noqa
        from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient  # noqa
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_  # noqa
        ok("All required Unitree SDK modules import cleanly.")
        return True
    except ImportError as e:
        fail(f"Import failed: {e}")
        info("Fix: pip install ./unitree_sdk2_python_repo  (from repo root)")
        info("     or activate the correct virtualenv where the SDK lives.")
        return False


# ---------------------------------------------------------------------------
# Check 3: Network
# ---------------------------------------------------------------------------

def list_interfaces() -> list[tuple[str, str]]:
    """Return list of (iface, ip) for NICs with IPv4 addresses."""
    results: list[tuple[str, str]] = []
    rc, out = run_cmd(["ip", "-o", "-4", "addr"])
    if rc == 0 and out:
        for ln in out.splitlines():
            parts = ln.split()
            if len(parts) >= 4 and parts[2] == "inet":
                iface = parts[1]
                ip = parts[3].split("/")[0]
                results.append((iface, ip))
        return results
    # macOS fallback
    rc, out = run_cmd(["ifconfig"])
    if rc == 0 and out:
        current = None
        for ln in out.splitlines():
            if ln and not ln.startswith("\t") and not ln.startswith(" "):
                current = ln.split(":")[0]
            elif "inet " in ln and current:
                ip = ln.strip().split()[1]
                results.append((current, ip))
    return results


def check_network(preferred_iface: Optional[str]) -> Optional[str]:
    banner("3. NETWORK")
    ifaces = list_interfaces()
    if not ifaces:
        fail("Could not enumerate network interfaces.")
        return None
    info("Available IPv4 interfaces:")
    chosen: Optional[str] = None
    for iface, ip in ifaces:
        tag = ""
        if ip.startswith("192.168.123."):
            tag = "   <-- ROBOT SUBNET"
            if chosen is None:
                chosen = iface
        info(f"    {iface:15s}  {ip}{tag}")

    if preferred_iface:
        match = [i for i, _ in ifaces if i == preferred_iface]
        if match:
            ok(f"User-specified iface '{preferred_iface}' exists.")
            chosen = preferred_iface
        else:
            fail(f"User-specified iface '{preferred_iface}' does NOT exist.")
            info(f"Available: {[i for i, _ in ifaces]}")
            return None

    if chosen is None:
        fail("No interface on the 192.168.123.x subnet.")
        info("Fix: plug Ethernet into robot, set laptop static IP 192.168.123.222/24")
        return None
    ok(f"Will use interface: {chosen}")

    banner("3b. PING ROBOT")
    for host in ("192.168.123.161", "192.168.123.164"):
        rc, out = run_cmd(["ping", "-c", "2", "-W", "2", host])
        if rc == 0:
            ok(f"{host} responds")
        else:
            fail(f"{host} UNREACHABLE")
            info(out.splitlines()[-1] if out else "(no output)")

    return chosen


# ---------------------------------------------------------------------------
# Check 4: DDS channel factory
# ---------------------------------------------------------------------------

def check_channel_factory(iface: str) -> bool:
    banner("4. DDS CHANNEL FACTORY")
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    try:
        info(f"Calling ChannelFactoryInitialize(0, '{iface}')...")
        ChannelFactoryInitialize(0, iface)
        ok("ChannelFactoryInitialize returned without error.")
        return True
    except Exception as e:
        fail(f"ChannelFactoryInitialize raised: {type(e).__name__}: {e}")
        info("Fix: check interface name and robot network.")
        return False


# ---------------------------------------------------------------------------
# Check 5: rt/lowstate subscription
# ---------------------------------------------------------------------------

def check_lowstate_subscription(timeout_s: float = 3.0) -> bool:
    banner("5. SUBSCRIBE TO rt/lowstate (robot telemetry)")
    from unitree_sdk2py.core.channel import ChannelSubscriber
    from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_

    state = {"msg": None, "count": 0}

    def _handler(msg):
        state["msg"] = msg
        state["count"] += 1

    try:
        sub = ChannelSubscriber("rt/lowstate", LowState_)
        sub.Init(_handler, 10)
    except Exception as e:
        fail(f"Subscriber init failed: {type(e).__name__}: {e}")
        return False

    info(f"Waiting up to {timeout_s}s for rt/lowstate messages...")
    t0 = time.time()
    while state["msg"] is None and (time.time() - t0) < timeout_s:
        time.sleep(0.05)

    if state["msg"] is None:
        fail("No rt/lowstate received within timeout.")
        info("Meaning: the robot isn't publishing DDS to this interface.")
        info("Check : robot powered on, SDK firmware running, iface correct.")
        return False

    time.sleep(0.5)
    msg = state["msg"]
    ok(f"Received {state['count']} rt/lowstate messages.")
    try:
        info(f"mode_machine reported  = {msg.mode_machine}")
        info(f"IMU roll/pitch/yaw     = "
             f"{msg.imu_state.rpy[0]:+.3f} "
             f"{msg.imu_state.rpy[1]:+.3f} "
             f"{msg.imu_state.rpy[2]:+.3f} rad")
        info(f"First 4 motor q values = "
             f"{msg.motor_state[0].q:+.3f} "
             f"{msg.motor_state[1].q:+.3f} "
             f"{msg.motor_state[2].q:+.3f} "
             f"{msg.motor_state[3].q:+.3f}")
    except Exception as e:
        warn(f"Could not read all message fields: {e}")
    return True


# ---------------------------------------------------------------------------
# Check 6: LocoClient Init
# ---------------------------------------------------------------------------

def check_loco_client_init() -> Optional[object]:
    banner("6. LocoClient INIT")
    from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
    try:
        c = LocoClient()
        c.SetTimeout(5.0)
        c.Init()
        ok("LocoClient().Init() returned without error.")
        return c
    except Exception as e:
        fail(f"LocoClient Init raised: {type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------------------
# Check 7: LocoClient safe probe (Damp - cannot move robot)
# ---------------------------------------------------------------------------

def check_loco_client_damp(loco) -> bool:
    banner("7. LocoClient.Damp()  (passive hold - robot will NOT move)")
    info("Sending Damp(). If the robot is standing, it will drop into")
    info("its passive damping state. Make sure the gantry is attached.")
    input("Press Enter to send Damp()...")
    try:
        loco.Damp()
        ok("Damp() returned without raising.")
        info("If 'client send request error' printed above, the motion")
        info("service on the robot is not accepting requests. Likely causes:")
        info("  - robot is in DEBUG MODE (L2+R2 -> L2+A was pressed): reboot robot")
        info("  - a previous script called ReleaseMode(): reboot robot")
        info("  - motion service crashed: reboot robot")
        return True
    except Exception as e:
        fail(f"Damp() raised: {type(e).__name__}: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    banner("G1 CONNECTIVITY DIAGNOSTIC")
    info(f"Log file: {LOG_PATH}")
    info(f"Time    : {datetime.now().isoformat()}")

    preferred = sys.argv[1] if len(sys.argv) > 1 else None

    check_environment()

    if not check_sdk_import():
        return 2

    iface = check_network(preferred)
    if iface is None:
        return 3

    if not check_channel_factory(iface):
        return 4

    if not check_lowstate_subscription():
        banner("DIAGNOSIS")
        fail("Robot is NOT publishing telemetry on this network interface.")
        info("This is the most common cause of 'client send request error'.")
        info("Fix sequence:")
        info("  1. power-cycle the robot")
        info("  2. confirm laptop IP is 192.168.123.222/24 (or similar)")
        info("  3. re-run this diagnostic")
        return 5

    loco = check_loco_client_init()
    if loco is None:
        return 6

    if not check_loco_client_damp(loco):
        banner("DIAGNOSIS")
        fail("LocoClient initialized but service did not accept Damp().")
        info("Almost certainly DEBUG MODE or stale ReleaseMode state.")
        info("Fix: REBOOT the robot (power cycle), then re-run.")
        return 7

    banner("ALL CHECKS PASSED")
    ok("Network + DDS + LocoClient + robot service all healthy.")
    info("You can now run g1_loco_overlay.py safely.")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        _line("\n[interrupted]")
        code = 130
    finally:
        _line("")
        _line(f"Full log saved to: {LOG_PATH}")
        _fh.close()
    sys.exit(code)
