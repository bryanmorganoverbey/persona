"""
Budget management utilities for goal agent.
"""


class BudgetExceededException(Exception):
    """Raised when an operation would exceed the remaining budget."""
    pass


def check_budget_before_call(remaining_budget: float, estimated_cost: float = 0.05) -> None:
    """
    Check if we have sufficient budget remaining before making an API call.
    
    Args:
        remaining_budget: Amount of budget remaining in USD
        estimated_cost: Estimated cost of the upcoming API call in USD
        
    Raises:
        BudgetExceededException: If estimated cost would exceed remaining budget
    """
    if remaining_budget <= 0:
        raise BudgetExceededException(
            f"Budget exhausted: ${remaining_budget:.4f} remaining"
        )
    
    if estimated_cost > remaining_budget:
        raise BudgetExceededException(
            f"Estimated cost ${estimated_cost:.4f} exceeds remaining budget ${remaining_budget:.4f}"
        )
