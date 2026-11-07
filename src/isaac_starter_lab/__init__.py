"""IsaacLabStarterLab: a reproducible tabletop pick-and-place teaching lab.

The package is split into small, testable modules:

``config``       frozen dataclasses for scene, camera and arm parameters
``scene``        real OpenUSD scene generation and reproducible hashing
``sim``          message schema, deterministic CPU backend, Isaac Sim adapter
``render``       NumPy/Pillow pinhole renderer matching the USD camera
``bridge``       dependency-free local bus and a ROS 2 bridge on one protocol
``perception``   HSV + connected components cube detector
``controller``   explicit pick-and-place state machine with analytic IK
``isaac_lab``    Isaac Lab task configuration mirroring the real ManagerBased API
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
