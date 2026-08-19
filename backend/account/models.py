from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class User(AbstractUser):
    email = models.EmailField(max_length=128, blank=True)
    # 고정·보편 필드: 대부분의 공지에서 '제약/자격'으로 작용하는 개인 배경.
    age = models.IntegerField(null=True, blank=True)
    job = models.CharField(max_length=128, blank=True)
    gender = models.CharField(max_length=32, blank=True)
    region = models.CharField(max_length=128, blank=True)
    bio = models.TextField(blank=True)  # 자유서술 catch-all: 정형 필드로 못 담는 맥락
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


class ProfileAttribute(models.Model):
    # Category 2: 도메인별로 달라지는 정보를 사용자가 직접 label+value 로 추가한다.
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, related_name="profile_attributes")
    label = models.CharField(max_length=64)    # 예: "학교", "직급", "가입 팬클럽"
    value = models.CharField(max_length=256)   # 예: "서울대학교", "과장", "OO 팬클럽"
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.label}: {self.value}"