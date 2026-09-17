"""SKYGUARD Simulator Package.

Synthetic AWS network generation, continuous meteorological dynamics,
controlled sensor fault injection, and scenario orchestration.
"""

from simulator.network import (
    DEFAULT_STATIONS,
    StationState,
    VirtualAWSNetwork,
)
from simulator.faults import (
    BaseFault,
    CommunicationFault,
    DriftFault,
    FrozenFault,
    SpikeFault,
    create_fault,
    normalize_param_name,
)
from simulator.scenario_engine import (
    ScenarioEngine,
    ScenarioResult,
)

__all__ = [
    "DEFAULT_STATIONS",
    "StationState",
    "VirtualAWSNetwork",
    "BaseFault",
    "SpikeFault",
    "FrozenFault",
    "DriftFault",
    "CommunicationFault",
    "create_fault",
    "normalize_param_name",
    "ScenarioEngine",
    "ScenarioResult",
]
