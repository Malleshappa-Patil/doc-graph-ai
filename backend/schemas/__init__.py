# This file marks the schemas/ directory as a Python package.
# It allows other modules to import from it like:
#   from schemas.entities import Entity, EntityList
#   from schemas.relationships import Relationship, RelationshipList

from schemas.entities import Entity, EntityList
from schemas.relationships import Relationship, RelationshipList

__all__ = ["Entity", "EntityList", "Relationship", "RelationshipList"]
