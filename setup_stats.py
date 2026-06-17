import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.common.models import PlatformStatistic

PlatformStatistic.objects.get_or_create(label='مستخدم نشط', stat_type='users', defaults={'icon_class': 'fas fa-users', 'value_override': 1500, 'display_order': 1})
PlatformStatistic.objects.get_or_create(label='طلب مكتمل', stat_type='orders', defaults={'icon_class': 'fas fa-receipt', 'value_override': 3000, 'display_order': 2})
PlatformStatistic.objects.get_or_create(label='عملية إيداع ناجحة', stat_type='deposits', defaults={'icon_class': 'fas fa-wallet', 'value_override': 500, 'display_order': 3})
PlatformStatistic.objects.get_or_create(label='طلبات سحب مكتملة', stat_type='withdrawals', defaults={'icon_class': 'fas fa-money-bill-wave', 'value_override': 100, 'display_order': 4})
PlatformStatistic.objects.get_or_create(label='تنفيذ سريع', stat_type='execution_time', defaults={'icon_class': 'fas fa-stopwatch', 'value_override': 15, 'display_order': 5})
