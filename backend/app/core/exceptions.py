"""Domain exceptions for the service layer.

Services raise these; routers catch and convert to HTTPException.
"""


class EntityNotFound(Exception):
    def __init__(self, entity_type: str, identifier: str | int):
        self.entity_type = entity_type
        self.identifier = identifier
        super().__init__(f"{entity_type} {identifier} not found")


class DuplicateEntity(Exception):
    def __init__(self, entity_type: str, identifier: str):
        self.entity_type = entity_type
        self.identifier = identifier
        super().__init__(f"{entity_type} {identifier!r} already exists")


class BusinessRuleViolation(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class InvalidState(Exception):
    def __init__(self, message: str):
        super().__init__(message)
