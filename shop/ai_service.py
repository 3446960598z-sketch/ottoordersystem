import requests
import json
from urllib.request import getproxies
from django.core.cache import cache
from django.db import connection
from site_settings.models import SiteSetting
import warnings

# --- 0. 动态配置及缓存 ---
def get_dynamic_setting(key, default_value):
    """
    从缓存或数据库获取配置。
    - 首先尝试从缓存中获取。
    - 如果缓存中没有，则从数据库中获取，并将其存入缓存。
    - 缓存时间：成功获取的配置缓存10分钟，不存在的配置缓存1分钟。
    """
    cache_key = f"site_setting:{key}"
    cached_value = cache.get(cache_key)
    if cached_value is not None:
        return cached_value

    try:
        if SiteSetting._meta.db_table not in connection.introspection.table_names():
            return default_value
        
        setting = SiteSetting.objects.get(key=key)
        value = setting.value
        cache.set(cache_key, value, timeout=600)  # 缓存10分钟
        return value
    except SiteSetting.DoesNotExist:
        cache.set(cache_key, default_value, timeout=60)  # 缓存“不存在”的结果1分钟
        return default_value
    except Exception:
        return default_value

# --- 1. 数据库查询工具 ---
def query_database(sql_query: str):
    """ 
    执行一个只读的SQL查询并返回结果。
    为了安全，只允许执行 SELECT 语句。
    """
    if not sql_query.strip().upper().startswith('SELECT'):
        return json.dumps({"error": "为了安全，只允许执行 SELECT 查询。"})
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql_query)
            columns = [col[0] for col in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if not results:
                return json.dumps({"message": "查询成功，但没有返回任何数据。"})
            return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"数据库查询出错: {str(e)}"})

# --- 2. AI 交互核心 ---

# 默认系统提示词，当数据库中未设置时使用
DEFAULT_SYSTEM_PROMPT = """
你是一个智能数据库助手。你的名字叫“数问”。
你的任务是根据用户的问题，生成并执行SQL查询来回答问题。

# 可用工具:
你只有一个名为 `query_database` 的工具，你可以使用它来执行SQL查询。

# 数据库结构:
以下是你可查询的数据库中的主要表和关键字段：
- `shop_shop` (店铺表): id, name, description, created_at, updated_at, account_id
- `shop_productcategory` (商品分类表): id, shop_id, name, description
- `shop_address` (收货地址表): id, user_id, address_line_1, city, postal_code, contact_name, contact_phone, is_default
- `shop_product` (商品表): id, shop_id, category_id, name, sku, price, stock, description, is_active, created_at, updated_at
- `shop_userprofile` (用户资料表): id, user_id, ai_tokens_used, last_token_reset_date
- `shop_rider` (外卖员表): id, user_id, created_at
- `shop_order` (订单表): id, user_id, shop_id, rider_id, shipping_address_id, subtotal, delivery_fee, total, status, created_at, paid_at, accepted_at, delivered_at
- `shop_orderitem` (订单项表): id, order_id, product_id, quantity
- `shop_review` (评价表): id, order_id, user_id, rating, comment, created_at
- `shop_supportticket` (客服工单表): id, user_id, subject, description, status, created_at, updated_at
- `shop_ticketmessage` (工单消息表): id, ticket_id, user_id, message, created_at
- `auth_user` (用户表): id, username, email, first_name, last_name, is_staff, is_active, date_joined

# 工作流程:
1.  **分析问题**: 理解用户的意图。
2.  **生成SQL**: 根据用户问题，生成一个合适的、只读的 `SELECT` SQL查询语句。你可以进行多表连接查询。
3.  **调用工具**: 使用 `query_database` 工具执行你生成的SQL。
4.  **生成最终答案**: 根据工具返回的JSON结果，用友好、自然的语言总结并回答用户的问题。如果需要，可以综合多个查询结果来提供更全面的信息。不要直接暴露SQL或原始JSON数据给用户。

# 重要提示：如何查询销量
- **有效订单**: 只有 `status` 为 'PAID', 'PREPARING', 'READY_FOR_PICKUP', 'DELIVERING', 'DELIVERED' 的订单才是有效销售。
- **菜品销量**: 要计算菜品销量，你需要连接 `shop_orderitem` 和 `shop_order` 表，并根据上述有效状态进行过滤。

# 示例：查询菜品销量
- **问题**: "查询每个菜品的销量"
- **SQL**: `SELECT p.name, SUM(oi.quantity) AS total_sold FROM shop_orderitem oi JOIN shop_order o ON oi.order_id = o.id JOIN shop_product p ON oi.product_id = p.id WHERE o.status IN ('PAID', 'PREPARING', 'READY_FOR_PICKUP', 'DELIVERING', 'DELIVERED') GROUP BY p.name ORDER BY total_sold DESC;`

# 行为准则:
- **安全第一**: 绝对不能生成或执行 `INSERT`, `UPDATE`, `DELETE`, `DROP` 等任何非 `SELECT` 的SQL语句。
- **友好回答**: 即使工具返回错误或没有数据，也要以友好的方式告知用户。
- **角色扮演**: 始终以“数问”的身份回答。
- **精确调用**: 严格按照工具的JSON格式进行调用。
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "执行一个只读的SQL查询来从数据库获取信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql_query": {
                        "type": "string",
                        "description": "要执行的SELECT SQL查询语句。例如：SELECT p.name, p.price, c.name FROM shop_product AS p JOIN shop_productcategory AS c ON p.category_id = c.id WHERE p.price > 50;"
                    }
                },
                "required": ["sql_query"]
            }
        }
    }
]

def get_ai_response(conversation):
    """获取AI的回复（非流式）"""
    api_url = get_dynamic_setting('AI_ASSISTANT_URL', "")
    api_key = get_dynamic_setting('OPENAI_API_KEY', "")
    
    if not api_url or not api_key:
        raise ValueError("AI服务未配置，请在后台设置API地址和密钥。")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "deepseek-chat",
        "messages": conversation,
        "tools": TOOLS,
        "tool_choice": "auto",
        "stream": False
    }
    
    # 获取并规范化系统代理
    system_proxies = getproxies()
    proxies = {}
    http_proxy = system_proxies.get('http')
    
    # 关键修复：如果存在http代理，则强制将其用于https流量，以覆盖错误的 "https://" 代理地址
    if http_proxy and isinstance(http_proxy, str) and http_proxy.startswith('http://'):
        proxies['http'] = http_proxy
        proxies['https'] = http_proxy # 强制使用http代理
    else:
        # 如果没有http代理，则尝试使用https代理，并纠正其协议
        https_proxy = system_proxies.get('https')
        if https_proxy and isinstance(https_proxy, str):
            normalized_proxy = https_proxy.replace('https://', 'http://')
            proxies['http'] = normalized_proxy
            proxies['https'] = normalized_proxy

    warnings.filterwarnings('ignore', message='Unverified HTTPS request')

    response = requests.post(api_url, headers=headers, json=payload, proxies=proxies, verify=False)
    response.raise_for_status()
    
    return response

def process_ai_conversation(conversation):
    """
    处理完整的AI对话流程（非流式），返回最终的回复字符串。
    """
    try:
        system_prompt_content = get_dynamic_setting('AI_SYSTEM_PROMPT', DEFAULT_SYSTEM_PROMPT)
        full_conversation = [{"role": "system", "content": system_prompt_content}] + conversation

        first_response = get_ai_response(full_conversation)
        ai_response_json = first_response.json()
        
        response_message = ai_response_json["choices"][0]["message"]
        full_conversation.append(response_message)
        
        if response_message.get("tool_calls"):
            tool_results_messages = []
            for tool_call in response_message["tool_calls"]:
                function_name = tool_call["function"]["name"]
                function_args = json.loads(tool_call["function"]["arguments"])

                if function_name == "query_database":
                    tool_result = query_database(sql_query=function_args.get("sql_query"))
                    tool_results_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": tool_result
                    })
            
            full_conversation.extend(tool_results_messages)

            final_response = get_ai_response(full_conversation)
            final_json = final_response.json()
            content = final_json["choices"][0]["message"]["content"]
            return content
        else:
            return response_message.get("content", "")

    except Exception as e:
        debug_info = "No proxy info available."
        try:
            system_proxies = getproxies()
            filtered_proxies = {k: v for k, v in system_proxies.items() if isinstance(v, str) and v.startswith(('http://', 'https://'))}
            debug_info = f"SystemProxies: {system_proxies}, FilteredProxies: {filtered_proxies}"
        except Exception as proxy_e:
            debug_info = f"Could not get proxy info: {proxy_e}"
            
        return f"请求AI服务时出错: {str(e)}. Debug: {debug_info}"
