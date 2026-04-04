# Action Items
- Create an empty GitHub repository, add collaborators, and configure repository settings so the team can push and access simulation code
- Upload the existing simulation code to the GitHub repository and share the repository link and access with the team
- Add a README to the repository listing required configuration changes and run notes (disable joystick, set correct robot DOF config, Cyclone DDS/OS limitations, mujoco setup steps) so others can run the simulation
- Create proper documentation for the project and the simulation tests (including how to run simulation in MuJoCo and notes about low-level vs high-level commands) to improve project clarity
- Ensure each team member sets up the code locally and can run the provided simulation; verify working simulation within one week
- Search for and document available high-level command APIs for the Unity/Unitree robot (particularly commands supporting leg movement and balancing) to enable high-level control integration
- Plan and start hardware testing with the physical robot in approximately 2–3 weeks to validate simulation behavior on the real robot

# Outline
### Robot Vision Integration Challenges
- The team identified that the robot’s main camera output is unreliable, requiring a solution to ensure accurate visual data for operation.

### Robot Control and High‑Level Command Development
- The team must develop high‑level leg movement commands for Unitree robot control.
- Documentation and accurate hand‑gesture tracking for upper body must be completed.

### Simulation‑Based Robot Testing Strategy
- The team will test robot movements in simulation using low‑level controls, foregoing VR hardware and hard‑coded gestures, and may incorporate vision models to track hand motions.

### GitHub Collaboration and Hardware Testing Plan
- The team will push the current SDK code to GitHub and work locally on high‑level commands.
- Weekly online syncs will prepare for hardware testing in two to three weeks.
- The team discussed ensuring the robot’s high‑level commands maintain balance and considered a fully wireless system for the showcase.
