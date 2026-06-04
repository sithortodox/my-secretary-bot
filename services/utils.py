from logger import logger


def safe_split_callback(data: str, prefix: str = "", min_parts: int = 2) -> list[str] | None:
    """
    Safely split callback.data and validate format.
    
    Args:
        data: The callback.data string
        prefix: Expected prefix (e.g., "adm:")
        min_parts: Minimum number of parts required
        
    Returns:
        List of parts if valid, None otherwise
    """
    if not data:
        return None
    
    parts = data.split(":")
    
    if len(parts) < min_parts:
        logger.warning(f"[CALLBACK] Invalid callback data format: {data}")
        return None
    
    if prefix and not data.startswith(prefix):
        logger.warning(f"[CALLBACK] Unexpected prefix in: {data}")
        return None
    
    return parts


def safe_int(value: str, field_name: str = "value") -> int | None:
    """
    Safely convert string to int.
    
    Returns:
        int if valid, None otherwise
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"[CALLBACK] Invalid {field_name}: {value}")
        return None
