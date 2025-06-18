"""Response models for MAGG tools."""

from typing import Any, List, Union, Optional
from pydantic import BaseModel, ConfigDict


class MAGGResponse(BaseModel):
    """Standardized response format for MAGG tools.
    
    Provides a consistent structure for both success and error cases,
    optimized for LLM consumption with automatic JSON serialization.
    """
    
    model_config = ConfigDict(
        # Allow arbitrary types in output field
        arbitrary_types_allowed=True
    )
    
    errors: Optional[List[Union[str, dict]]] = None
    output: Optional[Any] = None
    
    @classmethod
    def success(cls, output: Any) -> "MAGGResponse":
        """Create a success response with output data."""
        return cls(output=output)
    
    @classmethod
    def error(cls, error: Union[str, dict, List[Union[str, dict]]]) -> "MAGGResponse":
        """Create an error response."""
        if isinstance(error, list):
            return cls(errors=error)
        return cls(errors=[error])

    def add_error(self, error: Union[str, dict]) -> None:
        """Add an error to the response."""
        if self.errors is None:
            self.errors = []
        self.errors.append(error)
    
    @property
    def is_success(self) -> bool:
        """Check if this is a successful response (no errors)."""
        return self.errors is None or len(self.errors) == 0
    
    @property
    def is_error(self) -> bool:
        """Check if this response contains errors."""
        return not self.is_success