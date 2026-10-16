"""The rule router decides which nodes run, so its keyword matching has to be exact."""
import pytest

from src.adapters.llm_adapter import RuleLLMAdapter

router = RuleLLMAdapter()


@pytest.mark.parametrize("query", [
    "validate flight against DGCA CAR and active NOTAMs",
    "check crane NOTAM and DGCA CAR limits for this flight",
    "is this allowed under §7",
    "what do the rules say about this zone",
])
def test_a_regulatory_question_with_coordinates_takes_both_nodes(query):
    assert router.route(query, has_coords=True) == "both"


@pytest.mark.parametrize("query", [
    "D40 telemetry status check",
    "D7 scarce battery check",         # 'car' inside 'scarce'
    "carry out a routine ping",        # 'car' inside 'carry'
    "cardio payload test",             # 'car' inside 'cardio'
])
def test_a_plan_with_no_regulatory_question_takes_the_act_route(query):
    """Substring matching used to send these to 'both' because they contain 'car'."""
    assert router.route(query, has_coords=True) == "act"


def test_a_question_without_coordinates_takes_the_retrieve_route():
    assert router.route("what is the ceiling under CAR §7", has_coords=False) == "retrieve"
