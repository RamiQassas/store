class PaymentGatewayError(Exception):
    pass


class BasePaymentGateway:
    code = "base"

    def create_payment(self, deposit):
        raise NotImplementedError

    def verify_payment(self, deposit):
        raise NotImplementedError


class ShamCashPlaceholderGateway(BasePaymentGateway):
    code = "sham_cash"

    def create_payment(self, deposit):
        return {
            "provider": self.code,
            "status": "pending",
            "message": "Sham Cash API placeholder is ready for bank credentials.",
            "deposit_id": str(deposit.id),
        }

    def verify_payment(self, deposit):
        return {"provider": self.code, "status": deposit.status}


def gateway_for(provider):
    if provider.provider_type == "sham_cash":
        return ShamCashPlaceholderGateway()
    return ShamCashPlaceholderGateway()
