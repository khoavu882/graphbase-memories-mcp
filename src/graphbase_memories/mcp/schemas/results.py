"""Re-exports from domain.results — kept so adapter code needs no import changes."""

from graphbase_memories.domain.results import (  # noqa: F401
    AffectedServiceItem,
    BatchSaveResult,
    ConflictRecord,
    ContextBundle,
    CrossServiceBundle,
    CrossServiceItem,
    FreshnessReport,
    GovernanceTokenResult,
    HygieneReport,
    ImpactReport,
    SaveResult,
    ServiceInfo,
    ServiceListResult,
    ServiceRegistrationResult,
    StaleItem,
    SurfaceMatch,
    SurfaceResult,
    WorkspaceHealthReport,
    WorkspaceServiceHealth,
)
