"""transon-authoring — author engine-valid Transon JSON, verified before return.

The contract is docs/SPEC.md. Library surface (AD-006): get_metadata,
search_examples, check_samples, verify (+ debug validate / dry_run), delivered
across milestones A0-A2. A0 delivered the grounding spine (bundled pinned
metadata snapshot, examples corpus with its NL-intents sidecar, the
``python -m transon_authoring metadata`` entry); A1 delivers verification.
"""

from .examples import search_examples
from .metadata import get_metadata
from .samples import check_samples
from .verify import dry_run, validate, verify

__all__ = [
    "check_samples",
    "dry_run",
    "get_metadata",
    "search_examples",
    "validate",
    "verify",
]

__version__ = "0.0.1"
