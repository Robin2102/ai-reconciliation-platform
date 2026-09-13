"""
CONCEPT TO LEARN: the Adapter pattern.

Every upstream data source (CSV drop, REST API, another DB, a Kafka topic) is
DIFFERENT on the outside, but reconciliation only wants ONE canonical shape
on the inside. The adapter's job is to hide that difference.

This is also your first Pydantic-as-a-contract exercise, even inside Django:
the adapter's output is a Pydantic model, so it's validated the same way no
matter which concrete adapter produced it.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable, List, Optional
from pydantic import BaseModel, Field, model_validator


class CanonicalRecord(BaseModel):
    """
    The canonical shape every adapter produces.
    Reconciliation logic interacts exclusively with CanonicalRecord.
    """
    source_id: str = Field(description="Identifier of the data source")
    external_ref: str = Field(description="Upstream transaction reference ID")
    cr_amount: Decimal = Field(default=Decimal("0.00"), description="Credit amount (>= 0.00)")
    dr_amount: Decimal = Field(default=Decimal("0.00"), description="Debit amount (>= 0.00)")
    amount: Decimal = Field(default=Decimal("0.00"), description="Signed net amount (credit positive, debit negative)")
    currency: str = Field(default="INR", description="ISO currency code")
    timestamp: datetime = Field(description="UTC timestamp of the transaction")
    description: Optional[str] = Field(default=None, description="Transaction narrative/remarks")
    raw_payload: dict[str, Any] = Field(default_factory=dict, description="Original unparsed row payload for audit")

    @model_validator(mode="after")
    def compute_signed_amount(self) -> "CanonicalRecord":
        """
        Enforce credit/debit amount constraints and calculate signed net amount.
        amount = cr_amount - dr_amount
        """
        if self.cr_amount < Decimal("0.00"):
            raise ValueError(f"cr_amount must be non-negative, got {self.cr_amount}")
        if self.dr_amount < Decimal("0.00"):
            raise ValueError(f"dr_amount must be non-negative, got {self.dr_amount}")

        # Compute signed amount: Credit is positive (+), Debit is negative (-)
        self.amount = self.cr_amount - self.dr_amount
        return self


class DataSourceAdapter(ABC):
    """Base interface every concrete adapter implements."""

    @abstractmethod
    def extract(self, source_input: Any) -> Iterable[dict[str, Any]]:
        """Pull raw records from the source (file path, stream, DB, API)."""
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_record: dict[str, Any], source_id: str = "") -> CanonicalRecord:
        """Turn one raw record into a CanonicalRecord."""
        raise NotImplementedError

    def process(self, source_input: Any, source_id: str = "") -> List[CanonicalRecord]:
        """Convenience workflow method: extracts all raw records and normalizes them."""
        canonical_records = []
        for raw_record in self.extract(source_input):
            canonical = self.normalize(raw_record, source_id=source_id)
            canonical_records.append(canonical)
        return canonical_records

