from django.apps import AppConfig

class ShopConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shop'
    verbose_name = '商店'

    def ready(self):
        # 导入并连接信号处理器
        import shop.signals
