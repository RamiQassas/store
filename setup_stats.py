import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.common.models import PlatformStatistic

PlatformStatistic.objects.all().delete()

PlatformStatistic.objects.create(label='عميل موثق ومسجل', stat_type='users', value_override=1500, value_suffix='+', icon_class='fas fa-user-check', display_order=1)
PlatformStatistic.objects.create(label='طلب مكتمل على المنصة', stat_type='orders', value_override=3000, value_suffix='+', icon_class='fas fa-server', display_order=2)
PlatformStatistic.objects.create(label='دعم ومتابعة فنية', stat_type='custom', string_value='24/7', icon_class='fas fa-microchip', display_order=3)
PlatformStatistic.objects.create(label='تنفيذ آلي وسريع', stat_type='execution_time', value_override=10, value_suffix=' دقيقة', icon_class='fas fa-bolt-lightning', display_order=4)
