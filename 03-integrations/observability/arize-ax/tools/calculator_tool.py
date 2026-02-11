"""Calculator tool for performing mathematical operations."""

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def calculator(
    operation: str,
    a: float,
    b: float | None = None,
) -> dict[str, Any]:
    """Perform mathematical calculations.

    Args:
        operation: The operation (add, subtract, multiply, divide, factorial)
        a: First number (or the number for factorial)
        b: Second number (not used for factorial)

    Returns:
        Dictionary containing the operation, inputs, and result
    """
    if not operation or not isinstance(operation, str):
        raise ValueError("Operation must be a non-empty string")

    op = operation.strip().lower()
    valid_ops = ["add", "subtract", "multiply", "divide", "factorial"]
    if op not in valid_ops:
        raise ValueError(
            f"Unknown operation: {operation}. Valid: {', '.join(valid_ops)}"
        )

    if not isinstance(a, (int, float)):
        raise ValueError("First number must be numeric")

    logger.info("Performing %s with a=%s, b=%s", op, a, b)

    if op == "add":
        if b is None:
            raise ValueError("Addition requires two numbers")
        result_value = a + b
    elif op == "subtract":
        if b is None:
            raise ValueError("Subtraction requires two numbers")
        result_value = a - b
    elif op == "multiply":
        if b is None:
            raise ValueError("Multiplication requires two numbers")
        result_value = a * b
    elif op == "divide":
        if b is None:
            raise ValueError("Division requires two numbers")
        if b == 0:
            raise ValueError("Cannot divide by zero")
        result_value = a / b
    elif op == "factorial":
        if a < 0:
            raise ValueError("Cannot calculate factorial of a negative number")
        if not float(a).is_integer():
            raise ValueError("Factorial requires an integer value")
        result_value = math.factorial(int(a))

    return {
        "operation": op,
        "input_a": a,
        "input_b": b,
        "result": result_value,
    }
