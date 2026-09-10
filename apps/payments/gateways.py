from apps.payments.paymera import PaymeraClient, PaymeraError


class PaymentGatewayError(Exception):
    pass


class BasePaymentGateway:
    code = "base"

    def create_payment(self, deposit, request=None):
        raise NotImplementedError

    def verify_payment(self, deposit):
        raise NotImplementedError


class ShamCashPlaceholderGateway(BasePaymentGateway):
    code = "sham_cash"

    def create_payment(self, deposit, request=None):
        return {
            "provider": self.code,
            "status": "pending",
            "message": "Sham Cash API placeholder is ready for bank credentials.",
            "deposit_id": str(deposit.id),
        }

    def verify_payment(self, deposit):
        return {"provider": self.code, "status": deposit.status}


class PaymeraGateway(BasePaymentGateway):
    code = "paymera"

    def __init__(self, integration=None):
        self.integration = integration

    def get_client(self) -> PaymeraClient:
        if not self.integration:
            from apps.payments.models import PaymentGatewayIntegration
            self.integration = PaymentGatewayIntegration.objects.filter(
                provider=PaymentGatewayIntegration.Provider.PAYMERA,
                is_active=True
            ).first()

        if not self.integration:
            raise PaymentGatewayError("لا توجد إعدادات مفعلة لبوابة بيميرا (Paymera). يرجى ضبطها من لوحة التحكم.")

        return PaymeraClient.from_integration(self.integration)

    def create_payment(self, deposit, request=None):
        from django.urls import reverse
        client = self.get_client()

        # Determine callback & trigger URLs
        if request:
            callback_base = request.build_absolute_uri(reverse("paymera_callback"))
            trigger_base = request.build_absolute_uri(reverse("paymera_trigger"))
        else:
            callback_base = reverse("paymera_callback")
            trigger_base = reverse("paymera_trigger")

        callback_url = f"{callback_base}?deposit_id={deposit.id}"
        trigger_url = f"{trigger_base}?deposit_id={deposit.id}"

        # Paymera operations are strictly in Syrian Liras (SYP)
        # Calculate amount in SYP
        currency_code = deposit.currency.code if deposit.currency else "USD"
        if currency_code == "SYP":
            syp_amount = deposit.amount
        else:
            from apps.common.models import Currency
            syp_currency = Currency.objects.filter(code="SYP").first()
            if syp_currency and hasattr(deposit.currency, "to_base"):
                usd_val = deposit.currency.to_base(deposit.amount, "deposit")
                syp_amount = syp_currency.from_base(usd_val, "deposit")
            else:
                syp_amount = deposit.amount

        notes = f"Deposit #{deposit.id} for user {deposit.user.email}"
        try:
            res = client.create_payment(
                amount=syp_amount,
                callback_url=callback_url,
                trigger_url=trigger_url,
                notes=notes,
                lang="ar",
            )
            deposit.gateway_payment_id = res["payment_id"]
            if not isinstance(deposit.metadata, dict):
                deposit.metadata = {}
            deposit.metadata["paymera_url"] = res["url"]
            deposit.metadata["paymera_payment_id"] = res["payment_id"]
            deposit.metadata["syp_amount"] = int(round(float(syp_amount)))
            deposit.save(update_fields=["gateway_payment_id", "metadata"])
            return res
        except PaymeraError as err:
            raise PaymentGatewayError(str(err)) from err

    def verify_payment(self, deposit):
        payment_id = deposit.gateway_payment_id or (
            deposit.metadata.get("paymera_payment_id") if isinstance(deposit.metadata, dict) else None
        )
        if not payment_id:
            raise PaymentGatewayError("لا يوجد معرف دفعة بيميرا لهذا الطلب.")

        client = self.get_client()
        try:
            return client.get_payment_status(payment_id)
        except PaymeraError as err:
            raise PaymentGatewayError(str(err)) from err


def gateway_for(provider_or_obj):
    if hasattr(provider_or_obj, "provider"):
        code = provider_or_obj.provider
        if code == "paymera":
            return PaymeraGateway(integration=provider_or_obj)
    elif hasattr(provider_or_obj, "gateway") and provider_or_obj.gateway:
        return gateway_for(provider_or_obj.gateway)
    elif hasattr(provider_or_obj, "provider_type"):
        code = provider_or_obj.provider_type
    else:
        code = str(provider_or_obj)

    if code == "paymera":
        return PaymeraGateway()
    if code == "sham_cash":
        return ShamCashPlaceholderGateway()
    return ShamCashPlaceholderGateway()
