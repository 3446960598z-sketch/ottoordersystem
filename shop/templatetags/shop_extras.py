from django import template
from django.utils import timezone
from datetime import timedelta

register = template.Library()

@register.filter
def mul(value, arg):
    """返回 value * arg（适用于数字/Decimal）"""
    try:
        return value * arg
    except Exception:
        try:
            return float(value) * float(arg)
        except Exception:
            return ''

@register.filter
def is_new_shop(shop, days=7):
    """检查店铺是否在指定天数内创建"""
    if not shop.created_at:
        return False
    return timezone.now() - shop.created_at < timedelta(days=days)
