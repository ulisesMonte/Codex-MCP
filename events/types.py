"""Event type constants used by the MCP Factory pipeline."""


class EventTypes:
    CREATE_MCP_REQUESTED = "CreateMCPRequested"
    USER_MESSAGE_RECEIVED = "UserMessageReceived"
    SESSION_COMPLETED = "SessionCompleted"
    SESSION_FAILED = "SessionFailed"

    REQUIREMENTS_STARTED = "RequirementsStarted"
    REQUIREMENT_UPDATED = "RequirementUpdated"
    CLARIFICATION_NEEDED = "ClarificationNeeded"
    REQUIREMENTS_COMPLETED = "RequirementsCompleted"

    DESIGN_STARTED = "DesignStarted"
    DESIGN_COMPLETED = "DesignCompleted"
    DESIGN_FAILED = "DesignFailed"

    SCOUT_STARTED = "ScoutStarted"
    SCOUT_COMPLETED = "ScoutCompleted"
    SCOUT_VALIDATION_STARTED = "ScoutValidationStarted"
    SCOUT_VALIDATION_COMPLETED = "ScoutValidationCompleted"

    CODE_GENERATION_STARTED = "CodeGenerationStarted"
    CODE_GENERATED = "CodeGenerated"
    CODE_REPAIR_STARTED = "CodeRepairStarted"
    CODE_GENERATION_FAILED = "CodeGenerationFailed"

    VALIDATION_STARTED = "ValidationStarted"
    VALIDATION_PASSED = "ValidationPassed"
    VALIDATION_FAILED = "ValidationFailed"
    VALIDATION_RETRY_SCHEDULED = "ValidationRetryScheduled"

    DEPLOYMENT_STARTED = "DeploymentStarted"
    CODE_READY = "CodeReady"
    MCP_DEPLOYED = "MCPDeployed"
    DEPLOYMENT_FAILED = "DeploymentFailed"

    REGISTRY_UPDATE_STARTED = "RegistryUpdateStarted"
    REGISTRY_UPDATED = "RegistryUpdated"

    PIPELINE_FAILED = "PipelineFailed"
