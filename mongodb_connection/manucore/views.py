from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from datetime import datetime
from .db_connection import clients_collection, users_collection


def landing_page(request):
    return render(request, 'Landing/index.html')


def login_view(request):
    return render(request, 'Auth/index.html')

def admin_page(request):
    return render(request, "admin/admin.html")

def operator_page(request):
    return render(request, "operator/operator.html")

def client_page(request):
    return render(request, "client/client.html")


def register(request):
    print("masuk register")
    if request.method == "POST":
        print("masuk post")

        nama_depan   = request.POST.get("nama_depan")
        nama_belakang = request.POST.get("nama_belakang")
        email        = request.POST.get("email")
        company      = request.POST.get("company_name")
        password     = request.POST.get("password")

        # Cek email duplikat
        existing = clients_collection.find_one({"email": email})
        if existing:
            messages.error(request, "Email sudah digunakan. Silakan gunakan email lain.")
            return render(request, "Auth/index.html", {"open_register": True})

        # Simpan ke database
        data = {
            "nama_depan":   nama_depan,
            "nama_belakang": nama_belakang,
            "company_name": company,
            "email":        email,
            "password":     make_password(password),
            "created_at":   datetime.now()
        }
        clients_collection.insert_one(data)

        # Kirim pesan sukses ke halaman login
        messages.success(request, f"Akun berhasil dibuat! Selamat datang, {nama_depan}. Silakan masuk.")
        return redirect("login")

    return render(request, "Auth/index.html")


from django.contrib.auth.hashers import check_password

def login_process(request):
    print("LOGIN MASUK 🔥")
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        print("LOGIN ATTEMPT:", username)

        # 🔹 CEK KE USERS (ADMIN / OPERATOR)
        user = users_collection.find_one({"username": username})

        if user:
            if check_password(password, user["password"]):
                role = user.get("role")

                if role == "admin":
                    return redirect("admin_page")
                elif role == "operator":
                    return redirect("operator_page")

            else:
                return render(request, "Auth/index.html", {
                    "error": "Password salah"
                })

        # 🔹 CEK KE CLIENTS
        client = clients_collection.find_one({"email": username})

        if client:
            if check_password(password, client["password"]):
                return redirect("client_page")
            else:
                return render(request, "Auth/index.html", {
                    "error": "Password salah"
                })

        # ❌ GA KETEMU SAMA SEKALI
        return render(request, "Auth/index.html", {
            "error": "User tidak ditemukan"
        })

    return render(request, "Auth/index.html")