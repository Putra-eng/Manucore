from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from datetime import datetime
from .db_connection import clients_collection, users_collection, requests_collection
from .models import StaffUser
from bson import ObjectId

def landing_page(request):
    return render(request, 'Landing/index.html')

def login_view(request):
    return render(request, 'Auth/index.html')

def admin_page(request):
    users = list(users_collection.find())

    for u in users:
        u['id'] = str(u['_id'])

    return render(request, "admin/admin.html", {
        "users": users
    })
    
def operator_page(request):
    return render(request, "operator/operator.html")

def client_page(request):
    if request.method == "POST":
        nama_produk = request.POST.get("nama_produk")
        jumlah = request.POST.get("jumlah")
        spesifikasi = request.POST.get("spesifikasi", "")
        gambar = request.FILES.get("gambar")
        
        file_path = None
        if gambar:
            import os
            from django.conf import settings
            
            upload_dir = os.path.join(settings.BASE_DIR, 'media', 'requests')
            os.makedirs(upload_dir, exist_ok=True)
            
            file_path = os.path.join('requests', gambar.name)
            full_path = os.path.join(settings.BASE_DIR, 'media', file_path)
            
            with open(full_path, 'wb+') as destination:
                for chunk in gambar.chunks():
                    destination.write(chunk)
        
        request_data = {
            "nama_produk": nama_produk,
            "jumlah": int(jumlah),
            "spesifikasi": spesifikasi,
            "gambar_path": file_path,
            "status": "pending",
            "created_at": datetime.now()
        }
        
        requests_collection.insert_one(request_data)
        
        messages.success(request, f'Request "{nama_produk}" berhasil dikirim!')
        return redirect("client_page")
    
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


def user_list(request):
    users = list(users_collection.find())
    return render(request, 'admin/admin.html', {'users': users})


def user_create(request):
    if request.method == "POST":
        data = {
            "username": request.POST.get("username"),
            "password": make_password(request.POST.get("password")),
            "role": request.POST.get("role"),
            "created_at": datetime.now()
        }
        users_collection.insert_one(data)

        messages.success(request, "User berhasil ditambahkan")

    return redirect("admin_page")

def user_update(request, id):
    if request.method == "POST":
        update_data = {
            "username": request.POST.get("username"),
            "role": request.POST.get("role"),
        }

        password = request.POST.get("password")
        if password:
            update_data["password"] = make_password(password)

        users_collection.update_one(
            {"_id": ObjectId(id)},
            {"$set": update_data}
        )

        messages.success(request, "User berhasil diupdate")

    return redirect("admin_page")

def user_delete(request, id):
    users_collection.delete_one({"_id": ObjectId(id)})

    messages.success(request, "User berhasil dihapus")

    return redirect("admin_page")
