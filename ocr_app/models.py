from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

class BusinessCardManager(BaseUserManager):
    def create_user(self, email=None, phone=None, password=None, **extra_fields):
        if not email and not phone:
            raise ValueError("Email or phone must be provided")
        email = self.normalize_email(email) if email else None
        user = self.model(email=email, phone=phone, **extra_fields)

        # Use phone as default password if no password is provided
        default_password = password or (phone if phone else "set-me-now")
        user.set_password(default_password)
        user.save(using=self._db)
        return user
    def create_superuser(self, email, phone=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, phone, password, **extra_fields)



class BusinessCard(AbstractBaseUser, PermissionsMixin):
    # Login identifiers
    email = models.EmailField(unique=True, blank=True, null=True)
    phone = models.CharField(max_length=20, unique=True, blank=True, null=True)

    # Card fields
    image = models.ImageField(upload_to='cards/', blank=True, null=True)
    name = models.CharField(max_length=100, blank=True)
    company = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    extracted_text = models.TextField(blank=True)
    qr_image = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    # Permissions
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'  # Use email for login (can change to phone)
    REQUIRED_FIELDS = []

    objects = BusinessCardManager()

    def __str__(self):
        return self.name or f"Card {self.id}"
