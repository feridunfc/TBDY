from tbdy_engine.tools.validate_contract_constitution import main


def test_validator_main_passes():
    assert main() == 0
