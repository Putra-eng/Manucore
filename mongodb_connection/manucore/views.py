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
    return {
        "logged_username": request.session.get("user_username", "Admin"),
        "logged_display":  request.session.get("user_display",  "Admin"),
        "logged_role":     request.session.get("user_role",     "admin"),
    }


def notif(request, level, msg):
    if level == "success":
        messages.success(request, msg)
    elif level == "error":
        messages.error(request, msg)
    else:
        messages.warning(request, msg)


def rid(doc):
    doc["id"] = str(doc["_id"])
    return doc


# ============================================================
# PUBLIC
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

    # staff_users
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

    # client
    client = clients_collection.find_one({"email": identifier})
    if client:
        if check_password(password, client["password"]):
            request.session["user_id"]       = str(client["_id"])
            request.session["user_username"]  = client["email"]
            request.session["user_role"]      = "client"
            request.session["user_display"]   = (
                f"{client.get('nama_depan','')} {client.get('nama_belakang','')}".strip()
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
# ADMIN PAGE  (semua tab dalam 1 view)
# ============================================================

def admin_page(request):
    # staff_users
    users = [rid(u) for u in staff_users_collection.find()]

    # requests + join client
    reqs = []
    for r in requests_collection.find().sort("created_at", -1):
        rid(r)
        try:
            c = clients_collection.find_one({"_id": ObjectId(r["client_id"])}) if r.get("client_id") else None
            r["client_name"]  = f"{c.get('nama_depan','')} {c.get('nama_belakang','')}".strip() if c else "—"
            r["company_name"] = c.get("company_name", "—") if c else "—"
        except Exception:
            r["client_name"]  = "—"
            r["company_name"] = "—"
        reqs.append(r)

    total_req    = len(reqs)
    pending_req  = sum(1 for r in reqs if r.get("status") == "pending")
    approved_req = sum(1 for r in reqs if r.get("status") == "approved")
    rejected_req = sum(1 for r in reqs if r.get("status") == "rejected")

    # production_orders + join operator
    wos = []
    for wo in production_orders_collection.find().sort("created_at", -1):
        rid(wo)
        try:
            op = staff_users_collection.find_one({"_id": ObjectId(wo["assigned_to"])}) if wo.get("assigned_to") else None
            wo["operator_name"] = op["username"] if op else "—"
        except Exception:
            wo["operator_name"] = "—"
        wos.append(wo)

    total_wo  = len(wos)
    active_wo = sum(1 for wo in wos if wo.get("status") in ["active", "in_progress"])

    # production_log
    prod_logs = []
    for pl in production_log_collection.find().sort("date", -1):
        rid(pl)
        try:
            op = staff_users_collection.find_one({"_id": ObjectId(pl["operator_id"])}) if pl.get("operator_id") else None
            pl["operator_name"] = op["username"] if op else pl.get("operator_id", "—")
        except Exception:
            pl["operator_name"] = "—"
        prod_logs.append(pl)
    total_produced = sum(pl.get("quantity_done", 0) for pl in prod_logs)

    # reject_log
    reject_logs  = [rid(rl) for rl in reject_log_collection.find().sort("date", -1)]
    total_reject = sum(rl.get("quantity_reject", 0) for rl in reject_logs)
    reject_rate  = round(total_reject / total_produced * 100, 1) if total_produced else 0

    # clients
    clients_list = [rid(c) for c in clients_collection.find().sort("created_at", -1)]

    # operators untuk dropdown
    operators = [rid(op) for op in staff_users_collection.find({"role": "operator"})]

    ctx = {
        **get_session_ctx(request),
        "active_tab":     request.GET.get("tab", "dashboard"),
        "users":          users,
        "requests":       reqs,
        "total_req":      total_req,
        "pending_req":    pending_req,
        "approved_req":   approved_req,
        "rejected_req":   rejected_req,
        "work_orders":    wos,
        "total_wo":       total_wo,
        "active_wo":      active_wo,
        "operators":      operators,
        "prod_logs":      prod_logs,
        "total_produced": total_produced,
        "reject_logs":    reject_logs,
        "total_reject":   total_reject,
        "reject_rate":    reject_rate,
        "clients":        clients_list,
    }
    return render(request, "admin/admin.html", ctx)


# ============================================================
# USER CRUD  (collection: staff_users)
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
        staff_users_collection.update_one({"_id": ObjectId(id)}, {"$set": data})
        notif(request, "success", f"User '{username}' berhasil diperbarui.")
    return redirect("/admin-page/?tab=users")


def user_delete(request, id):
    u     = staff_users_collection.find_one({"_id": ObjectId(id)})
    uname = u["username"] if u else "User"
    staff_users_collection.delete_one({"_id": ObjectId(id)})
    notif(request, "success", f"User '{uname}' berhasil dihapus.")
    return redirect("/admin-page/?tab=users")


# ============================================================
# REQUEST ACTIONS  (collection: requests)
# ============================================================

def request_approve(request, id):
    if request.method == "POST":
        req = requests_collection.find_one({"_id": ObjectId(id)})
        if not req:
            notif(request, "error", "Request tidak ditemukan.")
            return redirect("/admin-page/?tab=requests")
        requests_collection.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"status": "approved", "admin_note": "", "approved_at": datetime.now()}},
        )
        production_orders_collection.insert_one({
            "request_id":   id,
            "product_name": req.get("product_name", "—"),
            "quantity":     req.get("quantity", 0),
            "assigned_to":  None,
            "status":       "pending",
            "start_date":   None,
            "end_date":     None,
            "created_at":   datetime.now(),
        })
        notif(request, "success",
              f"Request '{req.get('product_name','—')}' disetujui. Production Order otomatis dibuat.")
    return redirect("/admin-page/?tab=requests")


def request_reject(request, id):
    if request.method == "POST":
        admin_note = request.POST.get("admin_note", "").strip()
        req        = requests_collection.find_one({"_id": ObjectId(id)})
        if not req:
            notif(request, "error", "Request tidak ditemukan.")
            return redirect("/admin-page/?tab=requests")
        if not admin_note:
            notif(request, "error", "Alasan penolakan wajib diisi.")
            return redirect("/admin-page/?tab=requests")
        requests_collection.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"status": "rejected", "admin_note": admin_note, "rejected_at": datetime.now()}},
        )
        notif(request, "success", f"Request '{req.get('product_name','—')}' ditolak.")
    return redirect("/admin-page/?tab=requests")


def request_download(request, id):
    req = requests_collection.find_one({"_id": ObjectId(id)})
    if not req:
        raise Http404("Request tidak ditemukan")
    file_path = req.get("drawing_file")
    if not file_path:
        raise Http404("Tidak ada file")
    full = os.path.join(settings.BASE_DIR, "media", file_path)
    if not os.path.exists(full):
        raise Http404("File tidak ditemukan di server")
    return FileResponse(open(full, "rb"), as_attachment=True, filename=os.path.basename(full))


# ============================================================
# PRODUCTION ORDER ACTIONS  (collection: production_orders)
# ============================================================

def po_assign(request, id):
    if request.method == "POST":
        data = {"status": request.POST.get("status", "active")}
        op   = request.POST.get("operator_id", "").strip()
        sd   = request.POST.get("start_date", "")
        ed   = request.POST.get("end_date", "")
        if op: data["assigned_to"] = op
        if sd: data["start_date"]  = sd
        if ed: data["end_date"]    = ed
        production_orders_collection.update_one({"_id": ObjectId(id)}, {"$set": data})
        notif(request, "success", "Production Order berhasil diperbarui.")
    return redirect("/admin-page/?tab=workorders")


# ============================================================
# OPERATOR & CLIENT
# ============================================================

def operator_page(request):
    return render(request, "operator/operator.html")

                               
def client_page(request):
    if request.method == "POST":
        product_name = request.POST.get("product_name", "").strip()
        quantity     = request.POST.get("quantity", 0)
        description  = request.POST.get("description", "").strip()
        drawing_file = request.FILES.get("drawing_file")
        file_path    = None
        if drawing_file:
            upload_dir = os.path.join(settings.BASE_DIR, "media", "requests")
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join("requests", drawing_file.name)
            with open(os.path.join(settings.BASE_DIR, "media", file_path), "wb+") as f:
                for chunk in drawing_file.chunks():
                    f.write(chunk)
        requests_collection.insert_one({
            "client_id":    request.session.get("user_id", ""),
            "product_name": product_name,
            "quantity":     int(quantity),
            "drawing_file": file_path,
            "description":  description,
            "status":       "pending",
            "admin_note":   "",
            "created_at":   datetime.now(),
        })
        messages.success(request, f'Request "{product_name}" berhasil dikirim!')
        return redirect("client_page")
    return render(request, "client/client.html")