from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.http import FileResponse, Http404
from datetime import datetime
from .db_connection import (
    staff_users_collection,
    clients_collection,
    requests_collection,
    production_orders_collection,
    production_log_collection,
    reject_log_collection,
)
from bson import ObjectId
import os
from django.conf import settings


# ============================================================
# HELPERS
# ============================================================

def get_session_ctx(request):
    """Context untuk info user yang login — dipakai di semua render admin."""
    return {
        "logged_username": request.session.get("user_username", "Admin"),
        "logged_display":  request.session.get("user_display",  "Admin"),
        "logged_role":     request.session.get("user_role",     "admin"),
    }


def notif(request, level, msg):
    """Kirim notifikasi Django messages."""
    if level == "success":
        messages.success(request, msg)
    elif level == "error":
        messages.error(request, msg)
    else:
        messages.warning(request, msg)


def to_id(doc):
    """Tambah field 'id' (string) ke setiap document MongoDB."""
    if doc:
        doc["id"] = str(doc["_id"])
    return doc


def safe_object_id(id_str):
    """Konversi string ke ObjectId, return None jika invalid."""
    try:
        return ObjectId(id_str)
    except Exception:
        return None


# ============================================================
# PUBLIC PAGES
# ============================================================

def landing_page(request):
    return render(request, "Landing/index.html")


def login_view(request):
    return render(request, "Auth/index.html")


# ============================================================
# AUTH
# ============================================================

def login_process(request):
    if request.method != "POST":
        return render(request, "Auth/index.html")

    identifier = request.POST.get("username", "").strip()
    password   = request.POST.get("password", "")

    # Cek staff_users (admin / operator) — login pakai username
    user = staff_users_collection.find_one({"username": identifier})
    if user:
        if check_password(password, user["password"]):
            role = user.get("role", "operator")
            request.session["user_id"]       = str(user["_id"])
            request.session["user_username"]  = user["username"]
            request.session["user_role"]      = role
            request.session["user_display"]   = user.get("display_name", user["username"])
            return redirect("admin_page" if role == "admin" else "operator_page")
        return render(request, "Auth/index.html", {"error": "Password salah"})

    # Cek client — login pakai email
    client = clients_collection.find_one({"email": identifier})
    if client:
        if check_password(password, client["password"]):
            request.session["user_id"]       = str(client["_id"])
            request.session["user_username"]  = client["email"]
            request.session["user_role"]      = "client"
            request.session["user_display"]   = (
                f"{client.get('nama_depan', '')} {client.get('nama_belakang', '')}".strip()
                or client["email"]
            )
            return redirect("client_page")
        return render(request, "Auth/index.html", {"error": "Password salah"})

    return render(request, "Auth/index.html", {"error": "Akun tidak ditemukan"})


def logout_view(request):
    request.session.flush()
    return redirect("login")


def register(request):
    if request.method == "POST":
        nama_depan    = request.POST.get("nama_depan", "").strip()
        nama_belakang = request.POST.get("nama_belakang", "").strip()
        email         = request.POST.get("email", "").strip()
        company       = request.POST.get("company_name", "").strip()
        password      = request.POST.get("password", "")

        if clients_collection.find_one({"email": email}):
            messages.error(request, "Email sudah digunakan.")
            return render(request, "Auth/index.html", {"open_register": True})

        clients_collection.insert_one({
            "nama_depan":    nama_depan,
            "nama_belakang": nama_belakang,
            "company_name":  company,
            "email":         email,
            "password":      make_password(password),
            "created_at":    datetime.now(),
        })
        messages.success(request, f"Akun berhasil dibuat! Selamat datang, {nama_depan}.")
        return redirect("login")

    return render(request, "Auth/index.html")


# ============================================================
# ADMIN — MAIN PAGE (semua tab dalam 1 view)
# ============================================================

def admin_page(request):

    # ── staff_users ──────────────────────────────────────
    users = []
    for u in staff_users_collection.find().sort("created_at", -1):
        to_id(u)
        users.append(u)

    # ── requests + join info client ───────────────────────
    reqs = []
    for r in requests_collection.find().sort("created_at", -1):
        to_id(r)
        # Cari info client berdasarkan client_id
        client_name  = "—"
        company_name = "—"
        if r.get("client_id"):
            oid = safe_object_id(r["client_id"])
            if oid:
                c = clients_collection.find_one({"_id": oid})
                if c:
                    client_name  = f"{c.get('nama_depan', '')} {c.get('nama_belakang', '')}".strip() or "—"
                    company_name = c.get("company_name", "—") or "—"
        r["client_name"]  = client_name
        r["company_name"] = company_name
        reqs.append(r)

    total_req    = len(reqs)
    pending_req  = sum(1 for r in reqs if r.get("status") == "pending")
    approved_req = sum(1 for r in reqs if r.get("status") == "approved")
    rejected_req = sum(1 for r in reqs if r.get("status") == "rejected")

    # ── production_orders + join operator + join request ──
    wos = []
    for wo in production_orders_collection.find().sort("created_at", -1):
        to_id(wo)
        # Nama operator
        op_name = "—"
        if wo.get("assigned_to"):
            oid = safe_object_id(wo["assigned_to"])
            if oid:
                op = staff_users_collection.find_one({"_id": oid})
                op_name = op["username"] if op else "—"
        wo["operator_name"] = op_name
        wos.append(wo)

    total_wo  = len(wos)
    active_wo = sum(1 for wo in wos if wo.get("status") in ["active", "in_progress"])

    # ── production_log
    #    Field: id, request_id, operator_id, quantity_done, date, note
    # ─────────────────────────────────────────────────────
    prod_logs = []
    for pl in production_log_collection.find().sort("date", -1):
        to_id(pl)

        # Nama operator
        op_name = "—"
        if pl.get("operator_id"):
            oid = safe_object_id(pl["operator_id"])
            if oid:
                op = staff_users_collection.find_one({"_id": oid})
                op_name = op["username"] if op else str(pl["operator_id"])
        pl["operator_name"] = op_name

        # Info request (nama produk)
        product_name = "—"
        if pl.get("request_id"):
            oid = safe_object_id(pl["request_id"])
            if oid:
                req = requests_collection.find_one({"_id": oid})
                product_name = req.get("product_name", "—") if req else "—"
        pl["product_name"] = product_name

        prod_logs.append(pl)

    total_produced = sum(int(pl.get("quantity_done", 0) or 0) for pl in prod_logs)

    # ── reject_log
    #    Field: id, request_id, quantity_reject, reason, date
    # ─────────────────────────────────────────────────────
    reject_logs = []
    for rl in reject_log_collection.find().sort("date", -1):
        to_id(rl)

        # Info request (nama produk)
        product_name = "—"
        if rl.get("request_id"):
            oid = safe_object_id(rl["request_id"])
            if oid:
                req = requests_collection.find_one({"_id": oid})
                product_name = req.get("product_name", "—") if req else "—"
        rl["product_name"] = product_name

        reject_logs.append(rl)

    total_reject = sum(int(rl.get("quantity_reject", 0) or 0) for rl in reject_logs)
    reject_rate  = round(total_reject / total_produced * 100, 1) if total_produced else 0

    # ── clients ──────────────────────────────────────────
    clients_list = []
    for c in clients_collection.find().sort("created_at", -1):
        to_id(c)
        clients_list.append(c)

    # ── operators (untuk dropdown assign di production_orders) ──
    operators = []
    for op in staff_users_collection.find({"role": "operator"}):
        to_id(op)
        operators.append(op)

    # ── build context ──────────────────────────────────
    ctx = {
        **get_session_ctx(request),
        "active_tab":     request.GET.get("tab", "dashboard"),
        # users
        "users":          users,
        # requests
        "requests":       reqs,
        "total_req":      total_req,
        "pending_req":    pending_req,
        "approved_req":   approved_req,
        "rejected_req":   rejected_req,
        # production orders
        "work_orders":    wos,
        "total_wo":       total_wo,
        "active_wo":      active_wo,
        "operators":      operators,
        # production log
        "prod_logs":      prod_logs,
        "total_produced": total_produced,
        # reject log
        "reject_logs":    reject_logs,
        "total_reject":   total_reject,
        "reject_rate":    reject_rate,
        # clients
        "clients":        clients_list,
    }
    return render(request, "admin/admin.html", ctx)


# ============================================================
# USER CRUD  →  collection: staff_users
# ============================================================

def user_create(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()
        role     = request.POST.get("role", "operator")

        if not username or not password:
            notif(request, "error", "Username dan password wajib diisi.")
        elif staff_users_collection.find_one({"username": username}):
            notif(request, "error", f"Username '{username}' sudah digunakan.")
        else:
            staff_users_collection.insert_one({
                "username":   username,
                "password":   make_password(password),
                "role":       role,
                "created_at": datetime.now(),
            })
            notif(request, "success", f"User '{username}' berhasil ditambahkan sebagai {role}.")

    return redirect("/admin-page/?tab=users")


def user_update(request, id):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        role     = request.POST.get("role", "operator")
        data     = {"username": username, "role": role}
        pw       = request.POST.get("password", "").strip()
        if pw:
            data["password"] = make_password(pw)

        oid = safe_object_id(id)
        if oid:
            staff_users_collection.update_one({"_id": oid}, {"$set": data})
            notif(request, "success", f"User '{username}' berhasil diperbarui.")
        else:
            notif(request, "error", "ID user tidak valid.")

    return redirect("/admin-page/?tab=users")


def user_delete(request, id):
    oid = safe_object_id(id)
    if oid:
        u     = staff_users_collection.find_one({"_id": oid})
        uname = u["username"] if u else "User"
        staff_users_collection.delete_one({"_id": oid})
        notif(request, "success", f"User '{uname}' berhasil dihapus.")
    else:
        notif(request, "error", "ID user tidak valid.")
    return redirect("/admin-page/?tab=users")


# ============================================================
# REQUEST ACTIONS  →  collection: requests
# ============================================================

def request_approve(request, id):
    """
    Admin approve request:
    1. Update status requests → 'approved'
    2. Buat production_orders baru otomatis
    """
    if request.method == "POST":
        oid = safe_object_id(id)
        if not oid:
            notif(request, "error", "ID request tidak valid.")
            return redirect("/admin-page/?tab=requests")

        req = requests_collection.find_one({"_id": oid})
        if not req:
            notif(request, "error", "Request tidak ditemukan.")
            return redirect("/admin-page/?tab=requests")

        if req.get("status") != "pending":
            notif(request, "warning", "Hanya request berstatus 'pending' yang bisa di-approve.")
            return redirect("/admin-page/?tab=requests")

        # Update status request
        requests_collection.update_one(
            {"_id": oid},
            {"$set": {
                "status":      "approved",
                "admin_note":  "",
                "approved_at": datetime.now(),
            }},
        )

        # Buat production_order otomatis
        production_orders_collection.insert_one({
            "request_id":   id,            # simpan sebagai string (sesuai referensi)
            "product_name": req.get("product_name", "—"),
            "quantity":     req.get("quantity", 0),
            "assigned_to":  None,
            "status":       "pending",
            "start_date":   None,
            "end_date":     None,
            "created_at":   datetime.now(),
        })

        prod_name = req.get("product_name", "—")
        notif(request, "success",
              f"Request '{prod_name}' disetujui. Production Order otomatis dibuat.")

    return redirect("/admin-page/?tab=requests")


def request_reject(request, id):
    """
    Admin reject request:
    1. Validasi admin_note wajib diisi
    2. Update status requests → 'rejected' + simpan admin_note
    """
    if request.method == "POST":
        admin_note = request.POST.get("admin_note", "").strip()

        oid = safe_object_id(id)
        if not oid:
            notif(request, "error", "ID request tidak valid.")
            return redirect("/admin-page/?tab=requests")

        req = requests_collection.find_one({"_id": oid})
        if not req:
            notif(request, "error", "Request tidak ditemukan.")
            return redirect("/admin-page/?tab=requests")

        if not admin_note:
            notif(request, "error", "Alasan penolakan wajib diisi.")
            return redirect("/admin-page/?tab=requests")

        if req.get("status") != "pending":
            notif(request, "warning", "Hanya request berstatus 'pending' yang bisa di-reject.")
            return redirect("/admin-page/?tab=requests")

        requests_collection.update_one(
            {"_id": oid},
            {"$set": {
                "status":      "rejected",
                "admin_note":  admin_note,
                "rejected_at": datetime.now(),
            }},
        )

        prod_name = req.get("product_name", "—")
        notif(request, "success", f"Request '{prod_name}' ditolak. Alasan: {admin_note}")

    return redirect("/admin-page/?tab=requests")


def request_download(request, id):
    """Download file gambar teknik yang diupload client."""
    oid = safe_object_id(id)
    if not oid:
        raise Http404("ID tidak valid")

    req = requests_collection.find_one({"_id": oid})
    if not req:
        raise Http404("Request tidak ditemukan")

    file_path = req.get("drawing_file")
    if not file_path:
        raise Http404("File gambar teknik tidak tersedia untuk request ini")

    full_path = os.path.join(settings.BASE_DIR, "media", file_path)
    if not os.path.exists(full_path):
        raise Http404("File tidak ditemukan di server. Mungkin sudah dihapus.")

    return FileResponse(
        open(full_path, "rb"),
        as_attachment=True,
        filename=os.path.basename(full_path),
    )


# ============================================================
# PRODUCTION ORDER ACTIONS  →  collection: production_orders
# ============================================================

def po_assign(request, id):
    """
    Admin assign operator ke production order & update status/jadwal.
    Field yang bisa diupdate: assigned_to, status, start_date, end_date
    """
    if request.method == "POST":
        oid = safe_object_id(id)
        if not oid:
            notif(request, "error", "ID production order tidak valid.")
            return redirect("/admin-page/?tab=workorders")

        data = {"status": request.POST.get("status", "active")}

        operator_id = request.POST.get("operator_id", "").strip()
        start_date  = request.POST.get("start_date", "").strip()
        end_date    = request.POST.get("end_date", "").strip()

        if operator_id:
            data["assigned_to"] = operator_id
        if start_date:
            data["start_date"] = start_date
        if end_date:
            data["end_date"] = end_date

        production_orders_collection.update_one({"_id": oid}, {"$set": data})
        notif(request, "success", "Production Order berhasil diperbarui.")

    return redirect("/admin-page/?tab=workorders")


# ============================================================
# OPERATOR PAGE
# ============================================================

def operator_page(request):
    return render(request, "operator/operator.html")


# ============================================================
# CLIENT PAGE
# ============================================================

def client_page(request):
    if request.method == "POST":
        product_name = request.POST.get("product_name", "").strip()
        quantity     = request.POST.get("quantity", 0)
        description  = request.POST.get("description", "").strip()
        drawing_file = request.FILES.get("drawing_file")

        # Simpan file gambar teknik
        file_path = None
        if drawing_file:
            upload_dir = os.path.join(settings.BASE_DIR, "media", "requests")
            os.makedirs(upload_dir, exist_ok=True)
            # Hindari nama file yang konflik
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
            safe_name = timestamp + drawing_file.name
            file_path = os.path.join("requests", safe_name)
            full_path = os.path.join(settings.BASE_DIR, "media", file_path)
            with open(full_path, "wb+") as f:
                for chunk in drawing_file.chunks():
                    f.write(chunk)

        # Simpan request ke database
        requests_collection.insert_one({
            "client_id":    request.session.get("user_id", ""),
            "product_name": product_name,
            "quantity":     int(quantity),
            "drawing_file": file_path,   # field: drawing_file (path relatif dari /media/)
            "description":  description,
            "status":       "pending",
            "admin_note":   "",
            "created_at":   datetime.now(),
        })

        messages.success(request, f'Request "{product_name}" berhasil dikirim! Menunggu review admin.')
        return redirect("client_page")

    return render(request, "client/client.html")