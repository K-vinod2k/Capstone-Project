"""
check_dds_connection.py — DDS Connectivity Test (10-second timeout)
--------------------------------------------------------------------
Subscribes to rt/lowstate and waits up to 10 seconds for a message.
Exits 0 on success, 1 on timeout.

Called by verify_g1_hardware.sh but can also be run standalone:

    python check_dds_connection.py --interface eth0 --peer 192.168.123.164
"""

import os
import sys
import time
import argparse


def main():
    parser = argparse.ArgumentParser(description="DDS connectivity test — 10s timeout")
    parser.add_argument("--interface", default="eth0")
    parser.add_argument("--peer", default="")
    parser.add_argument("--domain", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="Seconds to wait for first message (default: 10)")
    args = parser.parse_args()

    if args.peer:
        peer_xml = (
            f"<CycloneDDS><Domain><Discovery><Peers>"
            f"<Peer address=\"{args.peer}\"/>"
            f"</Peers></Discovery></Domain></CycloneDDS>"
        )
        os.environ["CYCLONEDDS_URI"] = peer_xml

    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
    from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_

    received = []

    def on_msg(msg: LowState_):
        received.append(msg)

    ChannelFactoryInitialize(args.domain, args.interface)
    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(on_msg, 10)

    print(f"  Waiting up to {args.timeout:.0f}s for rt/lowstate on {args.interface} "
          f"(domain {args.domain}, peer {args.peer or 'auto'})...")

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if received:
            break
        time.sleep(0.1)

    if received:
        m = received[0]
        imu = m.imu_state
        q0 = m.motor_state[0].q
        print(f"  Received {len(received)} message(s) in "
              f"{args.timeout - (deadline - time.monotonic()):.1f}s")
        print(f"  Motor[0].q={q0:.4f} rad | "
              f"IMU w={imu.quaternion[0]:.3f} x={imu.quaternion[1]:.3f} "
              f"y={imu.quaternion[2]:.3f} z={imu.quaternion[3]:.3f}")
        sys.exit(0)
    else:
        print(f"  Timeout — no messages received in {args.timeout:.0f}s")
        sys.exit(1)


if __name__ == "__main__":
    main()
