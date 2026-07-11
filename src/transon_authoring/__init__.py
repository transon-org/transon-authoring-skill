"""transon-authoring — author engine-valid Transon JSON, verified before return.

The contract is docs/SPEC.md. Library surface (AD-006): get_metadata,
search_examples, check_samples, verify (+ debug validate / dry_run), delivered
across milestones A0-A2. This is the A0 grounding spine: the bundled pinned
metadata snapshot, the examples corpus with its NL-intents sidecar, and the
``python -m transon_authoring metadata`` entry; verification lands A1.
"""

__version__ = "0.0.1"
