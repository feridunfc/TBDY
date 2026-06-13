"""TBDY Engine package.

C1 Contract Constitution hardening keeps package import side-effect free.
Runtime modules must be imported explicitly from their concrete module paths;
package import must not touch ETABS clients, UI, DAG, scheduler, or legacy runners.
"""
from __future__ import annotations

__version__ = "0.1.0-c1-contract-hardening"

__all__ = ["__version__"]
