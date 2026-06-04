"""Tests for pipeline UI helpers."""
import time

from langchain_core.messages import AIMessage, HumanMessage

from requirements.enrichment import enrich_requirement
from events.types import EventTypes
from cli.pipeline_ui import (
    PIPELINE_MILESTONE_EVENTS,
    PIPELINE_UI_REFRESH_INTERVAL_S,
    ThrottledRefresher,
    will_run_full_pipeline,
)
from models.mcp_requirement import MCPRequirement


def test_pipeline_refresh_interval_is_slow_enough_for_stable_ui():
    assert PIPELINE_UI_REFRESH_INTERVAL_S >= 3.0


def test_pipeline_milestone_events_include_scout_phases():
    assert EventTypes.SCOUT_STARTED in PIPELINE_MILESTONE_EVENTS
    assert EventTypes.SCOUT_VALIDATION_COMPLETED in PIPELINE_MILESTONE_EVENTS


def test_throttled_refresher_default_interval_is_slow():
    r = ThrottledRefresher()
    assert r.min_interval_s >= 2.0


def test_throttled_refresher_mark_refreshed():
    r = ThrottledRefresher(min_interval_s=10.0)
    assert r.should_refresh() is True
    r.mark_refreshed()
    assert r.should_refresh() is False


def test_will_run_full_pipeline_on_confirm():
    req = enrich_requirement(
        MCPRequirement(),
        "mcp microservice factory with controller service repository",
    )
    state = {"requirement": req, "phase": "gathering", "messages": []}
    assert will_run_full_pipeline(state, "confirm") is True


def test_will_run_full_pipeline_false_while_gathering():
    state = {"requirement": MCPRequirement(), "phase": "gathering", "messages": []}
    assert will_run_full_pipeline(state, "necesito un mcp") is False


def test_will_run_full_pipeline_on_accept_after_agent_question():
    req = enrich_requirement(
        MCPRequirement(),
        "microservice factory controller service repository",
    )
    messages = [
        HumanMessage(content="microservice factory"),
        AIMessage(content="¿Confirmás controller_factory, service_factory y repository_factory?"),
    ]
    state = {"requirement": req, "phase": "gathering", "messages": messages}
    assert will_run_full_pipeline(state, "perfecto, eso es lo que quiero") is True


def test_will_run_full_pipeline_false_on_user_rejection():
    req = enrich_requirement(
        MCPRequirement(),
        "mcp dao con operaciones crud create read update delete",
    )
    state = {"requirement": req, "phase": "gathering", "messages": []}
    assert will_run_full_pipeline(state, "no, no es correcto") is False


def test_throttled_refresher_rate_limits():
    r = ThrottledRefresher(min_interval_s=10.0)
    assert r.should_refresh() is True
    assert r.should_refresh() is False
    r.reset()
    assert r.should_refresh() is True
