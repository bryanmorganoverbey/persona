"""
Budget management utilities for goal agent.
"""


class BudgetExceededException(Exception):
    """Raised when an operation would exceed the remaining budget."""
    pass


def check_budget_before_call(remaining_budget: float, estimated_cost: float = 0.05) -> bool:
    """
    Check if we have sufficient budget remaining before making an API call.
    
    Args:
        remaining_budget: Amount of budget remaining in USD
        estimated_cost: Estimated cost of the upcoming API call in USD
        
    Returns:
        True if sufficient budget, False if would exceed budget
    """
    if remaining_budget <= 0:
        return False
    
    if estimated_cost > remaining_budget:
        return False
    
    return True
