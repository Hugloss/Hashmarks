from .storage import OrderStore

class OrderService:
    def __init__(self, store: OrderStore):
        self.store = store

    def submit_order(self, order_id: str) -> str:
        return self.store.save_order(order_id)
