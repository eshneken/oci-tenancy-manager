"""Selected managed-object repair requests; no client-authored content or credentials."""

from typing import Annotated
from uuid import UUID

from pydantic import Field, model_validator

from otm.configuration.rollout_contracts import Category
from otm.contracts import Contract


# A preview selects one registered child and unique managed categories; assignment stays unchanged.
class ConfigurationRepairRequest(Contract):
    tenancy_id: UUID
    categories: Annotated[tuple[Category, ...], Field(min_length=1, max_length=4)]

    # Duplicate selections cannot obscure the reviewed mutation set.
    @model_validator(mode="after")
    def unique_categories(self):
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("DUPLICATE_REPAIR_CATEGORY")
        return self
