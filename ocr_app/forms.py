from django import forms
from .models import BusinessCard

class BusinessCardForm(forms.ModelForm):
    class Meta:
        model = BusinessCard
        fields = ['name', 'email', 'phone', 'company', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'company': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company Name'}),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Address'
            }),
        }
        labels = {
            'name': 'Name',
            'email': 'Email',
            'phone': 'Phone',
            'company': 'Company',
            'address': 'Address',
        }
