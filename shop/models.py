from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError

# ===== 店铺与商品 =====
class Shop(models.Model):
    name = models.CharField('店铺名称', max_length=255)
    description = models.TextField('店铺描述', blank=True)
    image = models.ImageField('店铺图片', upload_to='shops/', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    account = models.OneToOneField(User, on_delete=models.CASCADE, related_name='shop_account', verbose_name='店铺后台账号', null=True, blank=True)
    rating_avg = models.DecimalField('平均评分', max_digits=3, decimal_places=2, default=0.00)
    rating_count = models.PositiveIntegerField('评分总数', default=0)

    class Meta:
        verbose_name = '店铺'
        verbose_name_plural = '店铺'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('shop:shop_detail', args=[self.pk])

class ProductCategory(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='categories', verbose_name='店铺')
    name = models.CharField('分类名称', max_length=100)
    description = models.TextField('分类描述', blank=True)

    class Meta:
        verbose_name = '商品分类'
        verbose_name_plural = '商品分类'
        unique_together = ('shop', 'name')

    def __str__(self):
        return f'{self.shop.name} - {self.name}'

class Product(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, related_name='products', verbose_name='商品分类', null=True, blank=True)
    name = models.CharField('名称', max_length=255)
    sku = models.CharField('SKU', max_length=64, unique=True)
    price = models.DecimalField('价格', max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField('库存', default=0)
    description = models.TextField('描述', blank=True)
    image = models.ImageField('图片', upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField('上架', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '商品'
        verbose_name_plural = '商品'

    def __str__(self):
        return f'{self.name} ({self.sku})'

    def get_absolute_url(self):
        return reverse('shop:product_detail', args=[self.pk])

# ===== 平台管理 =====
class Banner(models.Model):
    title = models.CharField('横幅标题', max_length=100, help_text="仅用于后台识别", default='默认标题')
    image = models.ImageField('图片', upload_to='banners/')
    linked_shop = models.ForeignKey(Shop, on_delete=models.CASCADE, verbose_name='跳转店铺', null=True, blank=True, help_text="选择一个店铺，将优先于商品链接")
    linked_product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='跳转商品', null=True, blank=True, help_text="选择一个商品")
    is_active = models.BooleanField('是否激活', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '广告横幅'
        verbose_name_plural = '广告横幅'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def clean(self):
        if self.linked_shop and self.linked_product:
            raise ValidationError("不能同时选择店铺和商品作为跳转链接，请只选择一个。")
        if not self.linked_shop and not self.linked_product:
            raise ValidationError("必须选择一个店铺或商品作为跳转链接。")

    def get_link_url(self):
        if self.linked_shop:
            return self.linked_shop.get_absolute_url()
        if self.linked_product:
            return self.linked_product.get_absolute_url()
        return "#"

class Coupon(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='coupons', verbose_name='所属店铺')
    code = models.CharField('优惠码', max_length=50, unique=True)
    discount_amount = models.DecimalField('抵扣金额', max_digits=10, decimal_places=2)
    min_purchase_amount = models.DecimalField('最低消费金额', max_digits=10, decimal_places=2, default=0.00)
    valid_from = models.DateTimeField('生效时间')
    valid_to = models.DateTimeField('失效时间')
    is_active = models.BooleanField('是否激活', default=True)

    class Meta:
        verbose_name = '优惠券'
        verbose_name_plural = '优惠券'

    def __str__(self):
        return self.code

# ===== 用户相关 =====
class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses', verbose_name='用户')
    address_line_1 = models.CharField('地址行1', max_length=255)
    address_line_2 = models.CharField('地址行2', max_length=255, blank=True)
    city = models.CharField('城市', max_length=100)
    postal_code = models.CharField('邮政编码', max_length=20)
    contact_name = models.CharField('联系人', max_length=100)
    contact_phone = models.CharField('联系电话', max_length=20)
    is_default = models.BooleanField('是否默认', default=False)

    class Meta:
        verbose_name = '收货地址'
        verbose_name_plural = '收货地址'
        ordering = ['-is_default']

    def __str__(self):
        return f'{self.user.username} - {self.address_line_1}'

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    ai_tokens_used = models.PositiveIntegerField('今日AI-Tokens消耗', default=0)
    last_token_reset_date = models.DateField('最后Token重置日期', default=timezone.now)

    def __str__(self):
        return f'{self.user.username} 的资料'

    def reset_tokens_if_needed(self):
        today = timezone.now().date()
        if self.last_token_reset_date < today:
            self.ai_tokens_used = 0
            self.last_token_reset_date = today
            self.save()

class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites', verbose_name='用户')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='favorited_by', verbose_name='商品')
    created_at = models.DateTimeField('收藏时间', auto_now_add=True)

    class Meta:
        verbose_name = '收藏'
        verbose_name_plural = '收藏'
        unique_together = ('user', 'product')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} 收藏了 {self.product.name}'

class Rider(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='rider_profile', verbose_name='用户')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '外卖员'
        verbose_name_plural = '外卖员'

    def __str__(self):
        return f"外卖员: {self.user.username}"

# ===== 订单与评价 =====
class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '未支付'),
        ('PAID', '已支付'),
        ('PREPARING', '备货中'),
        ('READY_FOR_PICKUP', '待取货'),
        ('DELIVERING', '配送中'),
        ('DELIVERED', '已送达'),
        ('CANCELLED', '已取消'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='orders', verbose_name='店铺')
    rider = models.ForeignKey(Rider, on_delete=models.SET_NULL, related_name='orders', verbose_name='外卖员', null=True, blank=True)
    shipping_address = models.ForeignKey(Address, on_delete=models.SET_NULL, verbose_name='收货地址', null=True, blank=True)
    
    subtotal = models.DecimalField('商品总价', max_digits=12, decimal_places=2)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, related_name='orders', verbose_name='使用的优惠券', null=True, blank=True)
    discount = models.DecimalField('优惠金额', max_digits=12, decimal_places=2, default=0.00)
    delivery_fee = models.DecimalField('配送费', max_digits=10, decimal_places=2, default=1.00)
    total = models.DecimalField('订单总额', max_digits=12, decimal_places=2)

    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    paid_at = models.DateTimeField('支付时间', null=True, blank=True)
    accepted_at = models.DateTimeField('接单时间', null=True, blank=True)
    delivered_at = models.DateTimeField('送达时间', null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '订单'
        verbose_name_plural = '订单'

    def __str__(self):
        return f"Order#{self.pk} ({self.user.username})"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name='商品')
    quantity = models.PositiveIntegerField('数量', default=1)

    def __str__(self):
        return f"Order#{self.order.pk}: {self.product.name} x {self.quantity}"

class Review(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='review', verbose_name='订单')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews', verbose_name='用户')
    rating = models.IntegerField('评分', validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField('评论', blank=True)
    created_at = models.DateTimeField('评论时间', auto_now_add=True)

    class Meta:
        verbose_name = '订单评价'
        verbose_name_plural = '订单评价'
        unique_together = ('order', 'user')

# ===== 客服工单 =====
class SupportTicket(models.Model):
    STATUS_CHOICES = [
        ('OPEN', '待处理'),
        ('IN_PROGRESS', '处理中'),
        ('CLOSED', '已关闭'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_tickets', verbose_name='用户')
    subject = models.CharField('主题', max_length=255)
    description = models.TextField('问题描述')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '客服工单'
        verbose_name_plural = '客服工单'
        ordering = ['-created_at']

    def __str__(self):
        return f'工单 #{self.pk} - {self.subject}'

class TicketMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='messages', verbose_name='工单')
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='回复人')
    message = models.TextField('消息内容')
    created_at = models.DateTimeField('回复时间', auto_now_add=True)

    class Meta:
        verbose_name = '工单消息'
        verbose_name_plural = '工单消息'
        ordering = ['created_at']

    def __str__(self):
        return f'回复 on Ticket #{self.ticket.pk} by {self.user.username}'

# ===== 站内通知 =====
class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', verbose_name='接收用户')
    message = models.CharField('消息内容', max_length=255)
    link = models.URLField('相关链接', blank=True, null=True)
    is_read = models.BooleanField('是否已读', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '通知'
        verbose_name_plural = '通知'
        ordering = ['-created_at']

    def __str__(self):
        return f'给 {self.recipient.username} 的通知: {self.message[:20]}'
