from django.contrib import admin
from .models import SiteSetting

# 定义需要隐藏的敏感字段的key
SENSITIVE_KEYS = {'OPENAI_API_KEY', 'DEEPSEEK_API_KEY'} 

def mask_value(value, show_chars=4):
    """如果值很长，则隐藏它，只显示开头和结尾。"""
    if value and len(value) > show_chars * 2:
        return f"{value[:show_chars]}...{value[-show_chars:]}"
    return value

@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'masked_value')
    search_fields = ('key',)
    
    def masked_value(self, obj):
        """在列表视图中显示隐藏后的值。"""
        if obj.key in SENSITIVE_KEYS:
            return mask_value(obj.value)
        return obj.value
    masked_value.short_description = 'Value'

    def get_form(self, request, obj=None, **kwargs):
        """在编辑表单中处理值的显示。"""
        form = super().get_form(request, obj, **kwargs)
        if obj and obj.key in SENSITIVE_KEYS:
            # 预填充表单字段为隐藏后的值
            form.base_fields['value'].initial = mask_value(obj.value)
        return form

    def save_model(self, request, obj, form, change):
        """在保存时决定是否更新值。"""
        # 如果是敏感字段且值没有改变（仍然是隐藏格式），则不更新它
        if obj.key in SENSITIVE_KEYS and form.cleaned_data['value'] == mask_value(obj.value):
            # 值没有被用户修改，所以我们什么都不做来保留原始值
            # 注意：我们不调用 super().save_model() 来跳过保存过程
            # 但这会导致一个问题：如果其他字段被修改了，它们也不会被保存
            # 一个更好的方法是只恢复'value'字段
            
            # 重新从数据库获取原始对象以确保我们有未修改的值
            original_obj = SiteSetting.objects.get(pk=obj.pk)
            obj.value = original_obj.value # 将值重置为原始值
            
        super().save_model(request, obj, form, change)
