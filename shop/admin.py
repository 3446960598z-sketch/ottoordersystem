from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Shop, Rider, Product, ProductCategory, Order, OrderItem, 
    Address, Review, Banner, SupportTicket, TicketMessage, Coupon
)

# Helper function to mask sensitive codes
def mask_value(value, show_chars=4):
    """Masks a value, showing only the first and last few characters."""
    if value and len(value) > show_chars * 2:
        return f"{value[:show_chars]}...{value[-show_chars:]}"
    return value

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('masked_code', 'shop', 'discount_amount', 'min_purchase_amount', 'valid_from', 'valid_to', 'is_active')
    list_filter = ('shop', 'is_active')
    search_fields = ('code', 'shop__name')
    
    def masked_code(self, obj):
        return mask_value(obj.code)
    masked_code.short_description = '优惠码'

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj:
            form.base_fields['code'].initial = mask_value(obj.code)
        return form

    def save_model(self, request, obj, form, change):
        # If the code hasn't been changed (still masked), keep the original.
        if change and form.cleaned_data['code'] == mask_value(obj.code):
            obj.code = Coupon.objects.get(pk=obj.pk).code
        super().save_model(request, obj, form, change)

@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'get_linked_object', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title',)
    raw_id_fields = ('linked_shop', 'linked_product')

    def get_linked_object(self, obj):
        if obj.linked_shop:
            return f"店铺: {obj.linked_shop.name}"
        if obj.linked_product:
            return f"商品: {obj.linked_product.name}"
        return "无链接"
    get_linked_object.short_description = '跳转链接'

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'account', 'display_image', 'created_at')
    search_fields = ('name',)

    def display_image(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" />', obj.image.url)
        return "无图片"
    display_image.short_description = '店铺图片'

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop')
    list_filter = ('shop',)
    search_fields = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop', 'category', 'price', 'stock', 'is_active')
    list_filter = ('shop', 'category', 'is_active')
    search_fields = ('name', 'sku')

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'address_line_1', 'city', 'is_default')
    list_filter = ('user',)
    search_fields = ('address_line_1', 'city')

@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    search_fields = ('user__username',)

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'shop', 'status', 'total', 'created_at')
    list_filter = ('status', 'shop')
    search_fields = ('id', 'user__username')
    readonly_fields = ('user', 'shop', 'rider', 'shipping_address', 'subtotal', 'coupon', 'discount', 'delivery_fee', 'total', 'created_at', 'paid_at', 'accepted_at', 'delivered_at')
    inlines = [OrderItemInline]

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('order', 'user', 'rating', 'created_at')
    list_filter = ('rating',)
    search_fields = ('order__id', 'user__username')

class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 1
    readonly_fields = ('created_at',)

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'user', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('subject', 'user__username')
    inlines = [TicketMessageInline]
