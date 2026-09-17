from orders.service import OrderService
from orders.storage import OrderStore

def test_submit_order():
    assert OrderService(OrderStore()).submit_order('A1') == 'saved:A1'
