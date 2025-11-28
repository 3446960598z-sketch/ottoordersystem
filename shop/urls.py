from django.urls import path
from . import views

app_name = 'shop'

urlpatterns = [
    # 核心浏览
    path('', views.shop_list, name='shop_list'),
    path('shop/<int:pk>/', views.shop_detail, name='shop_detail'),
    path('products/', views.product_list, name='product_list'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),
    path('product/<int:product_id>/toggle-favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('search/', views.search, name='search'),

    # 用户认证与资料
    path('register/', views.register, name='register'),
    path('profile/', views.profile, name='profile'),
    path('favorites/', views.favorite_list, name='favorite_list'),

    # 通知
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_as_read, name='mark_notification_as_read'),

    # 购物车 (页面视图)
    path('cart/', views.cart_detail, name='cart_detail'),
    
    # 传统同步操作 (保留作为后备)
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/<int:item_id>/', views.update_cart_item, name='update_cart_item'),
    path('cart/remove/<int:item_id>/', views.remove_cart_item, name='remove_cart_item'),
    path('cart/clear/', views.clear_cart, name='clear_cart'),
    path('cart/apply-coupon/', views.apply_coupon, name='apply_coupon'),

    # 地址管理
    path('addresses/', views.address_list, name='address_list'),
    path('addresses/add/', views.address_create, name='address_create'),
    path('addresses/<int:pk>/edit/', views.address_edit, name='address_edit'),
    path('addresses/<int:pk>/delete/', views.address_delete, name='address_delete'),

    # 订单流程
    path('order/select-address/', views.select_address, name='select_address'),
    path('order/checkout/<int:address_id>/', views.checkout, name='checkout'),
    path('orders/', views.order_list, name='order_list'),
    path('order/<int:pk>/', views.order_detail, name='order_detail'),
    path('order/<int:pk>/pay/', views.order_pay, name='order_pay'),
    path('order/<int:pk>/review/', views.add_review, name='add_review'),

    # 商家中心
    path('merchant/', views.merchant_dashboard, name='merchant_dashboard'),
    path('merchant/sales-report/', views.merchant_sales_report, name='merchant_sales_report'),
    path('merchant/product-sales-report/', views.product_sales_report, name='product_sales_report'),
    path('merchant/orders/', views.merchant_order_list, name='merchant_order_list'),
    path('merchant/products/', views.product_list, name='merchant_product_list'),
    path('merchant/product/add/', views.product_add, name='product_add'),
    path('merchant/product/import/', views.product_import, name='product_import'),
    path('merchant/product/image-batch-update/', views.product_image_batch_update, name='product_image_batch_update'),
    path('merchant/product/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('merchant/product/<int:pk>/toggle/', views.product_toggle, name='product_toggle'),
    path('merchant/categories/', views.category_list, name='category_list'),
    path('merchant/category/add/', views.category_create, name='category_create'),
    path('merchant/category/clear-empty/', views.clear_empty_categories, name='clear_empty_categories'),
    path('merchant/category/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('merchant/category/<int:pk>/delete/', views.category_delete, name='category_delete'),
    path('merchant/support-inbox/', views.support_inbox, name='support_inbox'),
    path('merchant/api/sales-chart-data/', views.sales_chart_data, name='sales_chart_data'),

    # 后台管理
    path('manage/user-batch-create/', views.user_batch_create, name='user_batch_create'),
    path('manage/order-import/', views.order_import, name='order_import'),
    path('manage/review-import/', views.review_import, name='review_import'),

    # 外卖员中心
    path('rider/', views.rider_order_list, name='rider_order_list'),
    path('rider/income/', views.rider_income_dashboard, name='rider_income_dashboard'),
    path('rider/order/<int:pk>/accept/', views.rider_accept_order, name='rider_accept_order'),
    path('rider/order/<int:pk>/update-status/', views.rider_update_order_status, name='rider_update_order_status'),
    path('rider/history/', views.rider_history, name='rider_history'),
    path('rider/api/income-data/', views.rider_income_data, name='rider_income_data'),


    # 客服工单
    path('support/tickets/', views.ticket_list, name='ticket_list'),
    path('support/ticket/create/', views.ticket_create, name='ticket_create'),
    path('support/ticket/<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('support/ticket/<int:pk>/update-status/', views.ticket_update_status, name='ticket_update_status'),

    # API 路径 (用于异步操作)
    path('api/cart/state/', views.cart_state_api, name='cart_state_api'),
    path('api/cart/add/', views.add_to_cart_api, name='add_to_cart_api'),
    path('api/cart/update/', views.update_cart_item_api, name='update_cart_item_api'),
    path('api/cart/remove/', views.remove_cart_item_api, name='remove_cart_item_api'),
    path('api/cart/apply-coupon/', views.apply_coupon_api, name='apply_coupon_api'),
    path('api/chatbot/', views.chatbot_api, name='chatbot_api'),
]
