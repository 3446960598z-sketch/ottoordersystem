from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from .models import Order, Notification

@receiver(post_save, sender=Order)
def order_status_changed_handler(sender, instance, created, **kwargs):
    """
    监听Order模型保存后的信号，根据状态变化发送通知。
    """
    order = instance
    
    # 如果是新创建的订单(状态为PENDING)，通常不需要立即通知
    if created:
        return

    # 优化：仅当'status'字段被更新时，或无法确定更新字段时，才继续
    update_fields = kwargs.get('update_fields')
    if update_fields and 'status' not in update_fields:
        return

    # --- 定义不同角色的通知 ---
    
    # 1. 通知顾客
    customer_message = None
    if order.status == 'PAID':
        customer_message = f"您的订单 #{order.pk} 已支付成功，商家正在备货。"
    elif order.status == 'PREPARING':
        customer_message = f"商家已接单，您的订单 #{order.pk} 正在备货中。"
    elif order.status == 'READY_FOR_PICKUP':
        customer_message = f"您的订单 #{order.pk} 已备货完成，等待骑手取货。"
    elif order.status == 'DELIVERING':
        customer_message = f"骑手已取货，您的订单 #{order.pk} 正在飞速向您奔来！"
    elif order.status == 'DELIVERED':
        customer_message = f"您的订单 #{order.pk} 已送达，欢迎再次光临！"
    elif order.status == 'CANCELLED':
        customer_message = f"很遗憾，您的订单 #{order.pk} 已被取消。"

    if customer_message:
        Notification.objects.create(
            recipient=order.user,
            message=customer_message,
            link=reverse('shop:order_detail', kwargs={'pk': order.pk})
        )

    # 2. 通知商家
    merchant_message = None
    if order.status == 'PAID':
        merchant_message = f"您有新的待处理订单 #{order.pk}，请尽快备货。"
    
    if merchant_message and order.shop.account:
        Notification.objects.create(
            recipient=order.shop.account,
            message=merchant_message,
            link=reverse('shop:order_detail', kwargs={'pk': order.pk})
        )

    # 3. 通知骑手 (如果订单分配了骑手)
    rider_message = None
    # 注意：这里我们假设骑手是在接单时（accept_order视图）被分配的，
    # 那个时刻订单状态会从 PAID 变为 DELIVERING。
    # 如果有其他状态需要通知骑手，也可以在这里添加。
    
    # 示例：如果订单被设置为“待取货”，可以通知所有骑手（实现较为复杂，暂不添加）
    # 示例：如果订单被取消，而已有骑手接单，则通知骑手
    if order.status == 'CANCELLED' and order.rider:
        rider_message = f"订单 #{order.pk} 已被取消，您无需再进行配送。"
        
    if rider_message and order.rider:
        Notification.objects.create(
            recipient=order.rider.user,
            message=rider_message,
            link=reverse('shop:order_detail', kwargs={'pk': order.pk})
        )
