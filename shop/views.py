from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from .models import (
    Shop, Product, ProductCategory, Order, OrderItem, Rider, Address, 
    Banner, Review, SupportTicket, UserProfile, Coupon, Favorite,
    Notification
)
from .forms import (
    ProductForm, RegistrationForm, ProductCategoryForm, AddressForm, 
    ReviewForm, SupportTicketForm, TicketMessageForm, UserUpdateForm, PasswordChangeForm
)
from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib.auth.models import User
from django.contrib.auth import login, update_session_auth_hash
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Count, F, Prefetch
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_POST
import json
from .ai_service import process_ai_conversation
from datetime import date, timedelta
import csv
import io
import random

# ===== Helper Functions =====
def get_cart_summary(session):
    """Computes all cart details and returns them in a dictionary."""
    cart = session.get('cart', {})
    total_price = Decimal('0.00')
    total_items = 0
    for pid, item in cart.items():
        total_price += Decimal(item['price']) * item['quantity']
        total_items += item['quantity']

    summary = {
        'total_price': f'{total_price:.2f}',
        'total_items': total_items,
        'coupon': None,
        'discount': '0.00',
        'final_price': f'{total_price:.2f}',
    }

    coupon_id = session.get('coupon_id')
    if coupon_id:
        try:
            coupon = Coupon.objects.get(id=coupon_id)
            discount = coupon.discount_amount
            final_price = total_price - discount
            summary.update({
                'coupon': {'code': coupon.code, 'discount_amount': f'{discount:.2f}'},
                'discount': f'{discount:.2f}',
                'final_price': f'{final_price:.2f}',
            })
        except Coupon.DoesNotExist:
            session['coupon_id'] = None
            
    return summary

# ===== 核心页面 =====
def shop_list(request):
    shops = Shop.objects.prefetch_related(Prefetch('products', queryset=Product.objects.filter(is_active=True).order_by('-created_at')[:4], to_attr='recent_products'))
    banners = Banner.objects.filter(is_active=True)
    return render(request, 'shop/shop_list.html', {'shops': shops, 'banners': banners})

def search(request):
    query = request.GET.get('q')
    if not query:
        return redirect('shop:shop_list')
    shops = Shop.objects.filter(name__icontains=query)
    products = Product.objects.filter(name__icontains=query, is_active=True)
    return render(request, 'shop/search_results.html', {'query': query, 'shops': shops, 'products': products})

def shop_detail(request, pk):
    shop = get_object_or_404(Shop, pk=pk)
    products = shop.products.filter(is_active=True)
    categories = shop.categories.all()
    return render(request, 'shop/shop_detail.html', {'shop': shop, 'products': products, 'categories': categories})

def product_list(request):
    if is_merchant(request.user):
        products = Product.objects.filter(shop=request.user.shop_account)
    else:
        products = Product.objects.filter(is_active=True)
    return render(request, 'shop/product_list.html', {'products': products})

def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    is_owner = is_merchant(request.user) and product.shop == request.user.shop_account
    if not product.is_active and not is_owner:
        messages.error(request, "该商品已下架。")
        return redirect('shop:product_list')
    reviews = Review.objects.filter(order__items__product=product).distinct()
    
    is_favorited = False
    if request.user.is_authenticated:
        is_favorited = Favorite.objects.filter(user=request.user, product=product).exists()
        
    return render(request, "shop/product_detail.html", {
        "product": product, 
        "reviews": reviews,
        "is_favorited": is_favorited
    })

# ===== 身份校验 =====
def is_merchant(user):
    return user.is_authenticated and hasattr(user, 'shop_account')

def merchant_required(view_func):
    return user_passes_test(is_merchant, login_url='login')(view_func)

def is_rider(user):
    return user.is_authenticated and hasattr(user, 'rider_profile')

def rider_required(view_func):
    return user_passes_test(is_rider, login_url='login')(view_func)

def superuser_required(view_func):
    return user_passes_test(lambda u: u.is_superuser, login_url='login')(view_func)

# ===== API Views (for AJAX) =====
def cart_state_api(request):
    """Returns the current state of the cart."""
    return JsonResponse(get_cart_summary(request.session))

@require_POST
def add_to_cart_api(request):
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
        product = get_object_or_404(Product, pk=product_id)
        
        cart = request.session.get('cart', {})
        cart_shop_id = request.session.get('cart_shop_id')

        if cart and cart_shop_id != product.shop.id:
            return JsonResponse({'success': False, 'message': f"购物车中已有来自 ‘{Shop.objects.get(pk=cart_shop_id).name}’ 的商品，请先清空购物车再添加。"})
        
        if not cart:
            request.session['cart_shop_id'] = product.shop.id
            request.session['coupon_id'] = None

        pid_str = str(product_id)
        if pid_str in cart:
            cart[pid_str]['quantity'] += 1
        else:
            cart[pid_str] = {'name': product.name, 'price': str(product.price), 'quantity': 1}
        
        request.session['cart'] = cart
        return JsonResponse({'success': True, 'message': f"已将 {product.name} 添加到购物车。", 'cart': get_cart_summary(request.session)})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@require_POST
def update_cart_item_api(request):
    try:
        data = json.loads(request.body)
        item_id = str(data.get('item_id'))
        quantity = int(data.get('quantity'))
        
        cart = request.session.get('cart', {})
        if item_id in cart:
            if quantity > 0:
                cart[item_id]['quantity'] = quantity
            else:
                del cart[item_id]
            request.session['cart'] = cart
            if not cart:
                request.session.pop('cart_shop_id', None)
                request.session.pop('coupon_id', None)
            return JsonResponse({'success': True, 'cart': get_cart_summary(request.session)})
        return JsonResponse({'success': False, 'message': '商品未找到'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@require_POST
def remove_cart_item_api(request):
    try:
        data = json.loads(request.body)
        item_id = str(data.get('item_id'))
        cart = request.session.get('cart', {})
        if item_id in cart:
            del cart[item_id]
            request.session['cart'] = cart
            if not cart:
                request.session.pop('cart_shop_id', None)
                request.session.pop('coupon_id', None)
            return JsonResponse({'success': True, 'cart': get_cart_summary(request.session)})
        return JsonResponse({'success': False, 'message': '商品未找到'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@require_POST
def apply_coupon_api(request):
    try:
        data = json.loads(request.body)
        code = data.get('coupon_code')
        shop_id = request.session.get('cart_shop_id')
        cart = request.session.get('cart', {})

        if not code:
            return JsonResponse({'success': False, 'message': '请输入优惠码。'})
        if not shop_id:
            return JsonResponse({'success': False, 'message': '购物车为空，无法使用优惠券。'})

        now = timezone.now()
        try:
            coupon = Coupon.objects.get(code__iexact=code, shop_id=shop_id, is_active=True, valid_from__lte=now, valid_to__gte=now)
            total_price = sum(Decimal(item['price']) * item['quantity'] for item in cart.values())
            if total_price < coupon.min_purchase_amount:
                return JsonResponse({'success': False, 'message': f"订单金额未达到 ¥{coupon.min_purchase_amount} 的最低消费要求。"})

            request.session['coupon_id'] = coupon.id
            return JsonResponse({'success': True, 'message': f"已成功应用优惠券 '{coupon.code}'！", 'cart': get_cart_summary(request.session)})
        except Coupon.DoesNotExist:
            request.session['coupon_id'] = None
            return JsonResponse({'success': False, 'message': '无效或已过期的优惠券。'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required
@require_POST
def chatbot_api(request):
    try:
        # 检查并限制用户Token
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.reset_tokens_if_needed()
        DAILY_TOKEN_LIMIT = 100000 
        if profile.ai_tokens_used >= DAILY_TOKEN_LIMIT:
            return JsonResponse({'error': "抱歉，您今日的AI对话额度已用完，请明天再来。"}, status=429)

        # 解析请求
        data = json.loads(request.body)
        user_question = data.get('question')
        if not user_question:
            return JsonResponse({'error': '问题不能为空。'}, status=400)

        # 调用AI服务（非流式）
        conversation = [{"role": "user", "content": user_question}]
        response_generator = process_ai_conversation(conversation)
        
        # 将生成器的所有内容拼接成一个完整的字符串
        full_response = "".join(response_generator)

        # 检查在AI服务内部是否发生了错误
        if full_response.startswith("请求AI服务时出错:") or "处理请求时发生意外错误" in full_response:
             return JsonResponse({'error': full_response}, status=500)

        # 成功，返回完整响应
        return JsonResponse({'response': full_response})

    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON格式。'}, status=400)
    except Exception as e:
        # 捕获所有其他异常
        return JsonResponse({'error': f'处理请求时发生意外错误: {str(e)}'}, status=500)

@merchant_required
def sales_chart_data(request):
    shop = request.user.shop_account
    period = request.GET.get('period', '7days')
    
    if period == '30days':
        start_date = timezone.now().date() - timedelta(days=30)
    else: # default to 7days
        start_date = timezone.now().date() - timedelta(days=7)

    sales_data = Order.objects.filter(
        shop=shop, 
        paid_at__date__gte=start_date,
        status__in=['PAID', 'PREPARING', 'READY_FOR_PICKUP', 'DELIVERING', 'DELIVERED']
    ).annotate(
        day=TruncDate('paid_at')
    ).values('day').annotate(
        daily_sales=Sum('total')
    ).order_by('day')

    top_products_data = OrderItem.objects.filter(
        order__shop=shop,
        order__paid_at__date__gte=start_date,
        order__status__in=['PAID', 'PREPARING', 'READY_FOR_PICKUP', 'DELIVERING', 'DELIVERED']
    ).values('product__name').annotate(
        total_sold=Sum('quantity')
    ).order_by('-total_sold')[:5]

    data = {
        'sales_trend': {
            'labels': [d['day'].isoformat() if hasattr(d['day'], 'isoformat') else str(d['day']) for d in sales_data],
            'data': [float(d['daily_sales']) for d in sales_data],
        },
        'top_products': {
            'labels': [p['product__name'] for p in top_products_data],
            'data': [p['total_sold'] for p in top_products_data],
        }
    }
    return JsonResponse(data)

@rider_required
def rider_income_data(request):
    rider = request.user.rider_profile
    period = request.GET.get('period', '7days')
    
    if period == '30days':
        start_date = timezone.now().date() - timedelta(days=30)
    else: # default to 7days
        start_date = timezone.now().date() - timedelta(days=7)

    income_data = Order.objects.filter(
        rider=rider, 
        delivered_at__date__gte=start_date,
        status='DELIVERED'
    ).annotate(
        day=TruncDate('delivered_at')
    ).values('day').annotate(
        daily_income=Sum('delivery_fee')
    ).order_by('day')

    data = {
        'income_trend': {
            'labels': [d['day'].isoformat() if hasattr(d['day'], 'isoformat') else str(d['day']) for d in income_data],
            'data': [float(d['daily_income']) for d in income_data],
        }
    }
    return JsonResponse(data)

# ===== Page Rendering Views =====

# ===== 购物车 (页面视图) =====
def cart_detail(request):
    cart = request.session.get('cart', {})
    product_ids = [int(pid) for pid in cart.keys()]
    products = Product.objects.in_bulk(product_ids)
    
    for pid, item in cart.items():
        product = products.get(int(pid))
        if product:
            item['shop_name'] = product.shop.name
            item['subtotal'] = Decimal(item['price']) * item['quantity']

    summary = get_cart_summary(request.session)
    context = {'cart': cart, **summary}
    # The 'total_price', 'coupon', 'discount', 'final_price' are now coming from the summary
    context['total_price'] = Decimal(summary['total_price'])
    if summary['coupon']:
        context['coupon'] = Coupon.objects.get(code=summary['coupon']['code'])
        context['discount'] = Decimal(summary['discount'])
        context['final_price'] = Decimal(summary['final_price'])
    
    return render(request, 'shop/cart_detail.html', context)

# ===== 商家中心 =====
@merchant_required
def merchant_dashboard(request):
    shop = request.user.shop_account
    today = date.today()
    today_sales = Order.objects.filter(shop=shop, paid_at__date=today, status__in=['PAID', 'PREPARING', 'READY_FOR_PICKUP', 'DELIVERING', 'DELIVERED']).aggregate(total_sales=Sum('total'))['total_sales'] or 0
    pending_orders_count = Order.objects.filter(shop=shop, status__in=['PAID', 'PREPARING']).count()
    return render(request, 'shop/merchant_dashboard.html', {
        'shop': shop,
        'today_sales': today_sales,
        'pending_orders_count': pending_orders_count,
    })

@merchant_required
def product_import(request):
    if request.method == 'POST':
        if 'csv_file' not in request.FILES:
            messages.error(request, "请选择一个CSV文件进行上传。")
            return redirect('shop:product_import')

        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "文件格式错误，请上传CSV格式的文件。")
            return redirect('shop:product_import')

        try:
            decoded_file = csv_file.read().decode('utf-8-sig')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)
            
            shop = request.user.shop_account
            products_to_create = []
            products_to_update = []
            errors = []
            
            # Get all existing SKUs in the shop for faster lookup
            existing_skus = {p.sku: p for p in Product.objects.filter(shop=shop)}

            for i, row in enumerate(reader):
                line_num = i + 2
                try:
                    sku = row.get('sku', '').strip()
                    if not sku:
                        errors.append(f"第 {line_num} 行: 'sku' 字段不能为空。")
                        continue

                    name = row.get('name', '').strip()
                    if not name:
                        errors.append(f"第 {line_num} 行: 'name' 字段不能为空。")
                        continue
                        
                    price_str = row.get('price', '0').strip()
                    price = Decimal(price_str)
                    
                    stock_str = row.get('stock', '0').strip()
                    stock = int(stock_str)

                    category_name = row.get('category', '').strip()
                    category = None
                    if category_name:
                        category, _ = ProductCategory.objects.get_or_create(name=category_name, shop=shop)

                    is_active = row.get('is_active', 'true').strip().lower() in ['true', '1', 'yes']
                    
                    product_data = {
                        'name': name,
                        'description': row.get('description', '').strip(),
                        'price': price,
                        'category': category,
                        'stock': stock,
                        'is_active': is_active,
                        'shop': shop
                    }

                    # Use SKU to check for existing product
                    existing_product = existing_skus.get(sku)
                    if existing_product:
                        # Update existing product
                        for key, value in product_data.items():
                            setattr(existing_product, key, value)
                        products_to_update.append(existing_product)
                    else:
                        # Create new product
                        product_data['sku'] = sku
                        products_to_create.append(Product(**product_data))

                except (ValueError, TypeError, InvalidOperation) as e:
                    errors.append(f"第 {line_num} 行: 数据格式错误 - {e}")
                except Exception as e:
                    errors.append(f"第 {line_num} 行: 处理时发生未知错误 - {e}")

            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                with transaction.atomic():
                    if products_to_create:
                        Product.objects.bulk_create(products_to_create)
                        messages.success(request, f"成功创建 {len(products_to_create)} 个新商品。")
                    if products_to_update:
                        # Define fields to be updated
                        update_fields = ['name', 'description', 'price', 'category', 'stock', 'is_active']
                        Product.objects.bulk_update(products_to_update, update_fields)
                        messages.success(request, f"成功更新 {len(products_to_update)} 个现有商品。")
                if not products_to_create and not products_to_update:
                     messages.info(request, "CSV文件中没有需要导入或更新的商品数据。")
                return redirect('shop:product_list')

        except Exception as e:
            messages.error(request, f"处理文件时出错: {e}")

    return render(request, 'shop/product_import.html')

@merchant_required
def product_image_batch_update(request):
    shop = request.user.shop_account
    categories = ProductCategory.objects.filter(shop=shop)

    if request.method == 'POST':
        update_type = request.POST.get('update_type')
        category_id = request.POST.get('category')
        images = request.FILES.getlist('images')

        if not images:
            messages.error(request, "请至少上传一张图片。")
            return redirect('shop:product_image_batch_update')

        products_to_update = Product.objects.filter(shop=shop)
        if update_type == 'category' and category_id:
            products_to_update = products_to_update.filter(category_id=category_id)
        
        if not products_to_update.exists():
            messages.warning(request, "没有找到符合条件的商品进行更新。")
            return redirect('shop:product_image_batch_update')

        try:
            with transaction.atomic():
                if len(images) == 1:
                    # 一张图，覆盖所有选定商品
                    image_file = images[0]
                    for product in products_to_update:
                        product.image.save(image_file.name, image_file, save=True)
                        image_file.seek(0) # 重置文件指针以便下次使用
                else:
                    # 多张图，随机分配
                    for product in products_to_update:
                        chosen_image = random.choice(images)
                        product.image.save(chosen_image.name, chosen_image, save=True)
                        chosen_image.seek(0)
            
            messages.success(request, f"成功更新了 {products_to_update.count()} 个商品的图片。")
            return redirect('shop:product_list')

        except Exception as e:
            messages.error(request, f"更新图片时发生错误: {e}")
            return redirect('shop:product_image_batch_update')

    return render(request, 'shop/product_image_batch_update.html', {'categories': categories})

@merchant_required
def merchant_sales_report(request):
    shop = request.user.shop_account
    period = request.GET.get('period', 'today')
    today = date.today()
    if period == 'week':
        start_date = today - timedelta(days=today.weekday())
    elif period == 'month':
        start_date = today.replace(day=1)
    else:
        start_date = today
    orders = Order.objects.filter(shop=shop, paid_at__date__gte=start_date, status__in=['PAID', 'PREPARING', 'READY_FOR_PICKUP', 'DELIVERING', 'DELIVERED'])
    total_sales = orders.aggregate(Sum('total'))['total__sum'] or 0
    total_orders = orders.count()
    context = {
        'shop': shop,
        'total_sales': total_sales,
        'total_orders': total_orders,
        'orders': orders,
        'period': period
    }
    return render(request, 'shop/merchant_sales_report.html', context)

@merchant_required
def product_sales_report(request):
    shop = request.user.shop_account
    product_sales = OrderItem.objects.filter(
        order__shop=shop,
        order__status__in=['PAID', 'PREPARING', 'READY_FOR_PICKUP', 'DELIVERING', 'DELIVERED']
    ).values(
        'product__name', 
        'product__price'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('product__price'))
    ).order_by('-total_quantity')

    context = {
        'shop': shop,
        'product_sales': product_sales,
    }
    return render(request, 'shop/product_sales_report.html', context)

@merchant_required
def category_list(request):
    shop = request.user.shop_account
    categories = ProductCategory.objects.filter(shop=shop)
    return render(request, 'shop/category_list.html', {'categories': categories})

@merchant_required
def category_create(request):
    if request.method == 'POST':
        form = ProductCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.shop = request.user.shop_account
            category.save()
            messages.success(request, "分类创建成功")
            return redirect('shop:category_list')
    else:
        form = ProductCategoryForm()
    return render(request, 'shop/category_form.html', {'form': form, 'action': '创建'})

@merchant_required
def category_edit(request, pk):
    category = get_object_or_404(ProductCategory, pk=pk, shop=request.user.shop_account)
    if request.method == 'POST':
        form = ProductCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "分类更新成功")
            return redirect('shop:category_list')
    else:
        form = ProductCategoryForm(instance=category)
    return render(request, 'shop/category_form.html', {'form': form, 'action': '编辑'})

@merchant_required
def category_delete(request, pk):
    category = get_object_or_404(ProductCategory, pk=pk, shop=request.user.shop_account)
    if request.method == 'POST':
        category.delete()
        messages.success(request, "分类删除成功")
        return redirect('shop:category_list')
    return render(request, 'shop/category_confirm_delete.html', {'category': category})

@merchant_required
def clear_empty_categories(request):
    if request.method == 'POST':
        shop = request.user.shop_account
        # 找出所有在该店铺下，但没有任何商品关联的分类
        empty_categories = ProductCategory.objects.filter(shop=shop).annotate(
            num_products=Count('products')
        ).filter(num_products=0)
        
        count = empty_categories.count()
        if count > 0:
            empty_categories.delete()
            messages.success(request, f"成功删除了 {count} 个没有商品的分类。")
        else:
            messages.info(request, "没有找到需要清除的空分类。")
            
    return redirect('shop:category_list')

@merchant_required
def product_add(request):
    shop = request.user.shop_account
    if request.method == 'POST':
        form = ProductForm(shop, request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.shop = shop
            product.save()
            messages.success(request, "商品添加成功")
            return redirect('shop:product_list')
    else:
        form = ProductForm(shop)
    return render(request, 'shop/product_form.html', {'form': form, 'action': '添加'})

@merchant_required
def product_edit(request, pk):
    shop = request.user.shop_account
    product = get_object_or_404(Product, pk=pk, shop=shop)
    if request.method == 'POST':
        form = ProductForm(shop, request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "商品更新成功")
            return redirect('shop:product_detail', pk=pk)
    else:
        form = ProductForm(shop, instance=product)
    return render(request, 'shop/product_form.html', {'form': form, 'action': '编辑'})

@merchant_required
def product_toggle(request, pk):
    product = get_object_or_404(Product, pk=pk, shop=request.user.shop_account)
    product.is_active = not product.is_active
    product.save()
    state = "上架" if product.is_active else "下架"
    messages.success(request, f"商品已{state}。")
    return redirect('shop:product_detail', pk=pk)

@merchant_required
def merchant_order_list(request):
    shop = request.user.shop_account
    orders = Order.objects.filter(shop=shop).order_by('-created_at')
    return render(request, 'shop/merchant_order_list.html', {'orders': orders, 'shop': shop})

# ===== 地址管理 =====
@login_required
def address_list(request):
    addresses = Address.objects.filter(user=request.user)
    return render(request, 'shop/address_list.html', {'addresses': addresses})

@login_required
def address_create(request):
    if request.method == 'POST':
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, "地址添加成功")
            return redirect('shop:address_list')
    else:
        form = AddressForm()
    return render(request, 'shop/address_form.html', {'form': form, 'action': '添加'})

@login_required
def address_edit(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == 'POST':
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save()
            messages.success(request, "地址更新成功")
            return redirect('shop:address_list')
    else:
        form = AddressForm(instance=address)
    return render(request, 'shop/address_form.html', {'form': form, 'action': '编辑'})

@login_required
def address_delete(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == 'POST':
        address.delete()
        messages.success(request, "地址删除成功")
        return redirect('shop:address_list')
    return render(request, 'shop/address_confirm_delete.html', {'address': address})

# ===== 订单与支付 =====
@login_required
def select_address(request):
    addresses = Address.objects.filter(user=request.user)
    if not addresses:
        messages.info(request, "请先添加一个收货地址。")
        return redirect('shop:address_create')
    if request.method == 'POST':
        address_id = request.POST.get('address')
        if not address_id:
            messages.error(request, "请选择一个收货地址。")
            return redirect('shop:select_address')
        return redirect(reverse('shop:checkout', kwargs={'address_id': address_id}))
    return render(request, 'shop/select_address.html', {'addresses': addresses})

@login_required
@transaction.atomic
def checkout(request, address_id):
    cart = request.session.get('cart', {})
    shop_id = request.session.get('cart_shop_id')
    address = get_object_or_404(Address, pk=address_id, user=request.user)

    if not cart or not shop_id:
        messages.error(request, "购物车为空")
        return redirect('shop:cart_detail')

    shop = get_object_or_404(Shop, pk=shop_id)
    subtotal = sum(Decimal(item['price']) * item['quantity'] for item in cart.values())
    delivery_fee = Decimal('1.00')
    
    summary = get_cart_summary(request.session)
    discount = Decimal(summary['discount'])
    coupon = None
    if summary['coupon']:
        coupon = Coupon.objects.get(code=summary['coupon']['code'])

    total = subtotal - discount + delivery_fee
    if total < 0:
        total = 0

    order = Order.objects.create(
        user=request.user, 
        shop=shop, 
        shipping_address=address, 
        status='PENDING', 
        subtotal=subtotal, 
        coupon=coupon,
        discount=discount,
        delivery_fee=delivery_fee, 
        total=total
    )

    for pid, item in cart.items():
        product = get_object_or_404(Product, pk=int(pid))
        if product.stock < item['quantity']:
            messages.error(request, f"商品库存不足：{product.name}")
            transaction.set_rollback(True)
            return redirect('shop:cart_detail')
        OrderItem.objects.create(order=order, product=product, quantity=item['quantity'])
    
    request.session['cart'] = {}
    request.session.pop('cart_shop_id', None)
    request.session.pop('coupon_id', None)
    
    messages.success(request, "订单已创建，请支付")
    return redirect('shop:order_detail', pk=order.pk)

@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related('items__product').order_by('-created_at')
    return render(request, 'shop/order_list.html', {'orders': orders})

@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related('items__product'), pk=pk)
    is_customer = request.user == order.user
    is_shop_owner = is_merchant(request.user) and request.user.shop_account == order.shop
    is_order_rider = is_rider(request.user) and order.rider and request.user.rider_profile == order.rider
    if not (is_customer or is_shop_owner or is_order_rider):
        messages.error(request, "您没有权限查看此订单。")
        return redirect('shop:order_list')
    for item in order.items.all():
        item.subtotal = item.product.price * item.quantity
    return render(request, 'shop/order_detail.html', {'order': order})

@login_required
def order_pay(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status != 'PENDING':
        messages.info(request, "该订单不能支付")
        return redirect('shop:order_detail', pk=pk)
    with transaction.atomic():
        for item in order.items.all():
            product = item.product
            if product.stock < item.quantity:
                messages.error(request, f"商品库存不足：{product.name}")
                return redirect('shop:order_detail', pk=pk)
            product.stock -= item.quantity
            product.save()
        order.status = 'PAID'
        order.paid_at = timezone.now()
        order.save()
    messages.success(request, "支付成功，库存已扣除")
    return redirect('shop:order_detail', pk=order.pk)

# ===== 外卖员中心 =====
@rider_required
def rider_order_list(request):
    rider = request.user.rider_profile
    available_orders = Order.objects.filter(status='PAID', rider__isnull=True).order_by('paid_at')
    my_orders = Order.objects.filter(rider=rider, status='DELIVERING').order_by('accepted_at')
    return render(request, 'shop/rider_order_list.html', {'available_orders': available_orders, 'my_orders': my_orders})

@rider_required
@transaction.atomic
def rider_accept_order(request, pk):
    rider = request.user.rider_profile
    if rider.orders.filter(status='DELIVERING').count() >= 10:
        messages.error(request, "您最多只能同时接10个订单。")
        return redirect('shop:rider_order_list')
    order = get_object_or_404(Order, pk=pk, status='PAID', rider__isnull=True)
    order.rider = rider
    order.status = 'DELIVERING'
    order.accepted_at = timezone.now()
    order.save()
    messages.success(request, f"成功接收订单 #{order.pk}")
    return redirect('shop:rider_order_list')

@rider_required
def rider_update_order_status(request, pk):
    order = get_object_or_404(Order, pk=pk, rider=request.user.rider_profile)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status == 'READY_FOR_PICKUP' and order.status == 'PAID':
            order.status = new_status
            order.save()
            messages.success(request, "订单状态已更新为 ‘待取货’")
        elif new_status == 'DELIVERED' and order.status == 'DELIVERING':
            order.status = new_status
            order.delivered_at = timezone.now()
            order.save()
            messages.success(request, "订单已送达！")
        else:
            messages.error(request, "无效的状态更新。")
    return redirect('shop:order_detail', pk=order.pk)

@rider_required
def rider_history(request):
    rider = request.user.rider_profile
    completed_orders = Order.objects.filter(rider=rider, status='DELIVERED').order_by('-delivered_at')
    total_earnings = completed_orders.aggregate(total=Sum('delivery_fee'))['total'] or 0
    context = {'completed_orders': completed_orders, 'total_earnings': total_earnings}
    return render(request, 'shop/rider_history.html', context)

@rider_required
def rider_income_dashboard(request):
    rider = request.user.rider_profile
    today = timezone.now().date()
    
    # 总览数据
    total_earnings = Order.objects.filter(rider=rider, status='DELIVERED').aggregate(total=Sum('delivery_fee'))['total'] or 0
    total_orders = Order.objects.filter(rider=rider, status='DELIVERED').count()
    
    # 今日数据
    today_earnings = Order.objects.filter(rider=rider, status='DELIVERED', delivered_at__date=today).aggregate(total=Sum('delivery_fee'))['total'] or 0
    today_orders = Order.objects.filter(rider=rider, status='DELIVERED', delivered_at__date=today).count()

    context = {
        'total_earnings': total_earnings,
        'total_orders': total_orders,
        'today_earnings': today_earnings,
        'today_orders': today_orders,
    }
    return render(request, 'shop/rider_income_dashboard.html', context)

# ===== 评价 =====
@login_required
def add_review(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status != 'DELIVERED':
        messages.error(request, "订单尚未完成，不能评价。")
        return redirect('shop:order_detail', pk=order.pk)
    if hasattr(order, 'review'):
        messages.error(request, "您已经评价过此订单。")
        return redirect('shop:order_detail', pk=order.pk)
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.order = order
            review.user = request.user
            review.save()
            messages.success(request, "感谢您的评价！")
            return redirect('shop:order_detail', pk=order.pk)
    else:
        form = ReviewForm()
    return render(request, 'shop/add_review.html', {'form': form, 'order': order})

# ===== 客服工单 =====
@login_required
def ticket_list(request):
    tickets = SupportTicket.objects.filter(user=request.user)
    return render(request, 'shop/ticket_list.html', {'tickets': tickets})

@login_required
def ticket_create(request):
    if request.method == 'POST':
        form = SupportTicketForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.user = request.user
            ticket.save()
            messages.success(request, "您的客服工单已提交，我们会尽快处理。")
            return redirect('shop:ticket_detail', pk=ticket.pk)
    else:
        form = SupportTicketForm()
    return render(request, 'shop/ticket_form.html', {'form': form})

@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(SupportTicket, pk=pk)
    is_owner = ticket.user == request.user
    is_admin = request.user.is_superuser
    can_view = is_owner or is_admin or is_merchant(request.user)
    if not can_view:
        messages.error(request, "您没有权限查看此工单。")
        return redirect('shop:ticket_list')
    if request.method == 'POST':
        form = TicketMessageForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.ticket = ticket
            message.user = request.user
            message.save()
            if is_owner and ticket.status == 'CLOSED':
                ticket.status = 'IN_PROGRESS'
                ticket.save()
            messages.success(request, "您的回复已发送。")
            return redirect('shop:ticket_detail', pk=pk)
    else:
        form = TicketMessageForm()
    return render(request, 'shop/ticket_detail.html', {'ticket': ticket, 'form': form})

@login_required
def support_inbox(request):
    if not (request.user.is_superuser or is_merchant(request.user)):
        messages.error(request, "您没有权限访问此页面。")
        return redirect('shop:shop_list')
    if request.user.is_superuser:
        tickets = SupportTicket.objects.all()
    else:
        tickets = SupportTicket.objects.all()
    return render(request, 'shop/support_inbox.html', {'tickets': tickets})

@login_required
def ticket_update_status(request, pk):
    if not (request.user.is_superuser or is_merchant(request.user)):
        return redirect('shop:support_inbox')
    ticket = get_object_or_404(SupportTicket, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['OPEN', 'IN_PROGRESS', 'CLOSED']:
            ticket.status = new_status
            ticket.save()
            messages.success(request, f"工单 #{ticket.pk} 状态已更新。")
    return redirect('shop:ticket_detail', pk=pk)

# ===== 后台管理 =====
@superuser_required
def user_batch_create(request):
    if request.method == 'POST':
        if 'csv_file' not in request.FILES:
            messages.error(request, "请选择一个CSV文件进行上传。")
            return redirect('shop:user_batch_create')

        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "文件格式错误，请上传CSV格式的文件。")
            return redirect('shop:user_batch_create')

        errors = []
        created_count = 0
        try:
            decoded_file = csv_file.read().decode('utf-8-sig')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            with transaction.atomic():
                for i, row in enumerate(reader):
                    line_num = i + 2
                    username = row.get('username', '').strip()
                    password = row.get('password', '').strip()
                    user_type = row.get('user_type', 'customer').strip().lower()

                    if not username or not password:
                        errors.append(f"第 {line_num} 行: 'username' 和 'password' 字段不能为空。")
                        continue
                    
                    if User.objects.filter(username=username).exists():
                        errors.append(f"第 {line_num} 行: 用户名 '{username}' 已存在。")
                        continue

                    try:
                        user = User.objects.create_user(username=username, password=password)
                        
                        if user_type == 'merchant':
                            shop_name = row.get('shop_name', '').strip()
                            if not shop_name:
                                errors.append(f"第 {line_num} 行: 商家用户 '{username}' 必须关联一个 'shop_name'。")
                                continue # 继续循环但此用户不会被完全创建
                            
                            shop, created = Shop.objects.get_or_create(
                                name=shop_name,
                                defaults={'description': row.get('shop_description', ''), 'account': user}
                            )
                            if not created: # 如果店铺已存在
                                if shop.account and shop.account != user:
                                    errors.append(f"第 {line_num} 行: 店铺 '{shop_name}' 已被其他用户关联。")
                                    continue
                                shop.account = user
                                shop.save()
                            
                        elif user_type == 'rider':
                            Rider.objects.create(user=user)
                        
                        created_count += 1

                    except Exception as e:
                        errors.append(f"第 {line_num} 行 ('{username}'): 创建用户时出错 - {e}")

                if errors:
                    # 如果有任何错误，则回滚整个事务
                    transaction.set_rollback(True)
                    for error in errors:
                        messages.error(request, error)
                else:
                    messages.success(request, f"成功创建了 {created_count} 个用户。")
                    return redirect('shop:shop_list') # 成功后跳转

        except Exception as e:
            messages.error(request, f"处理文件时出错: {e}")

    return render(request, 'shop/admin/user_batch_create.html')

@superuser_required
def order_import(request):
    if request.method == 'POST':
        if 'csv_file' not in request.FILES:
            messages.error(request, "请选择一个CSV文件进行上传。")
            return redirect('shop:order_import')

        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "文件格式错误，请上传CSV格式的文件。")
            return redirect('shop:order_import')

        errors = []
        created_count = 0
        try:
            decoded_file = csv_file.read().decode('utf-8-sig')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            with transaction.atomic():
                for i, row in enumerate(reader):
                    line_num = i + 2
                    try:
                        user = User.objects.get(username=row.get('user_username', '').strip())
                        shop = Shop.objects.get(name=row.get('shop_name', '').strip())
                        
                        # Get or create address
                        address, _ = Address.objects.get_or_create(
                            user=user,
                            contact_name=row.get('contact_name', '').strip(),
                            contact_phone=row.get('contact_phone', '').strip(),
                            address_line_1=row.get('address_line_1', '').strip(),
                            city=row.get('city', '').strip(),
                            postal_code=row.get('postal_code', '').strip()
                        )

                        # 解析 items JSON
                        items_str = row.get('items', '[]').strip()
                        items_data = json.loads(items_str)
                        if not items_data:
                            errors.append(f"第 {line_num} 行: 'items' 字段不能为空列表。")
                            continue

                        # 计算订单金额
                        subtotal = Decimal('0.00')
                        order_items_to_create = []
                        for item_data in items_data:
                            product = Product.objects.get(sku=item_data['sku'], shop=shop)
                            quantity = int(item_data['quantity'])
                            subtotal += product.price * quantity
                            order_items_to_create.append(OrderItem(product=product, quantity=quantity))

                        delivery_fee = Decimal(row.get('delivery_fee', '1.00').strip())
                        total = subtotal + delivery_fee
                        
                        order_data = {
                            'user': user,
                            'shop': shop,
                            'shipping_address': address,
                            'status': row.get('status', 'DELIVERED').strip(),
                            'subtotal': subtotal,
                            'delivery_fee': delivery_fee,
                            'total': total,
                            'created_at': row.get('created_at') or timezone.now(),
                            'paid_at': row.get('paid_at') or timezone.now(),
                        }
                        
                        order = Order.objects.create(**order_data)
                        for item in order_items_to_create:
                            item.order = order
                        OrderItem.objects.bulk_create(order_items_to_create)
                        
                        created_count += 1

                    except User.DoesNotExist:
                        errors.append(f"第 {line_num} 行: 用户 '{row.get('user_username')}' 不存在。")
                    except Shop.DoesNotExist:
                        errors.append(f"第 {line_num} 行: 店铺 '{row.get('shop_name')}' 不存在。")
                    except Product.DoesNotExist:
                        errors.append(f"第 {line_num} 行: 商品SKU '{item_data['sku']}' 不存在或不属于该店铺。")
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        errors.append(f"第 {line_num} 行: 数据格式错误 - {e}")

                if errors:
                    transaction.set_rollback(True)
                    for error in errors:
                        messages.error(request, error)
                else:
                    messages.success(request, f"成功导入了 {created_count} 个订单。")
                    return redirect('shop:order_list')

        except Exception as e:
            messages.error(request, f"处理文件时发生严重错误: {e}")

    return render(request, 'shop/admin/order_import.html')

@superuser_required
def review_import(request):
    if request.method == 'POST':
        if 'csv_file' not in request.FILES:
            messages.error(request, "请选择一个CSV文件进行上传。")
            return redirect('shop:review_import')

        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "文件格式错误，请上传CSV格式的文件。")
            return redirect('shop:review_import')

        errors = []
        created_count = 0
        try:
            decoded_file = csv_file.read().decode('utf-8-sig')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            with transaction.atomic():
                for i, row in enumerate(reader):
                    line_num = i + 2
                    try:
                        order_id = row.get('order_id', '').strip()
                        if not order_id:
                            errors.append(f"第 {line_num} 行: 'order_id' 字段不能为空。")
                            continue

                        order = Order.objects.get(pk=order_id)
                        
                        # 检查该订单是否已经有评价
                        if Review.objects.filter(order=order).exists():
                            errors.append(f"第 {line_num} 行: 订单ID '{order_id}' 已存在评价，跳过。")
                            continue

                        rating = int(row.get('rating', '').strip())
                        if not (1 <= rating <= 5):
                            errors.append(f"第 {line_num} 行: 'rating' 必须是1到5之间的整数。")
                            continue

                        Review.objects.create(
                            order=order,
                            user=order.user, # 评价用户默认为订单用户
                            rating=rating,
                            comment=row.get('comment', '').strip(),
                            created_at=row.get('created_at') or timezone.now()
                        )
                        created_count += 1

                    except Order.DoesNotExist:
                        errors.append(f"第 {line_num} 行: 订单ID '{order_id}' 不存在。")
                    except (ValueError, TypeError) as e:
                        errors.append(f"第 {line_num} 行: 数据格式错误 - {e}")

                if errors:
                    transaction.set_rollback(True)
                    for error in errors:
                        messages.error(request, error)
                else:
                    messages.success(request, f"成功导入了 {created_count} 条评价。")
                    return redirect('shop:order_list')

        except Exception as e:
            messages.error(request, f"处理文件时发生严重错误: {e}")

    return render(request, 'shop/admin/review_import.html')


# ===== 用户注册 =====
def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "注册并登录成功")
            return redirect('shop:product_list')
    else:
        form = RegistrationForm()
    return render(request, 'registration/register.html', {'form': form})

# ===== 用户资料 =====
@login_required
def profile(request):
    if request.method == 'POST':
        # Determine which form is being submitted
        if 'update_profile' in request.POST:
            user_form = UserUpdateForm(request.POST, instance=request.user)
            password_form = PasswordChangeForm(request.user) # Keep it fresh
            if user_form.is_valid():
                user_form.save()
                messages.success(request, '您的个人信息已成功更新。')
                return redirect('shop:profile')
        
        elif 'change_password' in request.POST:
            user_form = UserUpdateForm(instance=request.user) # Keep it fresh
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # Important!
                messages.success(request, '您的密码已成功更改。')
                return redirect('shop:profile')
        
        else:
            # Fallback for unexpected POST
            user_form = UserUpdateForm(instance=request.user)
            password_form = PasswordChangeForm(request.user)

    else:
        user_form = UserUpdateForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)

    return render(request, 'shop/profile.html', {
        'user_form': user_form,
        'password_form': password_form
    })

# ===== 收藏夹 =====
@login_required
def favorite_list(request):
    favorites = Favorite.objects.filter(user=request.user).select_related('product')
    return render(request, 'shop/favorite_list.html', {'favorites': favorites})

@login_required
@require_POST
def toggle_favorite(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    fav, created = Favorite.objects.get_or_create(user=request.user, product=product)

    if created:
        messages.success(request, f"已将 ‘{product.name}’ 添加到您的收藏夹。")
    else:
        fav.delete()
        messages.success(request, f"已将 ‘{product.name}’ 从您的收藏夹中移除。")
    
    # Redirect back to the same page
    return redirect(request.META.get('HTTP_REFERER', 'shop:product_list'))

# ===== 通知 =====
@login_required
def notification_list(request):
    notifications = Notification.objects.filter(recipient=request.user)
    return render(request, 'shop/notification_list.html', {'notifications': notifications})

@login_required
def mark_notification_as_read(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, recipient=request.user)
    notification.is_read = True
    notification.save()
    
    if notification.link:
        return redirect(notification.link)
    
    return redirect('shop:notification_list')

# ===== 传统同步购物车操作 (后备) =====
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    cart = request.session.get('cart', {})
    cart_shop_id = request.session.get('cart_shop_id')
    if cart and cart_shop_id != product.shop.id:
        messages.error(request, f"购物车中已有来自 ‘{Shop.objects.get(pk=cart_shop_id).name}’ 的商品，请先清空购物车再添加。")
    else:
        if not cart:
            request.session['cart_shop_id'] = product.shop.id
        pid_str = str(product_id)
        if pid_str in cart:
            cart[pid_str]['quantity'] += 1
        else:
            cart[pid_str] = {'name': product.name, 'price': str(product.price), 'quantity': 1}
        request.session['cart'] = cart
        messages.success(request, f"已将 {product.name} 添加到购物车。")
    return redirect('shop:cart_detail')

def update_cart_item(request, item_id):
    cart = request.session.get('cart', {})
    pid_str = str(item_id)
    if pid_str in cart:
        try:
            qty = int(request.POST.get('quantity', 1))
            if qty > 0:
                cart[pid_str]['quantity'] = qty
            else:
                del cart[pid_str]
        except ValueError:
            messages.error(request, "数量无效。")
    request.session['cart'] = cart
    if not cart:
        request.session.pop('cart_shop_id', None)
        request.session.pop('coupon_id', None)
    return redirect('shop:cart_detail')

def remove_cart_item(request, item_id):
    cart = request.session.get('cart', {})
    pid_str = str(item_id)
    if pid_str in cart:
        del cart[pid_str]
    request.session['cart'] = cart
    if not cart:
        request.session.pop('cart_shop_id', None)
        request.session.pop('coupon_id', None)
    messages.success(request, "已移除商品")
    return redirect('shop:cart_detail')

def clear_cart(request):
    request.session['cart'] = {}
    request.session.pop('cart_shop_id', None)
    request.session.pop('coupon_id', None)
    messages.success(request, "购物车已清空")
    return redirect('shop:cart_detail')

# ===== 优惠券 =====
def apply_coupon(request):
    if request.method == 'POST':
        code = request.POST.get('coupon_code')
        shop_id = request.session.get('cart_shop_id')
        cart = request.session.get('cart', {})
        if not code:
            messages.error(request, "请输入优惠码。")
        elif not shop_id:
            messages.error(request, "购物车为空，无法使用优惠券。")
        else:
            now = timezone.now()
            try:
                coupon = Coupon.objects.get(code__iexact=code, shop_id=shop_id, is_active=True, valid_from__lte=now, valid_to__gte=now)
                total_price = sum(Decimal(item['price']) * item['quantity'] for item in cart.values())
                if total_price < coupon.min_purchase_amount:
                    messages.error(request, f"订单金额未达到 ¥{coupon.min_purchase_amount} 的最低消费要求。")
                else:
                    request.session['coupon_id'] = coupon.id
                    messages.success(request, f"已成功应用优惠券 '{coupon.code}'！")
            except Coupon.DoesNotExist:
                messages.error(request, "无效或已过期的优惠券。")
                request.session['coupon_id'] = None
    return redirect('shop:cart_detail')
