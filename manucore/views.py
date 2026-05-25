from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.http import FileResponse, Http404
from datetime import datetime, date, timedelta
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
    """Context untuk info user yang login — dipakai di semua render."""
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
# ADMIN — MAIN PAGE
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

    # ── production_orders + join operator ──
    wos = []
    for wo in production_orders_collection.find().sort("created_at", -1):
        to_id(wo)
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

    # ── production_log ──────────────────────────────────
    prod_logs = []
    for pl in production_log_collection.find().sort("date", -1):
        to_id(pl)

        op_name = "—"
        if pl.get("operator_id"):
            oid = safe_object_id(pl["operator_id"])
            if oid:
                op = staff_users_collection.find_one({"_id": oid})
                op_name = op["username"] if op else str(pl["operator_id"])
        pl["operator_name"] = op_name

        product_name   = "—"
        total_quantity = 0
        progress_pct   = 0
        status         = "pending"

        if pl.get("request_id"):
            oid = safe_object_id(pl["request_id"])
            if oid:
                req = requests_collection.find_one({"_id": oid})
                if req:
                    product_name   = req.get("product_name", "—")
                    total_quantity = req.get("quantity", 0)
                    wo = production_orders_collection.find_one({"request_id": pl["request_id"]})
                    if wo:
                        total_done   = wo.get("quantity_done", pl.get("quantity_done", 0))
                        progress_pct = round((total_done / total_quantity * 100)) if total_quantity > 0 else 0
                        status       = wo.get("status", "pending")
                    else:
                        total_done   = pl.get("quantity_done", 0)
                        progress_pct = round((total_done / total_quantity * 100)) if total_quantity > 0 else 0

        pl["product_name"]   = product_name
        pl["total_quantity"] = total_quantity
        pl["progress_pct"]   = progress_pct
        pl["status"]         = status
        prod_logs.append(pl)

    total_produced = sum(int(pl.get("quantity_done", 0) or 0) for pl in prod_logs)

    # ── reject_log ──────────────────────────────────────
    reject_logs = []
    for rl in reject_log_collection.find().sort("date", -1):
        to_id(rl)
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

    # ── clients ─────────────────────────────────────────
    clients_list = []
    for c in clients_collection.find().sort("created_at", -1):
        to_id(c)
        clients_list.append(c)

    # ── operators (untuk dropdown assign) ───────────────
    operators = []
    for op in staff_users_collection.find({"role": "operator"}):
        to_id(op)
        operators.append(op)

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

        requests_collection.update_one(
            {"_id": oid},
            {"$set": {
                "status":      "approved",
                "admin_note":  "",
                "approved_at": datetime.now(),
            }},
        )

        # Buat production_order otomatis — pastikan client_id ikut disimpan
        production_orders_collection.insert_one({
            "request_id":   id,
            "client_id":    req.get("client_id", ""),   # <-- WAJIB untuk tracking client
            "product_name": req.get("product_name", "—"),
            "quantity":     req.get("quantity", 0),
            "quantity_done": 0,
            "progress":     0,
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

        reject_log_collection.insert_one({
            "request_id":      id,
            "quantity_reject": req.get("quantity", 0),
            "reason":          admin_note,
            "date":            datetime.now(),
        })

        prod_name = req.get("product_name", "—")
        notif(request, "success", f"Request '{prod_name}' ditolak. Alasan: {admin_note}")

    return redirect("/admin-page/?tab=requests")


def request_download(request, id):
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
    operator_id = request.session.get("user_id", "")

    if not operator_id:
        return redirect("login")

    # ── Work orders yang di-assign ke operator ini ──
    work_orders = []
    for wo in production_orders_collection.find({"assigned_to": operator_id}).sort("created_at", -1):
        to_id(wo)

        product_name   = "—"
        quantity       = 0
        drawing_file   = None
        request_id_str = None

        if wo.get("request_id"):
            oid = safe_object_id(wo["request_id"])
            if oid:
                req = requests_collection.find_one({"_id": oid})
                if req:
                    product_name   = req.get("product_name", "—")
                    quantity       = req.get("quantity", 0)
                    drawing_file   = req.get("drawing_file")
                    request_id_str = wo["request_id"]

        quantity_done = wo.get("quantity_done", 0)
        progress_pct  = round((quantity_done / quantity * 100)) if quantity > 0 else 0

        wo["product_name"]   = product_name
        wo["quantity"]       = quantity
        wo["quantity_done"]  = quantity_done
        wo["progress_pct"]   = progress_pct
        wo["drawing_file"]   = drawing_file
        wo["request_id_str"] = request_id_str
        work_orders.append(wo)

    # ── Production logs milik operator ini ──
    prod_logs = []
    for pl in production_log_collection.find({"operator_id": operator_id}).sort("date", -1):
        to_id(pl)
        product_name = "—"
        if pl.get("request_id"):
            oid = safe_object_id(pl["request_id"])
            if oid:
                req = requests_collection.find_one({"_id": oid})
                product_name = req.get("product_name", "—") if req else "—"
        pl["product_name"] = product_name
        prod_logs.append(pl)

    total_produced = sum(int(pl.get("quantity_done", 0) or 0) for pl in prod_logs)

    # ── Stats hari ini ──
    today             = date.today()
    tomorrow          = today + timedelta(days=1)
    today_dt          = datetime.combine(today, datetime.min.time())
    tomorrow_dt       = datetime.combine(tomorrow, datetime.min.time())

    units_produced_today = sum(
        int(pl.get("quantity_done", 0) or 0)
        for pl in prod_logs
        if pl.get("date") and pl["date"] >= today_dt and pl["date"] < tomorrow_dt
    )

    reject_count_today = sum(
        int(rl.get("quantity_reject", 0) or 0)
        for rl in reject_log_collection.find({
            "date": {"$gte": today_dt, "$lt": tomorrow_dt}
        })
    )

    work_orders_active_count = sum(
        1 for wo in work_orders
        if wo.get("status") in ["active", "in_progress", "pending"]
    )

    ctx = {
        **get_session_ctx(request),
        "work_orders":              work_orders,
        "work_orders_active_count": work_orders_active_count,
        "prod_logs":                prod_logs,
        "total_produced":           total_produced,
        "units_produced_today":     units_produced_today,
        "reject_count_today":       reject_count_today,
    }
    return render(request, "operator/operator.html", ctx)


# ============================================================
# PRODUCTION LOG  →  collection: production_log
# ============================================================

def production_log_create(request):
    if request.method == "POST":
        operator_id   = request.session.get("user_id", "")
        request_id    = request.POST.get("request_id", "").strip()
        quantity_done = request.POST.get("quantity_done", 0)
        note          = request.POST.get("note", "").strip()

        if not operator_id:
            notif(request, "error", "Session expired. Silahkan login kembali.")
            return redirect("login")

        if not request_id or not quantity_done:
            notif(request, "error", "Request ID dan quantity harus diisi.")
            return redirect("operator_page")

        try:
            quantity_done = int(quantity_done)
            if quantity_done <= 0:
                raise ValueError
        except (ValueError, TypeError):
            notif(request, "error", "Quantity tidak valid.")
            return redirect("operator_page")

        req_oid = safe_object_id(request_id)
        if not req_oid:
            notif(request, "error", "ID request tidak valid.")
            return redirect("operator_page")

        req = requests_collection.find_one({"_id": req_oid})
        if not req:
            notif(request, "error", "Request tidak ditemukan.")
            return redirect("operator_page")

        # Insert production log
        production_log_collection.insert_one({
            "request_id":    request_id,
            "operator_id":   operator_id,
            "quantity_done": quantity_done,
            "note":          note,
            "date":          datetime.now(),
        })

        # Update production_order: accumulate quantity_done & recalc progress
        wo = production_orders_collection.find_one({"request_id": request_id})
        if wo:
            wo_qty = wo.get("quantity", 0)

            # Hitung total dari SEMUA log (bukan hanya log baru)
            all_logs     = list(production_log_collection.find({"request_id": request_id}))
            total_done   = sum(int(pl.get("quantity_done", 0) or 0) for pl in all_logs)
            progress_pct = round((total_done / wo_qty * 100)) if wo_qty > 0 else 0
            new_status   = "done" if total_done >= wo_qty else "in_progress"

            production_orders_collection.update_one(
                {"_id": wo["_id"]},
                {"$set": {
                    "quantity_done": total_done,
                    "progress":      progress_pct,
                    "status":        new_status,
                    "updated_at":    datetime.now(),
                }}
            )

        prod_name = req.get("product_name", "—")
        notif(request, "success",
              f"Log produksi '{prod_name}' — {quantity_done} unit berhasil dicatat.")

    return redirect("operator_page")


# ============================================================
# PRODUCTION ORDER STATUS UPDATE
# ============================================================

def update_production_status(request, id):
    if request.method == "POST":
        operator_id = request.session.get("user_id", "")
        status      = request.POST.get("status", "").strip()
        message     = request.POST.get("message", "").strip()

        if not operator_id:
            notif(request, "error", "Session expired. Silahkan login kembali.")
            return redirect("login")

        if not status or status not in ["pending", "in_progress", "paused", "done"]:
            notif(request, "error", "Status tidak valid.")
            return redirect("operator_page")

        wo_oid = safe_object_id(id)
        if not wo_oid:
            notif(request, "error", "ID production order tidak valid.")
            return redirect("operator_page")

        wo = production_orders_collection.find_one({"_id": wo_oid})
        if not wo:
            notif(request, "error", "Production order tidak ditemukan.")
            return redirect("operator_page")

        if wo.get("assigned_to") != operator_id:
            notif(request, "error", "Anda tidak memiliki akses ke production order ini.")
            return redirect("operator_page")

        update_data = {"status": status, "updated_at": datetime.now()}
        if message:
            update_data["operator_message"] = message

        production_orders_collection.update_one(
            {"_id": wo_oid},
            {"$set": update_data}
        )

        notif(request, "success", f"Status berhasil diperbarui ke '{status}'.")

    return redirect("operator_page")


# ============================================================
# FILE DOWNLOAD — untuk operator
# ============================================================

def request_download_operator(request, id):
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
        raise Http404("File tidak ditemukan di server.")

    return FileResponse(
        open(full_path, "rb"),
        as_attachment=True,
        filename=os.path.basename(full_path),
    )


# ============================================================
# REJECT LOG  →  collection: reject_log
# ============================================================

def reject_log_create(request):
    if request.method == "POST":
        operator_id     = request.session.get("user_id", "")
        request_id      = request.POST.get("request_id", "").strip()
        quantity_reject = request.POST.get("quantity_reject", 0)
        reason          = request.POST.get("reason", "").strip()

        if not operator_id:
            notif(request, "error", "Session expired. Silahkan login kembali.")
            return redirect("login")

        if not request_id or not quantity_reject or not reason:
            notif(request, "error", "Request ID, quantity, dan alasan harus diisi.")
            return redirect("operator_page")

        try:
            quantity_reject = int(quantity_reject)
            if quantity_reject <= 0:
                raise ValueError
        except (ValueError, TypeError):
            notif(request, "error", "Quantity tidak valid.")
            return redirect("operator_page")

        req_oid = safe_object_id(request_id)
        if not req_oid:
            notif(request, "error", "ID request tidak valid.")
            return redirect("operator_page")

        req = requests_collection.find_one({"_id": req_oid})
        if not req:
            notif(request, "error", "Request tidak ditemukan.")
            return redirect("operator_page")

        reject_log_collection.insert_one({
            "request_id":      request_id,
            "quantity_reject": quantity_reject,
            "reason":          reason,
            "date":            datetime.now(),
        })

        prod_name = req.get("product_name", "—")
        notif(request, "success",
              f"Log reject '{prod_name}' — {quantity_reject} unit berhasil dicatat.")

    return redirect("operator_page")


# ============================================================
# CLIENT PAGE  →  3 tab: Pemesanan, Riwayat, Progres
# ============================================================

def client_page(request):
    client_id = request.session.get("user_id", "")

    if not client_id:
        return redirect("login")

    # ── Handle POST: buat request baru ──────────────────
    if request.method == "POST":
        product_name = request.POST.get("product_name", "").strip()
        quantity     = request.POST.get("quantity", 0)
        description  = request.POST.get("description", "").strip()
        drawing_file = request.FILES.get("drawing_file")

        if not product_name or not quantity:
            messages.error(request, "Nama produk dan jumlah wajib diisi.")
            return redirect("client_page")

        try:
            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, "Jumlah produk tidak valid.")
            return redirect("client_page")

        # Simpan file gambar teknik
        file_path = None
        if drawing_file:
            upload_dir = os.path.join(settings.BASE_DIR, "media", "requests")
            os.makedirs(upload_dir, exist_ok=True)
            timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S_")
            safe_name  = timestamp + drawing_file.name
            file_path  = os.path.join("requests", safe_name)
            full_path  = os.path.join(settings.BASE_DIR, "media", file_path)
            with open(full_path, "wb+") as f:
                for chunk in drawing_file.chunks():
                    f.write(chunk)

        requests_collection.insert_one({
            "client_id":    client_id,
            "product_name": product_name,
            "quantity":     quantity,
            "drawing_file": file_path,
            "description":  description,
            "status":       "pending",
            "admin_note":   "",
            "created_at":   datetime.now(),
        })

        messages.success(request, f'Request "{product_name}" berhasil dikirim! Menunggu review admin.')
        return redirect("client_page")

    # ── GET: ambil semua request milik client ini ────────
    orders = []
    for req in requests_collection.find({"client_id": client_id}).sort("created_at", -1):
        to_id(req)
        orders.append(req)

    # ── Ambil production orders milik client ini ─────────
    # Semua status ditampilkan agar client bisa pantau dari awal hingga selesai
    active_orders = []
    for po in production_orders_collection.find({
        "client_id": client_id,
        "status": {"$in": ["pending", "active", "in_progress", "paused", "done"]}
    }).sort("created_at", -1):
        to_id(po)

        # Hitung total quantity_done dari semua production_log
        request_id_str = po.get("request_id", "")
        quantity_done  = 0

        if request_id_str:
            for pl in production_log_collection.find({"request_id": request_id_str}):
                quantity_done += int(pl.get("quantity_done", 0) or 0)

        po["quantity_done"] = quantity_done

        total_qty = int(po.get("quantity", 1) or 1)
        po["progress_percent"] = min(100, int((quantity_done / total_qty) * 100)) if total_qty > 0 else 0

        active_orders.append(po)

    ctx = {
        **get_session_ctx(request),
        "orders":        orders,
        "active_orders": active_orders,
    }
    return render(request, "client/client.html", ctx)
