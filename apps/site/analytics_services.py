import json
from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Sum, Count, F, Q, ExpressionWrapper, DecimalField, Avg
from django.utils import timezone
from django.db.models.functions import TruncDate

from apps.accounts.models import User
from apps.orders.models import Order, OrderItem, Coupon
from apps.payments.models import DepositRequest, WithdrawalRequest, PaymentMethod
from apps.wallets.models import Wallet, LedgerEntry, WalletTransaction
from apps.common.models import Currency

class FinancialAnalyticsService:
    def __init__(self, filters=None):
        self.filters = filters or {}
        # Expected filters: start_date, end_date, currency_id, payment_method_id, tier, user_id, status_filter, reporting_currency_code
        self.reporting_currency = Currency.objects.filter(code=self.filters.get("reporting_currency_code", "USD")).first() or Currency.objects.filter(is_default=True).first()
        self._cache = {}

    def _normalize(self, amount, from_currency, operation="deposit"):
        """Normalizes an amount to the reporting currency."""
        if not amount or amount == 0: return Decimal("0.00")
        if not from_currency: return Decimal(str(amount))
        
        # Convert to Base (USD)
        base_amt = from_currency.to_base(amount, operation=operation)
        
        # Convert from Base to Reporting Currency
        if self.reporting_currency.code == "USD":
            return base_amt
            
        return self.reporting_currency.from_base(base_amt, operation=operation)

    def _apply_date_filter(self, queryset, date_field="created_at"):
        start_date_str = self.filters.get("start_date")
        end_date_str = self.filters.get("end_date")
        date_preset = self.filters.get("date_preset", "all")
        
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
        elif date_preset == "custom":
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
        
        if self.filters.get("payment_method_id"):
            if hasattr(queryset.model, 'payment_method'):
                queryset = queryset.filter(**{f"{pfx}payment_method_id": self.filters.get("payment_method_id")})
        
        if self.filters.get("user_id"):
            user_field = f"{pfx}user_id" if prefix != "customer" else "customer_id"
            if prefix == "wallet": user_field = "wallet__user_id"
            if prefix == "": user_field = "user_id"
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
        # 1. Deposits
        dep_qs = DepositRequest.objects.all()
        if not self.filters.get("include_pending"):
            dep_qs = dep_qs.filter(status__in=[DepositRequest.Status.APPROVED, DepositRequest.Status.COMPLETED])
        
        dep_qs = self._apply_date_filter(dep_qs)
        dep_qs = self._apply_common_filters(dep_qs)
        
        total_deposits = Decimal("0.00")
        total_dep_fees = Decimal("0.00")
        for d in dep_qs.select_related('currency'):
            total_deposits += self._normalize(d.amount, d.currency)
            total_dep_fees += self._normalize(d.fee_amount, d.currency)

        # 2. Withdrawals
        with_qs = WithdrawalRequest.objects.all()
        if not self.filters.get("include_pending"):
            with_qs = with_qs.filter(status__in=[WithdrawalRequest.Status.APPROVED, WithdrawalRequest.Status.COMPLETED])
        
        with_qs = self._apply_date_filter(with_qs)
        with_qs = self._apply_common_filters(with_qs)
        
        total_withdrawals = Decimal("0.00")
        total_with_fees = Decimal("0.00")
        for w in with_qs.select_related('currency'):
            total_withdrawals += self._normalize(w.amount, w.currency, operation="withdraw")
            total_with_fees += self._normalize(w.fee_amount, w.currency, operation="withdraw")

        # 3. Orders & Product Profit
        orders_qs = Order.objects.exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
        orders_qs = self._apply_date_filter(orders_qs)
        orders_qs = self._apply_common_filters(orders_qs, prefix="customer")
        
        product_revenue = Decimal("0.00")
        product_cost = Decimal("0.00")
        coupon_discounts = Decimal("0.00")
        
        for o in orders_qs.prefetch_related('items__variant'):
            total_amt = o.total_amount or Decimal("0.00")
            product_revenue += total_amt
            
            # Calculate Coupon/Adjustment Discount
            orig_total = o.original_total
            if orig_total is not None:
                if orig_total > total_amt:
                    coupon_discounts += (orig_total - total_amt)
            
            for item in o.items.all():
                if item.variant and item.variant.cost is not None:
                    product_cost += (item.variant.cost * (item.quantity or 1))

        # 4. Debts & Collections
        wallets_qs = Wallet.objects.all()
        wallets_qs = self._apply_common_filters(wallets_qs, prefix="")
        total_liabilities = wallets_qs.aggregate(total=Sum('available_balance'))['total'] or Decimal("0.00")
        total_outstanding_debt = wallets_qs.aggregate(total=Sum('debt_balance'))['total'] or Decimal("0.00")

        # 5. Cash Collections (from LedgerEntry source='admin_cash')
        cash_qs = LedgerEntry.objects.filter(source="admin_cash", entry_type=LedgerEntry.EntryType.DEBT_PAYMENT)
        cash_qs = self._apply_date_filter(cash_qs)
        cash_qs = self._apply_common_filters(cash_qs, prefix="wallet")
        
        total_cash_collections = Decimal("0.00")
        for log in cash_qs.select_related('wallet__currency'):
            # Convert to reporting currency. Note: log.amount is in wallet currency.
            total_cash_collections += self._normalize(log.amount, log.wallet.currency)

        return {
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "net_cashflow": total_deposits - total_withdrawals,
            "total_fees_earned": total_dep_fees + total_with_fees,
            "product_revenue": product_revenue,
            "product_net_profit": product_revenue - product_cost - coupon_discounts,
            "total_outstanding_debt": total_outstanding_debt,
            "total_liabilities": total_liabilities,
            "total_cash_collections": total_cash_collections,
            "coupon_losses": coupon_discounts,
            "reporting_currency": self.reporting_currency.code
        }

    def get_pnl_statement(self):
        kpis = self.get_dashboard_kpis()
        
        # Refunds (from LedgerEntry)
        refunds_qs = LedgerEntry.objects.filter(description__icontains="Refund")
        refunds_qs = self._apply_date_filter(refunds_qs)
        refunds_qs = self._apply_common_filters(refunds_qs, prefix="wallet")
        total_refunds = refunds_qs.aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
        
        # FX Profit
        fx_stats = self.get_fx_profit_report()
        
        net_profit = kpis["product_net_profit"] + kpis["total_fees_earned"] + fx_stats["net_fx_profit"] - total_refunds
        
        return {
            "revenue": {
                "product_profit": kpis["product_net_profit"],
                "deposit_fees": kpis["total_fees_earned"] * Decimal("0.6"), # Estimated breakdown if not tracked separately
                "withdrawal_fees": kpis["total_fees_earned"] * Decimal("0.4"),
                "fx_profit": fx_stats["net_fx_profit"],
            },
            "losses": {
                "coupons": kpis["coupon_losses"],
                "refunds": total_refunds,
            },
            "net_profit": net_profit
        }

    def get_treasury_status(self):
        # Aggregate across all wallets
        wallets = Wallet.objects.all()
        wallets = self._apply_common_filters(wallets, prefix="")
            
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

    def get_fx_profit_report(self):
        """Calculates FX profit based on capital rates."""
        pm_stats = self.get_payment_method_performance()
        total_fx_profit = sum(item["exchange_revenue"] for item in pm_stats)
        return {
            "net_fx_profit": total_fx_profit,
            "details": pm_stats
        }

    def get_payment_method_performance(self):
        methods = PaymentMethod.objects.all()
        if self.filters.get("payment_method_id"):
            methods = methods.filter(id=self.filters.get("payment_method_id"))
            
        results = []
        for pm in methods:
            # Group by currency for this payment method
            pm_currencies = pm.supported_currencies.all()
            if not pm_currencies.exists():
                pm_currencies = Currency.objects.filter(is_active=True)

            currency_details = []
            pm_total_fx_profit = Decimal("0.00")
            
            for curr in pm_currencies:
                # Deposits for this PM + Currency
                deps = DepositRequest.objects.filter(payment_method=pm, currency=curr, status=DepositRequest.Status.COMPLETED)
                deps = self._apply_date_filter(deps)
                deps = self._apply_common_filters(deps)
                
                # Withdrawals for this PM + Currency
                withs = WithdrawalRequest.objects.filter(payment_method=pm, currency=curr, status=WithdrawalRequest.Status.COMPLETED)
                withs = self._apply_date_filter(withs)
                withs = self._apply_common_filters(withs)
                
                dep_vol_raw = deps.aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
                dep_fees_raw = deps.aggregate(total=Sum('fee_amount'))['total'] or Decimal("0.00")
                with_vol_raw = withs.aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
                
                # FX Logic using the new Currency.capital_rate
                market_buy_rate = curr.buy_rate
                market_sell_rate = curr.sell_rate
                
                # Use Currency capital_rate, fallback to PM capital rate if PM rate is NOT 1.0
                cap_rate = curr.capital_rate
                if cap_rate == Decimal("1.000000") and pm.capital_exchange_rate != Decimal("1.000000"):
                    cap_rate = pm.capital_exchange_rate
                
                # Fallback to spread if no capital rate configured
                if cap_rate == Decimal("1.000000"):
                    cap_rate_buy = market_sell_rate
                    cap_rate_sell = market_buy_rate
                else:
                    cap_rate_buy = cap_rate
                    cap_rate_sell = cap_rate

                curr_fx_profit = Decimal("0.00")
                
                # FX for Deposits
                if dep_vol_raw > 0:
                    base_val = curr.to_base(dep_vol_raw, operation="deposit")
                    if curr.conversion_method == Currency.ConversionMethod.DIVIDE:
                        cost_val = dep_vol_raw * cap_rate_buy
                    else:
                        cost_val = dep_vol_raw / cap_rate_buy
                    curr_fx_profit += (cost_val - base_val)
                
                # FX for Withdrawals
                if with_vol_raw > 0:
                    base_val = curr.to_base(with_vol_raw, operation="withdraw")
                    if curr.conversion_method == Currency.ConversionMethod.DIVIDE:
                        cost_val = with_vol_raw * cap_rate_sell
                    else:
                        cost_val = with_vol_raw / cap_rate_sell
                    curr_fx_profit += (base_val - cost_val)

                pm_total_fx_profit += curr_fx_profit
                
                currency_details.append({
                    "currency_code": curr.code,
                    "deposits_raw": dep_vol_raw,
                    "withdrawals_raw": with_vol_raw,
                    "fees_raw": dep_fees_raw,
                    "net_raw": dep_vol_raw - with_vol_raw,
                    "fx_profit_usd": curr_fx_profit
                })

            # Main PM aggregates (normalized)
            dep_vol_norm = sum(self._normalize(c['deposits_raw'], Currency.objects.get(code=c['currency_code'])) for c in currency_details)
            with_vol_norm = sum(self._normalize(c['withdrawals_raw'], Currency.objects.get(code=c['currency_code']), operation="withdraw") for c in currency_details)
            
            results.append({
                "name": pm.name,
                "deposits_volume": dep_vol_norm,
                "withdrawals_volume": with_vol_norm,
                "net_movement": dep_vol_norm - with_vol_norm,
                "exchange_revenue": pm_total_fx_profit,
                "currencies": currency_details,
                "real_balance": dep_vol_norm - with_vol_norm # Estimate
            })
        return results


    def get_debt_aging(self):
        now = timezone.now()
        wallets = Wallet.objects.filter(debt_balance__gt=0)
        wallets = self._apply_common_filters(wallets, prefix="")
        
        aging = {
            "1-7": {"count": 0, "amount": Decimal("0.00")},
            "8-30": {"count": 0, "amount": Decimal("0.00")},
            "31-90": {"count": 0, "amount": Decimal("0.00")},
            "90+": {"count": 0, "amount": Decimal("0.00")},
        }
        
        for w in wallets:
            # Find the oldest unpaid debt entry
            oldest_debt = LedgerEntry.objects.filter(wallet=w, entry_type=LedgerEntry.EntryType.DEBT).order_by('created_at').first()
            if oldest_debt:
                days = (now - oldest_debt.created_at).days
                if days <= 7: key = "1-7"
                elif days <= 30: key = "8-30"
                elif days <= 90: key = "31-90"
                else: key = "90+"
                
                aging[key]["count"] += 1
                aging[key]["amount"] += w.debt_balance
                
        return aging

    def get_cash_collection_logs(self):
        """Returns detailed logs for cash collections."""
        cash_qs = LedgerEntry.objects.filter(source="admin_cash", entry_type=LedgerEntry.EntryType.DEBT_PAYMENT)
        cash_qs = self._apply_date_filter(cash_qs)
        cash_qs = self._apply_common_filters(cash_qs, prefix="wallet")
        return cash_qs.select_related('wallet__user', 'wallet__currency', 'created_by').order_by('-created_at')

    def get_trends(self):
        # Last 30 days trends
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=29)
        
        deps = DepositRequest.objects.filter(status=DepositRequest.Status.COMPLETED, reviewed_at__date__range=[start_date, end_date])
        withs = WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.COMPLETED, reviewed_at__date__range=[start_date, end_date])
        
        dep_trend = deps.annotate(date=TruncDate('reviewed_at')).values('date').annotate(total=Sum('amount')).order_by('date')
        with_trend = withs.annotate(date=TruncDate('reviewed_at')).values('date').annotate(total=Sum('amount')).order_by('date')
        
        # Map to dict for easy access
        dep_data = {item['date'].isoformat(): float(item['total']) for item in dep_trend}
        with_data = {item['date'].isoformat(): float(item['total']) for item in with_trend}
        
        labels = []
        dep_series = []
        with_series = []
        
        curr = start_date
        while curr <= end_date:
            d_str = curr.isoformat()
            labels.append(d_str)
            dep_series.append(dep_data.get(d_str, 0))
            with_series.append(with_data.get(d_str, 0))
            curr += timedelta(days=1)
            
        return {
            "labels": labels,
            "deposits": dep_series,
            "withdrawals": with_series
        }
