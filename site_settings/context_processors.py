from .models import SiteSetting

def settings(request):
    settings = SiteSetting.objects.all()
    return {s.key: s.value for s in settings}
