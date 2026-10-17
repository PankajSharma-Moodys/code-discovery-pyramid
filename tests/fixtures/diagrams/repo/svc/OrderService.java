package svc;

public class OrderService {
    private final OrderRepository repository;

    /** Places an order: validates, then saves. */
    public Order placeOrder(OrderRequest request) {
        Order order = new Order(request.getSku());
        validator.validate(order);
        return repository.save(order);
    }

    /**
     * Refunds an order. Calls repository.delete in the end.
     */
    public void refund(Order order) {
        notifier.notifyRefund(order);
        ledger.reverse(order);
        mailer.send(order);
        audit.log(order);
        repository.delete(order);
    }
}
