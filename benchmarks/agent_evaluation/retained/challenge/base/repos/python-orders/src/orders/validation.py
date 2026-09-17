def validate_order_id(order_id: str) -> bool:
    return bool(order_id and order_id.strip())
