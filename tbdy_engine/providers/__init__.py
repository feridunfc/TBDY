"""Provider foundation exports for C3.

Only fake/test provider infrastructure is implemented here. Live ETABS is out of
scope for C3.
"""
from tbdy_engine.providers.fake_etabs import FakeEtabsProvider
from tbdy_engine.providers.table_registry import TableRegistry

__all__ = ["FakeEtabsProvider", "TableRegistry"]
