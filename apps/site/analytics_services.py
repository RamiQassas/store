import json
from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Sum, Count, F, Q, ExpressionWrapper, DecimalField
from django.utils import timezone

from apps.accounts.models import User
from apps.orders.models import Order, OrderItem, Coupon
from apps.payments.models import DepositRequest, WithdrawalRequest, PaymentMethod
from apps.wallets.models import Wallet, LedgerEntry, WalletTransaction
from apps.common.models import Currency

class FinancialAnalyticsService:
    def __init__(self, filters=None):
        self.filters = filters or {}
        # Expected filters: start_date, end_date, currency_id, payment_method_id, tier, user_id, product_id, status
        self._cache = {}

    def _apply_date_filter(self, queryset, date_field="created_at"):
        start_date_str = self.filters.get("start_date")
        end_date_str = self.filters.get("end_date")
        
        # Handle predefined ranges
        date_preset = self.filters.get("date_preset")
        now = timezone.now()
        if date_preset == "today":
            queryset = queryset.filter(**{f"{date_field}__date": now.date()})
        elif date_preset == "yesterday":
            queryset = queryset.filter(**{f"{date_field}__date": now.date() - timedelta(days=1)})
        elif date_preset == "this_week":
            start_of_week = now - timedelta(days=now.weekday())
            queryset = queryset.filter(**{f"{date_field}__date__gte": start_of_week.date()})
        elif date_preset == "last_week":
            start_of_last_week = now - timedelta(days=now.weekday() + 7)
            end_of_last_week = start_of_last_week + timedelta(days=6)
            queryset = queryset.filter(**{f"{date_field}__date__gte": start_of_last_week.date(), f"{date_field}__date__lte": end_of_last_week.date()})
        elif date_preset == "this_month":
            queryset = queryset.filter(**{f"{date_field}__year": now.year, f"{date_field}__month": now.month})
        elif date_preset == "last_month":
            first_day_this_month = now.replace(day=1)
            last_month = first_day_this_month - timedelta(days=1)
            queryset = queryset.filter(**{f"{date_field}__year": last_month.year, f"{date_field}__month": last_month.month})
        else:
            # Custom range
            if start_date_str:
                try:
                    start_date = timezone.datetime.fromisoformat(start_date_str)
                    if timezone.is_naive(start_date): start_date = timezone.make_aware(start_date)
                    queryset = queryset.filter(**{f"{date_field}__gte": start_date})
                except ValueError: pass
            if end_date_str:
                try:
                    end_date = timezone.datetime.fromisoformat(end_date_str)
                    if timezone.is_naive(end_date): end_date = timezone.make_aware(end_date)
                    queryset = queryset.filter(**{f"{date_field}__lte": end_date})
                except ValueError: pass
                
        return queryset

    def _apply_common_filters(self, queryset, prefix=""):
        pfx = f"{prefix}__" if prefix else ""
        
        if self.filters.get("currency_id"):
            queryset = queryset.filter(**{f"{pfx}currency_id": self.filters.get("currency_id")})
        
        if self.filters.get("user_id"):
            user_field = f"{pfx}user_id" if prefix != "customer" else "customer_id"
            if prefix == "wallet": user_field = "wallet__user_id"
            if prefix == "": user_field = "user_id" # Defaults
            
            # Special case for Order
            if hasattr(queryset.model, 'customer'): user_field = "customer_id"
            
            queryset = queryset.filter(**{user_field: self.filters.get("user_id")})
            
        if self.filters.get("tier"):
            user_field = f"{pfx}user__tier" if prefix != "customer" else "customer__tier"
            if prefix == "wallet": user_field = "wallet__user__tier"
            if prefix == "": user_field = "user__tier"
            
            if hasattr(queryset.model, 'customer'): user_field = "customer__tier"
                
            queryset = queryset.filter(**{user_field: self.filters.get("tier")})
            
        return queryset

    def get_dashboard_kpis(self):
        # 1. Total Deposits
        deposits_qs = DepositRequest.objects.filter(status=DepositRequest.Status.COMPLETED)
        deposits_qs = self._apply_date_filter(deposits_qs, "reviewed_at")
        deposits_qs = self._apply_common_filters(deposits_qs)
        if self.filters.get("payment_method_id"):
            deposits_qs = deposits_qs.filter(payment_method_id=self.filters.get("payment_method_id"))
            
        total_deposits = deposits_qs.aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
        total_deposit_fees = deposits_qs.aggregate(total=Sum('fee_amount'))['total'] or Decimal("0.00")

        # 2. Total Withdrawals
        withdrawals_qs = WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.COMPLETED)
        withdrawals_qs = self._apply_date_filter(withdrawals_qs, "reviewed_at")
        withdrawals_qs = self._apply_common_filters(withdrawals_qs)
        if self.filters.get("payment_method_id"):
            withdrawals_qs = withdrawals_qs.filter(payment_method_id=self.filters.get("payment_method_id"))
            
        total_withdrawals = withdrawals_qs.aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
        total_withdrawal_fees = withdrawals_qs.aggregate(total=Sum('fee_amount'))['total'] or Decimal("0.00")

        # 3. Product Sales & Profit
        orders_qs = Order.objects.exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
        orders_qs = self._apply_date_filter(orders_qs)
        orders_qs = self._apply_common_filters(orders_qs, prefix="customer")
        
        # Note: In multi-currency, summing total_amount directly might be inaccurate if orders are in different currencies.
        # However, orders are usually priced in USD base and converted for display, or priced in base.
        # Assuming order.total_amount is in USD or base currency.
        product_revenue = orders_qs.aggregate(total=Sum('total_amount'))['total'] or Decimal("0.00")
        
        # Calculate cost
        order_items = OrderItem.objects.filter(order__in=orders_qs)
        total_cost = order_items.annotate(
            total_item_cost=ExpressionWrapper(F('variant__cost') * F('quantity'), output_field=DecimalField())
        ).aggregate(total=Sum('total_item_cost'))['total'] or Decimal("0.00")
        
        product_net_profit = product_revenue - total_cost

        # 4. Exchange Profit/Loss
        # This requires comparing the deposit's base currency value vs the payment method's capital_exchange_rate
        # For a simplified MVP, if capital rate is provided:
        # Profit = (amount_in_fiat / capital_rate) - amount_in_usd
        exchange_profit = Decimal("0.00")
        if not self.filters.get("payment_method_id"):
            # Aggregate across all
            for pm in PaymentMethod.objects.all():
                pm_deposits = deposits_qs.filter(payment_method=pm)
                if pm_deposits.exists():
                    # Assuming deposit.amount is fiat, we need its USD equivalent based on capital_exchange_rate
                    # Actually, if deposit.amount is what user inputs, and deposit.wallet_amount is what they get.
                    # We need to know the currency.
                    pass # Complex logic to be implemented below in detailed method

        # 5. Debts
        wallets_qs = Wallet.objects.all()
        if self.filters.get("user_id"): wallets_qs = wallets_qs.filter(user_id=self.filters.get("user_id"))
        if self.filters.get("tier"): wallets_qs = wallets_qs.filter(user__tier=self.filters.get("tier"))
        
        total_outstanding_debt = wallets_qs.aggregate(total=Sum('debt_balance'))['total'] or Decimal("0.00")
        
        # Collected debt (LedgerEntry DEBT_PAYMENT)
        debt_payments = LedgerEntry.objects.filter(entry_type=LedgerEntry.EntryType.DEBT_PAYMENT)
        debt_payments = self._apply_date_filter(debt_payments)
        debt_payments = self._apply_common_filters(debt_payments, prefix="wallet")
        total_collected_debt = debt_payments.aggregate(total=Sum('amount'))['total'] or Decimal("0.00")

        # 6. Coupons
        coupons_qs = Order.objects.filter(coupon__isnull=False).exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
        coupons_qs = self._apply_date_filter(coupons_qs)
        coupons_qs = self._apply_common_filters(coupons_qs, prefix="customer")
        
        # original_total - total_amount = discount
        coupon_losses = coupons_qs.annotate(
            discount=ExpressionWrapper(F('original_total') - F('total_amount'), output_field=DecimalField())
        ).aggregate(total=Sum('discount'))['total'] or Decimal("0.00")

        return {
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "net_cashflow": total_deposits - total_withdrawals,
            "total_fees_earned": total_deposit_fees + total_withdrawal_fees,
            "product_revenue": product_revenue,
            "product_net_profit": product_net_profit,
            "total_outstanding_debt": total_outstanding_debt,
            "total_collected_debt": total_collected_debt,
            "coupon_losses": coupon_losses,
            "pending_deposits_count": DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).count(),
            "pending_withdrawals_count": WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PENDING).count(),
        }

    def get_payment_method_performance(self):
        methods = PaymentMethod.objects.all()
        if self.filters.get("payment_method_id"):
            methods = methods.filter(id=self.filters.get("payment_method_id"))
            
        results = []
        for pm in methods:
            deposits = DepositRequest.objects.filter(payment_method=pm, status=DepositRequest.Status.COMPLETED)
            deposits = self._apply_date_filter(deposits, "reviewed_at")
            deposits = self._apply_common_filters(deposits)
            
            withdrawals = WithdrawalRequest.objects.filter(payment_method=pm, status=WithdrawalRequest.Status.COMPLETED)
            withdrawals = self._apply_date_filter(withdrawals, "reviewed_at")
            withdrawals = self._apply_common_filters(withdrawals)
            
            dep_vol = deposits.aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
            dep_fees = deposits.aggregate(total=Sum('fee_amount'))['total'] or Decimal("0.00")
            
            with_vol = withdrawals.aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
            with_fees = withdrawals.aggregate(total=Sum('fee_amount'))['total'] or Decimal("0.00")
            
            # Exchange Profit Calculation
            # Deposit Amount * (System Rate - Capital Rate)
            # This is a simplified estimation. A real system would log this per transaction.
            exchange_revenue = Decimal("0.00")
            
            results.append({
                "id": str(pm.id),
                "name": pm.name,
                "type": pm.method_type,
                "deposits_volume": dep_vol,
                "withdrawals_volume": with_vol,
                "net_movement": dep_vol - with_vol,
                "fees_generated": dep_fees + with_fees,
                "capital_rate": pm.capital_exchange_rate,
                "exchange_revenue": exchange_revenue
            })
        return results

    def get_pnl_statement(self):
        kpis = self.get_dashboard_kpis()
        
        # Fetch Refunds
        refunds_qs = LedgerEntry.objects.filter(description__icontains="Refund")
        refunds_qs = self._apply_date_filter(refunds_qs)
        refunds_qs = self._apply_common_filters(refunds_qs, prefix="wallet")
        total_refunds = refunds_qs.aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
        
        # Manual Adjustments (Credits/Debits by Admin)
        manual_credits = LedgerEntry.objects.filter(entry_type=LedgerEntry.EntryType.CREDIT, source="admin").aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
        manual_debits = LedgerEntry.objects.filter(entry_type=LedgerEntry.EntryType.DEBIT, source="admin").aggregate(total=Sum('amount'))['total'] or Decimal("0.00")

        gross_profit = kpis["product_net_profit"] + kpis["total_fees_earned"] # + exchange profit
        total_losses = kpis["coupon_losses"] + total_refunds # + debt write-offs
        
        net_profit = gross_profit - total_losses

        return {
            "revenue": {
                "product_profit": kpis["product_net_profit"],
                "deposit_fees": DepositRequest.objects.filter(status=DepositRequest.Status.COMPLETED).aggregate(total=Sum('fee_amount'))['total'] or Decimal("0.00"),
                "withdrawal_fees": WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.COMPLETED).aggregate(total=Sum('fee_amount'))['total'] or Decimal("0.00"),
                "exchange_spread": Decimal("0.00"), # TBD
            },
            "losses": {
                "coupons": kpis["coupon_losses"],
                "refunds": total_refunds,
                "manual_adjustments_net": manual_credits - manual_debits
            },
            "gross_profit": gross_profit,
            "net_profit": net_profit
        }

    def get_treasury_status(self):
        # Aggregate across all wallets
        wallets = Wallet.objects.all()
        if self.filters.get("currency_id"):
            wallets = wallets.filter(currency_id=self.filters.get("currency_id"))
            
        stats = wallets.aggregate(
            total_available=Sum('available_balance'),
            total_pending=Sum('pending_balance'),
            total_frozen=Sum('frozen_balance'),
            total_held=Sum('held_balance'),
            total_reserved=Sum('reserved_balance'),
            total_debt=Sum('debt_balance')
        )
        
        # Replace Nones with 0
        for k, v in stats.items():
            if v is None: stats[k] = Decimal("0.00")
            
        stats['total_liabilities'] = stats['total_available'] + stats['total_frozen'] + stats['total_held'] + stats['total_reserved']
        
        return stats
