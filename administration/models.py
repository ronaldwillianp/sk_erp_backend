from django.db import models
from django.contrib.auth.models import AbstractUser
from configuration.models import Province, Municipality

# Create your models here.

class User(AbstractUser):
    ci = models.CharField(max_length=11, unique=True, help_text="Carnet de Identidad")
    address = models.CharField(max_length=255, blank=True, default='')
    province = models.ForeignKey(Province, on_delete=models.PROTECT, null=True, blank=True)
    municipality = models.ForeignKey(Municipality, on_delete=models.PROTECT, null=True, blank=True)
    contact = models.CharField(max_length=8, blank=True, default='')
    
    def __str__(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return f"{self.username} | {full_name}" if full_name else self.username     
        