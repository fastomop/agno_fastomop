from pydantic import BaseModel
from typing import List, Optional, Dict, Literal

class ConceptMapping(BaseModel):
    term: str
    concept_code: str
    vocabulary_id: str
    domain_id: Literal["Condition", "Drug", "Device", "Observation",
                         "Procedure", "Measurement", "Gender", 
                         "Race", "Ethnicity", "Visit"]
    concept_id: Optional[int] = None

class TemporalConstraint(BaseModel):
    window_days: int
    constraint_type: str # "within", "after", "before"

    def to_sql(self):
        if self.constraint_type == "within":
            return f"ABS(date1 - date2) <= {self.window_days}"
        elif self.constraint_type == "after":
            return f"(date1 - date2) >= 0 AND (date1 - date2) <= {self.window_days}"
        elif self.constraint_type == "before":
            return f"(date2 - date1) >= 0 AND (date2 - date1) <= {self.window_days}"

class SemanticContext(BaseModel):
    user_query: str
    query_intent: str  # Allow any query type (e.g., "demographics", "distribution", "cohort_analysis", etc.)

    entities: Optional[List[ConceptMapping]] = []  # Empty for demographics queries
    temporal_constraint: Optional[TemporalConstraint] = None
    additional_filters: Optional[Dict] = None

class QueryResult(BaseModel):
    sql: str
    result_count: Optional[int] = None
    execution_time: Optional[str] = None
    schema_prefix: str
    rows: Optional[List[Dict]] = None
    message: Optional[str] = None  # For error messages or explanations

class ErrorResponse(BaseModel):
    error_type: str
    message: str
    suggested_fix: Optional[str] = None


