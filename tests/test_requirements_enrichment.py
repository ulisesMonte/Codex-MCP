"""Tests for inference-first requirements enrichment."""
from langchain_core.messages import AIMessage, HumanMessage

from requirements.enrichment import (
    agent_asked_confirmation,
    combined_user_text,
    decide_status,
    enrich_requirement,
    finalize_requirement,
    is_affirmative,
    user_accepts_proposal,
    user_confirmed,
    user_facing_gaps,
    user_rejects_proposal,
    user_sent_tool_correction,
)
from models.mcp_requirement import MCPRequirement, ToolSpec


BIGQUERY_USER_TEXT = (
    "el mcp tiene una tool que se conecta a bigquery a la tabla source "
    "en el dataset info en el proyecto test y tendra una sola tool que haga eso, "
    "su nombre sera source_connection y no tendra parametros, sera simplemente "
    "para consultar la tabla"
)

MICROSERVICE_USER_TEXT = (
    "necesito un mcp para crear microservicios, distintas tools cada una para "
    "un controller, otra para un service y otra para generar repositories, "
    "con nombres descriptivos como controller_factory"
)

MICROSERVICE_NL_USER_TEXT = (
    "necesito que crees una tool de un mcp para crear microservciios, que haya 3 tools distintas, "
    "controller, service y repository, pero quiero que entienda como crear logica de "
    "microservicios en base a propmts de lenguaje natural"
)

CONNECTION_USER_TEXT = (
    "necesito un mcp con una tool para crear conexiones a postgres, "
    "que valide la conexion y devuelva el estado"
)


def test_enrich_bigquery_from_natural_language():
    req = enrich_requirement(MCPRequirement(), BIGQUERY_USER_TEXT)
    assert req.mcp_name == "source_connection"
    assert len(req.tools) >= 1
    assert req.tools[0].name == "source_connection"
    assert req.tools[0].parameters == []
    assert "google-cloud-bigquery" in req.dependencies
    assert req.is_ready(), req.missing_fields()


def test_enrich_microservice_nl_factory_three_tools_with_spec_param():
    req = enrich_requirement(MCPRequirement(), MICROSERVICE_NL_USER_TEXT)
    assert len(req.tools) == 3
    names = {t.name for t in req.tools}
    assert names == {"controller_factory", "service_factory", "repository_factory"}
    assert all(
        len(t.parameters) == 1 and t.parameters[0].name == "specification"
        for t in req.tools
    )
    assert req.mcp_name == "microservice_factory"
    assert req.is_ready()


def test_enrich_microservice_tools_from_natural_language():
    req = enrich_requirement(MCPRequirement(), MICROSERVICE_USER_TEXT)
    names = {t.name for t in req.tools}
    assert "controller_factory" in names
    assert "service_factory" in names
    assert "repository_factory" in names
    assert len(req.tools) >= 3
    assert req.is_ready()


def test_enrich_postgres_connection_from_natural_language():
    req = enrich_requirement(MCPRequirement(), CONNECTION_USER_TEXT)
    assert len(req.tools) >= 1
    assert any("connection" in t.name for t in req.tools)
    assert "psycopg2-binary" in req.dependencies
    assert req.mcp_name == "connection_manager"
    assert req.is_ready()


def test_affirmative_si_applies_agent_proposed_connection_name():
    messages = [
        HumanMessage(content=CONNECTION_USER_TEXT),
        AIMessage(content="¿Querés que la tool se llame `create_connection`?"),
        HumanMessage(content="si"),
    ]
    req = enrich_requirement(MCPRequirement(), CONNECTION_USER_TEXT, messages)
    assert any(t.name == "create_connection" for t in req.tools)
    assert req.clarifications_needed == []
    assert req.is_ready()


def test_affirmative_si_applies_factory_naming_after_agent_question():
    messages = [
        HumanMessage(content=MICROSERVICE_USER_TEXT),
        AIMessage(
            content=(
                "¿Querés que cada herramienta tenga un nombre específico como "
                "controller_factory, service_factory y repository_factory?"
            )
        ),
        HumanMessage(content="si"),
    ]
    req = enrich_requirement(MCPRequirement(), MICROSERVICE_USER_TEXT, messages)
    names = {t.name for t in req.tools}
    assert names == {"controller_factory", "service_factory", "repository_factory"}
    assert req.clarifications_needed == []
    assert req.is_ready()
    gaps = user_facing_gaps(req)
    assert not any("describe what the mcp" in g.lower() for g in gaps)
    assert any("confirm" in g.lower() for g in gaps)


def test_user_facing_gaps_when_ready_is_confirm_only():
    req = enrich_requirement(MCPRequirement(), BIGQUERY_USER_TEXT)
    gaps = user_facing_gaps(req)
    assert any("confirm" in g.lower() for g in gaps)


def test_user_facing_gaps_filters_client_id():
    req = MCPRequirement(
        mcp_name="x",
        description="y",
        tools=[ToolSpec(name="t", description="d", returns_type="str", returns_description="r")],
        clarifications_needed=["ID del cliente (Client ID) para BigQuery"],
    )
    gaps = user_facing_gaps(req)
    assert not any("client" in g.lower() for g in gaps)


def test_user_confirmed():
    assert user_confirmed("confirm")
    assert user_confirmed("confirmar")
    assert user_confirmed("conrim")
    assert not user_confirmed("sí")
    assert not user_confirmed("maybe")


def test_is_affirmative():
    assert is_affirmative("si")
    assert is_affirmative("sí")
    assert is_affirmative("yes")
    assert is_affirmative("perfecto, eso es lo que quiero")
    assert not is_affirmative("confirm")


def test_user_accepts_proposal_after_agent_confirm_question():
    from langchain_core.messages import AIMessage, HumanMessage

    messages = [
        HumanMessage(content="microservices factory with 3 tools"),
        AIMessage(content="¿Confirmás controllers_factory, services_factory y repositories_factory?"),
        HumanMessage(content="perfecto, eso es lo que quiero"),
    ]
    assert user_accepts_proposal("perfecto, eso es lo que quiero")
    assert agent_asked_confirmation(messages)
    req = enrich_requirement(MCPRequirement(), MICROSERVICE_USER_TEXT, messages)
    status = decide_status(req, "gathering", "perfecto, eso es lo que quiero", messages)
    assert status == "complete"


def test_user_correction_three_factory_tools():
    from langchain_core.messages import AIMessage, HumanMessage

    msg1 = (
        "necesito un mcp microservicesFactory con 3 funciones controllers services repositories"
    )
    msg2 = (
        "osea debe tener 3 tools uno para cada uno "
        "controller_factory, services_factory y repository_factory"
    )
    messages = [
        HumanMessage(content=msg1),
        AIMessage(content="Propongo un solo tool microservicesfactory. ¿Confirmás?"),
        HumanMessage(content=msg2),
    ]
    req = MCPRequirement(
        mcp_name="microservicesfactory",
        tools=[
            ToolSpec(
                name="microservicesfactory",
                description="wrong",
                returns_type="str",
                returns_description="r",
            )
        ],
    )
    req = enrich_requirement(req, combined_user_text(messages), messages)
    names = {t.name for t in req.tools}
    assert names == {
        "controller_factory",
        "services_factory",
        "repository_factory",
    }
    assert len(req.tools) == 3
    assert req.mcp_name == "microservice_factory"
    assert user_sent_tool_correction(msg2)


def test_finalize_requirement_forces_three_factory_tools_from_first_message():
    """User's exact prompt: microservicesFactory + 3 funciones."""
    msg = (
        "necesito un mcp microservicesFactory con 3 funciones "
        "controllers services repositories desde lenguaje natural"
    )
    messages = [HumanMessage(content=msg)]
    req = MCPRequirement(
        mcp_name="microservicesfactory",
        tools=[
            ToolSpec(
                name="repository_factory",
                description="only one",
                returns_type="str",
                returns_description="r",
            )
        ],
    )
    req = finalize_requirement(req, messages)
    names = {t.name for t in req.tools}
    assert len(req.tools) == 3
    assert names == {"controller_factory", "service_factory", "repository_factory"}
    assert req.mcp_name == "microservice_factory"


DAO_CRUD_USER_TEXT = (
    "quiero que crees un mcp que sirva para crear un DAO, osea que ayude a un agente "
    "a crear Daos a partir de mcp y cada tool del mcp debe ser una operacion CRUD del dao"
)

DAO_CRUD_CORRECTION = (
    "no, no es correcto, debe tener 4 tools, create, read, update, delete"
)


def test_enrich_dao_crud_four_tools_from_natural_language():
    req = enrich_requirement(MCPRequirement(), DAO_CRUD_USER_TEXT)
    assert len(req.tools) == 4
    assert [t.name for t in req.tools] == ["create", "read", "update", "delete"]
    assert req.mcp_name == "dao_mcp"
    assert req.is_ready()


def test_user_rejection_keeps_gathering_and_applies_crud_correction():
    messages = [
        HumanMessage(content=DAO_CRUD_USER_TEXT),
        AIMessage(content="Propongo tool `del`. ¿Es correcto?"),
        HumanMessage(content=DAO_CRUD_CORRECTION),
    ]
    req = MCPRequirement(
        mcp_name="del",
        description="Executes del",
        tools=[
            ToolSpec(
                name="del",
                description="wrong",
                returns_type="str",
                returns_description="r",
            )
        ],
    )
    req = enrich_requirement(req, combined_user_text(messages), messages)
    assert user_rejects_proposal(DAO_CRUD_CORRECTION)
    assert [t.name for t in req.tools] == ["create", "read", "update", "delete"]
    assert req.mcp_name == "dao_mcp"
    status = decide_status(req, "complete", DAO_CRUD_CORRECTION, messages)
    assert status == "gathering"


def test_user_rejects_proposal_blocks_complete():
    req = enrich_requirement(MCPRequirement(), BIGQUERY_USER_TEXT)
    assert user_rejects_proposal("no, no es correcto")
    status = decide_status(req, "complete", "no, no es correcto", [])
    assert status == "gathering"


def test_invalid_mcp_name_del_is_not_used():
    req = enrich_requirement(
        MCPRequirement(mcp_name="del", description="Executes del"),
        "cada tool del mcp debe ser una operacion CRUD",
    )
    assert req.mcp_name != "del"
    assert len(req.tools) == 4

