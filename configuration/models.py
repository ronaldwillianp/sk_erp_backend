from django.db import models
# from django.utils.text import slugify

# Create your models here.

class Company(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slogan = models.CharField(max_length=150)
    email = models.EmailField(max_length=50, unique=True)
    phone = models.CharField(max_length=15, unique=True)
    address = models.CharField(max_length=100)
    logo = models.ImageField(upload_to='company_logos/', null=True, blank=True)

class Category(models.Model):
    CATEGORY_TYPES = [
        ('INCOME', 'Ingreso'),
        ('EXPENSE', 'Gasto'),
        ('PRODUCT', 'Producto'),
    ]
    
    name = models.CharField(max_length=50)
    category_type = models.CharField(max_length=10, choices=CATEGORY_TYPES)
    parent = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='children'
    )
    description = models.CharField(max_length=100, blank=True)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = 'Categories'
        unique_together = ('name', 'category_type', 'parent')


class Province(models.Model):
    name = models.CharField(max_length=50, unique=True)
    short_name = models.CharField(max_length=5)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.short_name} | {self.name}"
        

class Municipality(models.Model):
    province = models.ForeignKey(Province, on_delete=models.PROTECT, related_name='municipalities')
    name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=5)

    class Meta:
        # Esto asegura que no haya dos municipios con el mismo nombre DENTRO de la misma provincia
        unique_together = ('name', 'province') 

    def __str__(self):
        return f"{self.province.short_name} | {self.name}"

class MeasureUnit(models.Model):
    name = models.CharField(max_length=16)
    short_name = models.CharField(max_length=4)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.short_name} | {self.name}"
        
    class Meta:
        ordering = ['name']

class Currency(models.Model):
    name = models.CharField(max_length=16)
    short_name = models.CharField(max_length=4)
    default = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True) 

    def __str__(self):
         return f"{self.short_name} | {self.name}"

class PaymentMethod(models.Model):
    name = models.CharField(max_length=25)
    description = models.CharField(max_length=50)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name}"
