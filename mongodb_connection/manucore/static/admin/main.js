  "use strict";
      // CURSOR
      const cur = document.getElementById("cursor"),
        ring = document.getElementById("cursorRing");
      let mx = 0,
        my = 0,
        rx = 0,
        ry = 0;
      document.addEventListener("mousemove", (e) => {
        mx = e.clientX;
        my = e.clientY;
        cur.style.left = mx + "px";
        cur.style.top = my + "px";
      });
      document.addEventListener("mouseover", (e) => {
        if (e.target.matches("a,button,input,.nav-item,.btn"))
          ring.classList.add("hovered");
      });
      document.addEventListener("mouseout", (e) => {
        if (e.target.matches("a,button,input,.nav-item,.btn"))
          ring.classList.remove("hovered");
      });
      (function a() {
        rx += (mx - rx) * 0.13;
        ry += (my - ry) * 0.13;
        ring.style.left = rx + "px";
        ring.style.top = ry + "px";
        requestAnimationFrame(a);
      })();
      // CLOCK
      function tick() {
        const n = new Date(),
          p = (v) => String(v).padStart(2, "0");
        document.getElementById("clock").textContent =
          p(n.getHours()) + ":" + p(n.getMinutes()) + ":" + p(n.getSeconds());
      }
      tick();
      setInterval(tick, 1000);
      // PAGE NAV
      const PAGES = [
        "dashboard",
        "requests",
        "workorders",
        "users",
        "clients",
        "prodlog",
        "rejectlog",
      ];
      const LABELS = {
        dashboard: "Dashboard",
        requests: "Requests",
        workorders: "Work Orders",
        users: "Users",
        clients: "Clients",
        prodlog: "Production Log",
        rejectlog: "Reject Logs",
      };
      function goto(id, navEl) {
        PAGES.forEach((p) => {
          const el = document.getElementById("p-" + p);
          if (el) el.style.display = "none";
        });
        const t = document.getElementById("p-" + id);
        if (t) t.style.display = "block";
        document
          .querySelectorAll(".nav-item")
          .forEach((a) => a.classList.remove("active"));
        if (navEl) navEl.classList.add("active");
        document.getElementById("bcCur").textContent = LABELS[id] || id;
        document
          .getElementById("content")
          .scrollTo({ top: 0, behavior: "smooth" });
      }
      // TABLE FILTER
      function ft(inp, tid) {
        const q = inp.value.toLowerCase();
        document.querySelectorAll("#" + tid + " tbody tr").forEach((r) => {
          r.style.display = r.textContent.toLowerCase().includes(q)
            ? ""
            : "none";
        });
      }
      // COUNTER ANIMATION
      window.addEventListener("load", () => {
        document.querySelectorAll(".sc-val[data-count]").forEach((el) => {
          const target = parseInt(el.dataset.count);
          const suffix = el.innerHTML.replace(/[\d]/g, "");
          let cur = 0;
          const step = Math.max(1, Math.ceil(target / 50));
          const t = setInterval(() => {
            cur = Math.min(cur + step, target);
            el.innerHTML = cur + suffix;
            if (cur >= target) clearInterval(t);
          }, 20);
        });
      });


function openCreate() {
  document.getElementById('user-modal').style.display = 'block';

  const form = document.getElementById('user-form');
  form.action = document.getElementById('user-create-url').value;

  document.getElementById('f-username').value = "";
  document.getElementById('f-password').value = "";
  document.getElementById('f-role').value = "operator";
}

function openEdit(id, username, role) {
  document.getElementById('user-modal').style.display = 'block';

  const form = document.getElementById('user-form');

  let updateUrl = document.getElementById('user-update-url').value;
  updateUrl = updateUrl.replace('ID_PLACEHOLDER', id);

  form.action = updateUrl;

  document.getElementById('f-username').value = username;
  document.getElementById('f-password').value = ""; // ❗ kosongin
  document.getElementById('f-role').value = role;
}

function closeModal() {
  document.getElementById('user-modal').style.display = 'none';
}