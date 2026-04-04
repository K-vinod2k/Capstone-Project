import time
import sys
import os
import math

# Add the parent directory to sys.path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.core.channel import ChannelPublisher, ChannelSubscriber
from unitree_sdk2py.utils.crc import CRC

if config.ROBOT == "g1":
    from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowState_ as LowState_default
    from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_ as LowCmd_default
    from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_
    from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_
    # G1 currently might still use SportModeState from go if needed for high-level state, 
    # but for low-level control we use hg.
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
    from unitree_sdk2py.idl.default import unitree_go_msg_dds__SportModeState_
    NUM_MOTOR = 35
else:
    from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowState_ as LowState_default
    from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowCmd_ as LowCmd_default
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
    from unitree_sdk2py.idl.default import unitree_go_msg_dds__SportModeState_
    NUM_MOTOR = 20


def HighStateHandler(msg: SportModeState_):
    # print("Position: ", msg.position)
    pass


def LowStateHandler(msg: LowState_):
    # print("IMU quaternion: ", msg.imu_state.quaternion)
    pass


if __name__ == "__main__":
    # Initialize with domain ID from config, interface from config
    ChannelFactoryInitialize(config.DOMAIN_ID, config.INTERFACE)

    hight_state_suber = ChannelSubscriber("rt/sportmodestate", SportModeState_)
    low_state_suber = ChannelSubscriber("rt/lowstate", LowState_)

    hight_state_suber.Init(HighStateHandler, 10)
    low_state_suber.Init(LowStateHandler, 10)

    low_cmd_puber = ChannelPublisher("rt/lowcmd", LowCmd_)
    low_cmd_puber.Init()
    crc = CRC()

    # Create command message
    cmd = LowCmd_default()
    
    if config.ROBOT == "g1":
        cmd.mode_pr = 0
        cmd.mode_machine = 0
    else:
        cmd.head[0]=0xFE
        cmd.head[1]=0xEF
        cmd.level_flag = 0xFF
        cmd.gpio = 0

    # Initialize motor commands
    for i in range(NUM_MOTOR):
        cmd.motor_cmd[i].mode = 0x01  # (PMSM) mode
        cmd.motor_cmd[i].q= 0.0
        cmd.motor_cmd[i].kp = 0.0
        cmd.motor_cmd[i].dq = 0.0
        cmd.motor_cmd[i].kd = 0.0
        cmd.motor_cmd[i].tau = 0.0

    print(f"Starting simulation control for {config.ROBOT}...")
    
    dt = 0.002
    t = 0.0
    
    while True:
        t += dt
        
        # Move all joints back and forth using a sine wave on torque
        for i in range(NUM_MOTOR):
            cmd.motor_cmd[i].q = 0.0 
            cmd.motor_cmd[i].kp = 0.0
            cmd.motor_cmd[i].dq = 0.0 
            cmd.motor_cmd[i].kd = 0.0
            # Apply a small oscillating torque to all joints
            cmd.motor_cmd[i].tau = 1.5 * math.sin(2 * math.pi * 1.5 * t)

        if config.ROBOT != "g1":
            cmd.crc = crc.Crc(cmd)

        # Publish message
        low_cmd_puber.Write(cmd)
        time.sleep(dt)
