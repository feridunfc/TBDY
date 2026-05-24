from tbdy_engine.adapters.check_adapter import CheckAdapter


class DummyCatalog:
    def model_dump(self):
        return {
            "checks": {
                "column_capacity_hierarchy": {
                    "id": "column_capacity_hierarchy",
                    "evaluation": "COLUMN_DESIGN",
                    "evaluation_field": "capacity_hierarchy",
                    "runner_enabled": True,
                    "tbdy_ref": "TBDY §7.3.3",
                    "severity": "HIGH",
                    "category": "DESIGN_SCWB",
                }
            }
        }


def test_source_and_screening_level_are_inferred_from_message():
    adapter = CheckAdapter(DummyCatalog())
    raw_eval = {
        "outputs": [
            {
                "label": "C1",
                "story": "+0.00",
                "checks": {
                    "capacity_hierarchy": {
                        "status": "WARNING",
                        "ratio": 0.0,
                        "message": "SCWB DESIGN_LEVEL yapilamadi. source=screening_fallback",
                    }
                },
            }
        ]
    }
    results = adapter.adapt("COLUMN_DESIGN", raw_eval)
    assert len(results) == 1
    assert results[0].source == "screening_fallback"
    assert results[0].evaluation_level == "SCREENING"
