import time
import sys
import os

# Add the parent directory to sys.path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient

if __name__ == "__main__":
    # Initialize Channel Factory
    ChannelFactoryInitialize(config.DOMAIN_ID, config.INTERFACE)

    # Create LocoClient from installed unitree_sdk2py
    client = LocoClient()
    client.Init()
    client.WaitLeaseApplied()

    print("G1 High Level Control Test Started (using unitree_sdk2py).")
    
    # 1. Sit / Damp (FSM 1)
    print("Calling Damp (FSM 1)...")
    client.Damp()
    time.sleep(2.0)

    # 2. Zero movement mode (FSM 200 / Start)
    print("Calling Start (FSM 200) - Zero movement...")
    client.Start()
    time.sleep(2.0)

    # 3. Running/walking mode
    print("Moving forward (vx=0.5 m/s) - Running/walking...")
    client.Move(0.5, 0.0, 0.0, True)
    time.sleep(3.0)

    # 4. The rest (Stop, and maybe back to Damp?)
    print("Stopping...")
    client.StopMove()
    time.sleep(1.0)

    print("Returning to Damp...")
    client.Damp()
    
    print("Test finished.")
