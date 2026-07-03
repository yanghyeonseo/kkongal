from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class User(AbstractUser):
    email = models.EmailField(max_length=128, blank=True)
    age = models.IntegerField(null=True, blank=True)
    job = models.CharField(max_length=128, blank=True)
    gender = models.CharField(max_length=32, blank=True)
    onboarded = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"id={self.id}, username={self.username}"
    

class Interest(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, related_name="interests")
    keyword = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    priority = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.keyword