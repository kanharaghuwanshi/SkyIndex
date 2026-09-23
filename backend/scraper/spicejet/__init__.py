"""SpiceJet source adapter for SkyIndex."""

from .client import SpiceJetClient, SpiceJetAPIError
from .parser import parse_availability_response

__all__ = [
    "SpiceJetClient",
    "SpiceJetAPIError",
    "parse_availability_response",
]
