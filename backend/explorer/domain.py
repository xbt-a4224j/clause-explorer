"""This application's declaration of itself, read once at import.

`quorum.yaml` in the repo root says which Cube members mean what: the subject axis nearly
every question names, the dimension holding the answer, the two count measures and the
denominator a percentile is out of. The platform reads it and needs to know nothing about
mergers.

One module-level instance rather than a parameter threaded through every call site. The
manifest is a file on disk that cannot change while the process runs, and passing it down
seven layers would be ceremony around a constant. `load()` is exported for tests that want a
modified domain.

Validation happens here, at import, on purpose: a manifest naming a member that does not exist
produces an app that declines every question, and that symptom reads as a model problem rather
than a configuration one. Failing at startup costs a container restart; failing at query time
costs an afternoon.
"""

from __future__ import annotations

import pathlib

from quorum.domain import Domain, load

#: The repo root — three levels up from `backend/explorer/domain.py`.
ROOT = pathlib.Path(__file__).resolve().parents[2]

DOMAIN: Domain = load(ROOT)

__all__ = ["DOMAIN", "ROOT", "Domain", "load"]
