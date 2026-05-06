from django import forms

class RegisterForm(forms.Form):
    nama_depan = forms.CharField(max_length=100)
    nama_belakang = forms.CharField(max_length=100)
    email = forms.EmailField()
    company_name = forms.CharField(max_length=200)
    password = forms.CharField(widget=forms.PasswordInput)