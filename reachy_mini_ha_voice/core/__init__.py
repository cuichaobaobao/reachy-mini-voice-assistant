"""Core module for Reachy Mini Voice Assistant.

This module contains fundamental components:
- DaemonStateMonitor: Monitors robot daemon state
- SleepAwareService: Base class for services that support resource suspend/resume
- ServiceManager: Manages multiple suspend-aware services
- Config: Centralized configuration management
- Exceptions: Project exception classes
- RobotStateMonitor: Robot connection state tracking
- Util: Common utility functions
"""

from .config import Config
from .daemon_monitor import DaemonState, DaemonStateMonitor, DaemonStatus
from .exceptions import (
    ConfigurationError,
    DaemonUnavailableError,
    EntityRegistrationError,
    ModelLoadError,
    ReachyHAError,
    ResourceUnavailableError,
    RobotConnectionError,
    ServiceSuspendedError,
)
from .robot_state_monitor import RobotStateMonitor
from .service_base import RobustOperationMixin, ServiceManager, ServiceState, SleepAwareService
from .util import call_all, get_mac

__all__ = [
    "Config",
    "ConfigurationError",
    "DaemonState",
    "DaemonStateMonitor",
    "DaemonStatus",
    "DaemonUnavailableError",
    "EntityRegistrationError",
    "ModelLoadError",
    # Exceptions
    "ReachyHAError",
    "ResourceUnavailableError",
    "RobotConnectionError",
    # Robot state
    "RobotStateMonitor",
    "RobustOperationMixin",
    "ServiceManager",
    "ServiceState",
    "ServiceSuspendedError",
    "SleepAwareService",
    "call_all",
    # Utilities
    "get_mac",
]
