from events import EventBus, EventTypes, JsonlEventStore
from models.mcp_requirement import MCPRequirement, ToolSpec


def test_event_store_appends_and_reads_in_sequence(tmp_path):
    store = JsonlEventStore(tmp_path)
    bus = EventBus("session-a", store=store)

    first = bus.publish(EventTypes.CREATE_MCP_REQUESTED, "test", "started")
    second = bus.publish(EventTypes.USER_MESSAGE_RECEIVED, "test", "message")

    events = store.read_session("session-a")
    assert [event.sequence for event in events] == [1, 2]
    assert events[0].event_id == first.event_id
    assert events[1].event_id == second.event_id


def test_event_bus_persists_and_notifies_subscribers(tmp_path):
    store = JsonlEventStore(tmp_path)
    bus = EventBus("session-b", store=store)
    seen = []
    bus.subscribe(seen.append)

    event = bus.publish(EventTypes.VALIDATION_PASSED, "validator", "passed")

    assert seen == [event]
    assert store.read_session("session-b") == [event]


def test_event_payload_accepts_pydantic_models(tmp_path):
    store = JsonlEventStore(tmp_path)
    bus = EventBus("session-c", store=store)
    req = MCPRequirement(
        mcp_name="price_tools",
        description="Price tools",
        tools=[
            ToolSpec(
                name="calculate_price",
                description="Calculates price",
                returns_type="float",
                returns_description="Final price",
            )
        ],
    )

    bus.publish(
        EventTypes.REQUIREMENT_UPDATED,
        "requirements_agent",
        "updated",
        payload={"requirement": req},
    )

    event = store.read_session("session-c")[0]
    assert event.payload["requirement"]["mcp_name"] == "price_tools"


def test_simulated_successful_session_event_order(tmp_path):
    store = JsonlEventStore(tmp_path)
    bus = EventBus("session-d", store=store)

    for event_type in [
        EventTypes.CREATE_MCP_REQUESTED,
        EventTypes.USER_MESSAGE_RECEIVED,
        EventTypes.REQUIREMENTS_COMPLETED,
        EventTypes.DESIGN_COMPLETED,
        EventTypes.CODE_GENERATED,
        EventTypes.VALIDATION_PASSED,
        EventTypes.CODE_READY,
        EventTypes.REGISTRY_UPDATED,
        EventTypes.SESSION_COMPLETED,
    ]:
        bus.publish(event_type, "test", event_type)

    events = store.read_session("session-d")
    assert [event.type for event in events][-2:] == [
        EventTypes.REGISTRY_UPDATED,
        EventTypes.SESSION_COMPLETED,
    ]


def test_validation_failed_schedules_retry_event(tmp_path):
    store = JsonlEventStore(tmp_path)
    bus = EventBus("session-e", store=store)

    bus.publish(EventTypes.VALIDATION_FAILED, "validator", "failed")
    bus.publish(EventTypes.VALIDATION_RETRY_SCHEDULED, "validator", "retry")

    assert [event.type for event in store.read_session("session-e")] == [
        EventTypes.VALIDATION_FAILED,
        EventTypes.VALIDATION_RETRY_SCHEDULED,
    ]
