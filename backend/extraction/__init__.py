# This file marks extraction/ as a Python package.
# It re-exports the two main functions other modules will call.
#
# Usage:
#   from extraction import extract_entities, extract_relationships
#   from extraction.entity_extractor import extract_entities
#   from extraction.relationship_extractor import extract_relationships

from extraction.entity_extractor import extract_entities
from extraction.relationship_extractor import extract_relationships

__all__ = ["extract_entities", "extract_relationships"]
