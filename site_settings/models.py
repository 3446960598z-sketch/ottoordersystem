from django.db import models

class SiteSetting(models.Model):
    key = models.CharField(max_length=255, primary_key=True)
    value = models.TextField()

    def __str__(self):
        return self.key
