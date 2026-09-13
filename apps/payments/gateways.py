from apps.payments.paymera import PaymeraClient, PaymeraError


class PaymentGatewayError(Exception):
    pass


class BasePaymentGateway:
    code = "base"

    def create_payment(self, deposit, request=None):
        raise NotImplementedError

    def verify_payment(self, deposit):
        raise NotImplementedError

    def create_order_payment(self, order, request=None):
        raise NotImplementedError

    def verify_order_payment(self, order):
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
        has_creds = (
            self.integration
            and getattr(self.integration, "api_key", None)
            and getattr(self.integration, "terminal_id", None)
        )
        if not has_creds:
            from apps.payments.models import PaymentGatewayIntegration
            self.integration = (
                PaymentGatewayIntegration.all_objects.filter(
                    provider=PaymentGatewayIntegration.Provider.PAYMERA,
                    is_active=True
                )
                .exclude(terminal_id="")
                .exclude(api_key="")
                .first()
            )

        if self.integration:
            return PaymeraClient.from_integration(self.integration)

        from django.conf import settings
        return PaymeraClient(
            api_key=getattr(settings, "PAYMERA_API_KEY", "70504_FSdHLdNbZaa2KC6PthtNSuKqtgc88fiABRGxPczJ"),
            terminal_id=getattr(settings, "PAYMERA_TERMINAL_ID", "14740429"),
            base_url=getattr(settings, "PAYMERA_BASE_URL", "https://egate-t.paymera.cc"),
            mode=getattr(settings, "PAYMERA_MODE", "sandbox"),
        )

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

    def create_order_payment(self, order, request=None):
        from django.urls import reverse
        from apps.common.models import Currency
        client = self.get_client()

        if request:
            callback_base = request.build_absolute_uri(reverse("paymera_callback"))
            trigger_base = request.build_absolute_uri(reverse("paymera_trigger"))
        else:
            callback_base = reverse("paymera_callback")
            trigger_base = reverse("paymera_trigger")

        callback_url = f"{callback_base}?order_id={order.id}"
        trigger_url = f"{trigger_base}?order_id={order.id}"

        # Order total_amount is in USD. Convert to Syrian Liras (SYP)
        syp_currency = Currency.all_objects.filter(code="SYP").first()
        if syp_currency:
            syp_amount = syp_currency.from_base(order.total_amount, "deposit")
        else:
            syp_amount = order.total_amount

        notes = f"Order #{order.number} for {order.customer.email}"
        try:
            res = client.create_payment(
                amount=syp_amount,
                callback_url=callback_url,
                trigger_url=trigger_url,
                notes=notes,
                lang="ar",
            )
            if not isinstance(order.metadata, dict):
                order.metadata = {}
            order.metadata["gateway_payment_id"] = res["payment_id"]
            order.metadata["paymera_url"] = res["url"]
            order.metadata["syp_amount"] = int(round(float(syp_amount)))
            order.metadata["payment_provider"] = self.code
            order.save(update_fields=["metadata"])
            return res
        except PaymeraError as err:
            raise PaymentGatewayError(str(err)) from err

    def verify_order_payment(self, order):
        payment_id = (
            order.metadata.get("gateway_payment_id")
            if isinstance(order.metadata, dict)
            else None
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
