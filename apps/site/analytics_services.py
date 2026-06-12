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

        # 4. Debts
        wallets_qs = Wallet.objects.all()
        wallets_qs = self._apply_common_filters(wallets_qs, prefix="")
        total_liabilities = wallets_qs.aggregate(total=Sum('available_balance'))['total'] or Decimal("0.00")
        total_outstanding_debt = wallets_qs.aggregate(total=Sum('debt_balance'))['total'] or Decimal("0.00")

        return {
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "net_cashflow": total_deposits - total_withdrawals,
            "total_fees_earned": total_dep_fees + total_with_fees,
            "product_revenue": product_revenue,
            "product_net_profit": product_revenue - product_cost - coupon_discounts,
            "total_outstanding_debt": total_outstanding_debt,
            "total_liabilities": total_liabilities,
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
            # Deposits
            deps = DepositRequest.objects.filter(payment_method=pm, status=DepositRequest.Status.COMPLETED)
            deps = self._apply_date_filter(deps)
            deps = self._apply_common_filters(deps)
            
            # Withdrawals
            withs = WithdrawalRequest.objects.filter(payment_method=pm, status=WithdrawalRequest.Status.COMPLETED)
            withs = self._apply_date_filter(withs)
            withs = self._apply_common_filters(withs)
            
            dep_vol = Decimal("0.00")
            dep_fees = Decimal("0.00")
            fx_profit = Decimal("0.00")
            
            for d in deps.select_related('currency'):
                val_norm = self._normalize(d.amount, d.currency)
                dep_vol += val_norm
                dep_fees += self._normalize(d.fee_amount, d.currency)
                
                # FX Logic: (Base Amount - Capital Cost)
                # If capital rate is 1.0, profit is 0.
                # If capital rate is 36.5 (local per 1 USD) and we get 1 USD.
                # Profit = Amount_in_Base * (1 - (SystemRate/CapitalRate))? No.
                # Let's use simple logic: Cost = Amount_in_Local / CapitalRate.
                # Profit = Amount_in_Base - Cost.
                # FX Logic: (Market_Base_Value - Capital_Cost_Base_Value)
                cap_rate = pm.capital_exchange_rate or Decimal("1.000000")
                if cap_rate > 0:
                    base_val = d.currency.to_base(d.amount or 0)
                    # Profit = Local_Amount * ( (1/Market_Rate) - (1/Capital_Rate) )
                    # Since Currency.to_base handles (Local / Rate) or (Local * Rate), we mirror that.
                    if d.currency.conversion_method == Currency.ConversionMethod.DIVIDE:
                        # base = local / market_rate -> market_rate = local / base
                        # cost = local / cap_rate
                        # profit = base - cost
                        cost = (d.amount or 0) / cap_rate
                        fx_profit += (base_val - cost)
                    else:
                        # base = local * market_rate
                        # cost = local * cap_rate
                        # profit = base - cost
                        cost = (d.amount or 0) * cap_rate
                        fx_profit += (base_val - cost)
                
            with_vol = Decimal("0.00")
            for w in withs.select_related('currency'):
                with_vol += self._normalize(w.amount, w.currency, operation="withdraw")

            # Real Balance Tracking
            # This is hard without a full ledger per payment method, so we estimate from completed trans
            real_balance = dep_vol - with_vol # + opening balance (if we had it)
            
            results.append({
                "name": pm.name,
                "deposits_volume": dep_vol,
                "withdrawals_volume": with_vol,
                "net_movement": dep_vol - with_vol,
                "fees_generated": dep_fees,
                "capital_rate": pm.capital_exchange_rate,
                "exchange_revenue": fx_profit,
                "real_balance": real_balance
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
