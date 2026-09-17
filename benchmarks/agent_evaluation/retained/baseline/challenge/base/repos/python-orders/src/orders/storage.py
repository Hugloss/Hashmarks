class OrderStore:
    def save_order(self, order_id: str) -> str:
        return f'saved:{order_id}'
