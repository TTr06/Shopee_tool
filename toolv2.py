import asyncio
import json
import os
import random
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
import tkinter as tk
import customtkinter as ctk
import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR
from telethon import TelegramClient, events

# --- CẤU HÌNH API TELEGRAM & KÊNH MẶC ĐỊNH ---
API_ID = 35941628
API_HASH = "4ff2740f67c881028c1ae826a3765f47"
TARGET_CHANNEL = "xueshopee"
CONFIG_FILE = "config.json"
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class ShopeeCoinHunter(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Shopee Coin Hunter - Kịch Bản Tự Động Săn Xu (@xueshopee)")
        self.geometry("600 x 900")
        self.resizable(False, False)

        self.client = None
        self.loop = None
        self.phone_code_hash = None
        self.latest_messages = []
        self.opened_urls = set()

        # Trạng thái Auto
        self.auto_hunting_enabled = False
        self.auto_thread = None

        # Khởi tạo OCR & Template ảnh
        self.update_status_text = "Đang khởi tạo OCR..."
        self.ocr = RapidOCR()
        self.tpl_luu = None
        self.tpl_banner = None
        self.load_templates()

        # --- TIÊU ĐỀ ---
        self.title_label = ctk.CTkLabel(
            self,
            text="🎯 Shopee Coin Hunter (@xueshopee)",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.title_label.pack(pady=(12, 2))

        # Hiển thị kết nối ADB
        self.device_info_label = ctk.CTkLabel(
            self, text="Thiết bị ADB: Đang kiểm tra...", text_color="gray"
        )
        self.device_info_label.pack(pady=2)

        # --- KHUNG TỰ ĐỘNG SĂN XU THEO KỊCH BẢN ---
        self.auto_frame = ctk.CTkFrame(self, fg_color="#1A202C", corner_radius=10)
        self.auto_frame.pack(pady=8, padx=20, fill="x")

        self.auto_title = ctk.CTkLabel(
            self.auto_frame,
            text="⚡ KỊCH BẢN: VÀO SHOPEE ➔ NHẬN LINK ➔ PHẦN THƯỞNG ➔ Ô XU > 4P",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#F6E05E",
        )
        self.auto_title.pack(pady=(10, 4))

        self.auto_rules_label = ctk.CTkLabel(
            self.auto_frame,
            text="• 1. Vào app Shopee ➔ Nhận link Telegram (< 1p, nhiều xu & slot nhất)\n"
                 "• 2. Check biểu tượng 'PHẦN THƯỞNG': Không có ➔ Thoát app, vào lại Shopee ➔ Chuyển link\n"
                 "• 3. Check ô xu > 4 phút (loại bỏ lướt video): Không có ➔ Thoát app, vào lại ➔ Chuyển link\n"
                 "• 4. Có ô xu > 4p ➔ Đợi hết giờ đến khi hiện: 'Nhấn để nhận thưởng!'\n"
                 "• 5. Nhấn 'Lưu' (chống auto click) ➔ Đợi 3s ➔ Thoát Shopee ➔ Vào lại Shopee ➔ Link mới",
            font=ctk.CTkFont(size=11),
            text_color="#CBD5E0",
            justify="left",
        )
        self.auto_rules_label.pack(pady=(0, 8), padx=15, anchor="w")

        # Nút Bật/Tắt Auto & Nhãn trạng thái
        self.auto_btn_row = ctk.CTkFrame(self.auto_frame, fg_color="transparent")
        self.auto_btn_row.pack(fill="x", padx=15, pady=(0, 10))

        self.auto_toggle_btn = ctk.CTkButton(
            self.auto_btn_row,
            text="▶ BẬT TỰ ĐỘNG SĂN XU",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.toggle_auto_hunter,
            fg_color="#38A169",
            hover_color="#2F855A",
            height=38,
            width=200,
        )
        self.auto_toggle_btn.pack(side="left")

        self.auto_status_label = ctk.CTkLabel(
            self.auto_btn_row,
            text="⚪ Đang Tắt",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="gray",
            anchor="w",
        )
        self.auto_status_label.pack(side="left", padx=15, expand=True, fill="x")

        # --- KHUNG ĐĂNG NHẬP TELEGRAM ---
        self.login_frame = ctk.CTkFrame(self)
        self.login_frame.pack(pady=5, padx=20, fill="x")

        self.phone_row = ctk.CTkFrame(self.login_frame, fg_color="transparent")
        self.phone_row.pack(fill="x", padx=10, pady=(8, 4))

        self.phone_entry = ctk.CTkEntry(
            self.phone_row,
            placeholder_text="SĐT Telegram (+84...)...",
            height=32,
        )
        self.phone_entry.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.send_otp_btn = ctk.CTkButton(
            self.phone_row,
            text="📩 Lấy Mã OTP",
            command=self.request_otp,
            fg_color="#2B6CB0",
            hover_color="#2C5282",
            width=110,
            height=32,
        )
        self.send_otp_btn.pack(side="right")

        self.otp_row = ctk.CTkFrame(self.login_frame, fg_color="transparent")
        self.otp_row.pack(fill="x", padx=10, pady=(2, 4))

        self.otp_entry = ctk.CTkEntry(
            self.otp_row,
            placeholder_text="Mã OTP...",
            height=32,
            state="disabled",
        )
        self.otp_entry.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.verify_otp_btn = ctk.CTkButton(
            self.otp_row,
            text="✅ Xác Nhận OTP",
            command=self.submit_otp,
            fg_color="#38A169",
            hover_color="#2F855A",
            width=110,
            height=32,
            state="disabled",
        )
        self.verify_otp_btn.pack(side="right")

        self.logout_btn = ctk.CTkButton(
            self.login_frame,
            text="🚪 Đăng Xuất",
            command=self.logout,
            fg_color="#4A5568",
            hover_color="#2D3748",
            height=26,
            width=100,
        )
        self.logout_btn.pack(pady=(2, 6))

        # --- KHUNG HIỂN THỊ TIN NHẮN MỚI NHẤT ---
        self.msg_section_label = ctk.CTkLabel(
            self,
            text="📩 Tin nhắn mới nhất từ @xueshopee (Bấm để mở thủ công qua ADB):",
            font=ctk.CTkFont(weight="bold"),
        )
        self.msg_section_label.pack(anchor="w", padx=25, pady=(6, 2))

        self.cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.cards_frame.pack(pady=0, padx=20, fill="x")

        self.card_buttons = []
        for i in range(3):
            btn = ctk.CTkButton(
                self.cards_frame,
                text=f"[{i+1}] Đang chờ dữ liệu từ nhóm...",
                font=ctk.CTkFont(size=12),
                anchor="w",
                height=58,
                fg_color="#2D3748",
                hover_color="#4A5568",
                text_color="#E2E8F0",
                command=lambda idx=i: self.on_card_click(idx),
            )
            btn.pack(fill="x", pady=3)
            self.card_buttons.append(btn)

        # --- KHUNG NHẬP MỞ THỦ CÔNG ---
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.pack(pady=6, padx=20, fill="x")

        self.url_entry = ctk.CTkEntry(
            self.input_frame,
            placeholder_text="Hoặc dán link Shopee vào đây để mở thủ công...",
            height=32,
        )
        self.url_entry.pack(fill="x", padx=10, pady=6)
        self.setup_keyboard_shortcuts()

        self.open_btn = ctk.CTkButton(
            self,
            text="🚀 Mở Link Nhập Thủ Công",
            command=self.open_manual_link,
            height=34,
            font=ctk.CTkFont(weight="bold"),
            fg_color="#EE4D2D",
            hover_color="#D03E1F",
        )
        self.open_btn.pack(pady=2)

        # Trạng thái tổng quát
        self.status_label = ctk.CTkLabel(
            self, text="Sẵn sàng.", font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(pady=6)

        # 🚀 KHỞI TẠO ASYNCIO LOOP RIÊNG CHO TELEGRAM
        self.start_async_loop()

        # Khởi tạo dữ liệu người dùng & kiểm tra ADB
        self.check_adb_device()
        self.load_user_config()
        self.auto_connect_if_logged_in()
        self.refresh_message_ages()

    # --- TẢI MẪU ẢNH (TEMPLATES) ---
    def load_templates(self):
        luu_path = os.path.join(TEMPLATES_DIR, "btn_luu_target.png")
        if not os.path.exists(luu_path):
            luu_path = os.path.join(TEMPLATES_DIR, "btn_claim.png")
        if os.path.exists(luu_path):
            self.tpl_luu = cv2.imread(luu_path)

        banner_path = os.path.join(TEMPLATES_DIR, "phan_thuong_banner.png")
        if os.path.exists(banner_path):
            self.tpl_banner = cv2.imread(banner_path)

    # --- KHỞI TẠO ASYNCIO LOOP ---
    def start_async_loop(self):
        self.loop = asyncio.new_event_loop()

        def _run_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        threading.Thread(target=_run_loop, daemon=True).start()

    def refresh_message_ages(self):
        if self.latest_messages:
            self.update_cards_gui()
        self.after(1000, self.refresh_message_ages)

    # --- LƯU & TẢI USER ---
    def load_user_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    saved_phone = data.get("phone", "")
                    if saved_phone:
                        self.phone_entry.insert(0, saved_phone)
            except Exception:
                pass

    def save_user_config(self, phone):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"phone": phone}, f)
        except Exception:
            pass

    def auto_connect_if_logged_in(self):
        if os.path.exists("user_session.session"):
            self.update_status("🔄 Đang tự động kết nối lại session...", "white")
            self.send_otp_btn.configure(state="disabled")
            asyncio.run_coroutine_threadsafe(self._async_auto_login(), self.loop)

    async def _async_auto_login(self):
        try:
            self.client = TelegramClient("user_session", API_ID, API_HASH, loop=self.loop)
            await self.client.connect()
            if await self.client.is_user_authorized():
                me = await self.client.get_me()
                name = me.first_name or "Bạn"
                self.update_status(f"✅ Đã kết nối Telegram: {name}", "green")
                await self._start_listening_async()
            else:
                self.update_status("⚠️ Phiên đăng nhập hết hạn. Vui lòng lấy mã OTP mới.", "orange")
                self.after(0, lambda: self.send_otp_btn.configure(state="normal"))
        except Exception as e:
            self.update_status(f"❌ Lỗi tự động kết nối: {e}", "red")
            self.after(0, lambda: self.send_otp_btn.configure(state="normal"))

    def logout(self):
        if os.path.exists("user_session.session"):
            try:
                os.remove("user_session.session")
            except Exception:
                pass
        self.client = None
        self.otp_entry.delete(0, tk.END)
        self.otp_entry.configure(state="disabled")
        self.verify_otp_btn.configure(state="disabled")
        self.send_otp_btn.configure(state="normal")
        self.update_status("🚪 Đã đăng xuất.", "white")

    # --- GIAO DIỆN & PHÍM TẮT ---
    def setup_keyboard_shortcuts(self):
        self.url_entry.bind("<Control-a>", self.select_all_text)
        self.url_entry.bind("<Control-A>", self.select_all_text)
        self.url_entry.bind("<Return>", lambda event: self.open_manual_link())

    def select_all_text(self, event):
        event.widget.select_range(0, tk.END)
        event.widget.icursor(tk.END)
        return "break"

    def update_status(self, text, color="white"):
        self.after(0, lambda: self.status_label.configure(text=text, text_color=color))

    def update_auto_status(self, text, color="white"):
        self.after(0, lambda: self.auto_status_label.configure(text=text, text_color=color))

    # --- CÁC HÀM ADB ---
    def run_adb_cmd(self, command):
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return result.stdout.strip()
        except Exception:
            return None

    def check_adb_device(self):
        output = self.run_adb_cmd(["adb", "devices"])
        if output is None:
            self.device_info_label.configure(
                text="❌ Không tìm thấy công cụ ADB!", text_color="red"
            )
            return False

        lines = output.split("\n")[1:]
        devices = [
            line.split("\t")[0]
            for line in lines
            if line.endswith("device") and line.strip()
        ]
        if devices:
            self.device_info_label.configure(
                text=f"✅ Đã kết nối ADB: {devices[0]}", text_color="green"
            )
            return True
        else:
            self.device_info_label.configure(
                text="⚠️ Chưa kết nối thiết bị ADB!", text_color="orange"
            )
            return False

    def force_stop_shopee(self):
        """Thoát hoàn toàn ứng dụng Shopee"""
        self.run_adb_cmd(["adb", "shell", "am", "force-stop", "com.shopee.vn"])

    def launch_shopee_app(self):
        """Mở lại app Shopee vào màn hình chính"""
        self.run_adb_cmd([
            "adb", "shell", "monkey", "-p", "com.shopee.vn",
            "-c", "android.intent.category.LAUNCHER", "1"
        ])

    def open_url_via_adb(self, url):
        if not url:
            self.update_status("⚠️ Tin nhắn không chứa link Shopee hợp lệ!", "orange")
            return False

        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        adb_cmd = [
            "adb",
            "shell",
            "am",
            "start",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            url,
        ]
        output = self.run_adb_cmd(adb_cmd)
        if output and "Error" not in output:
            self.update_status(f"✅ [ADB OK] Đã mở: {url}", "green")
            return True
        else:
            self.update_status("❌ Gửi lệnh ADB thất bại!", "red")
            return False

    def capture_screen_cv2(self):
        """Chụp màn hình điện thoại siêu nhanh qua adb exec-out"""
        try:
            proc = subprocess.Popen(
                ["adb", "exec-out", "screencap", "-p"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            data, _ = proc.communicate(timeout=4)
            if data:
                return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            pass
        return None

    # --- CHỐNG AUTO CLICK: GIẢ LẬP NGÓN TAY NGƯỜI DÙNG ---
    def human_like_tap(self, cx, cy, bw=60, bh=25):
        """
        Thực hiện thao tác nhấn tự nhiên chống auto-click:
        - Tọa độ lệch ngẫu nhiên trong vùng nút
        - Độ trễ phản xạ ngẫu nhiên (human delay)
        - Thời gian tiếp xúc màn hình (touch duration) từ 90ms - 140ms
        - Độ rung ngón tay nhẹ (1-2px)
        """
        # 1. Trễ ngẫu nhiên trước khi nhấn
        time.sleep(random.uniform(0.35, 0.75))

        # 2. Lệch tọa độ ngẫu nhiên an toàn trong vùng nút
        max_dx = max(3, int(bw * 0.22))
        max_dy = max(2, int(bh * 0.22))
        rx = cx + random.randint(-max_dx, max_dx)
        ry = cy + random.randint(-max_dy, max_dy)

        # 3. Micro jitter (ngón tay tiếp xúc có độ xê dịch cực nhỏ)
        ex = rx + random.randint(-1, 1)
        ey = ry + random.randint(-1, 1)

        # 4. Thời gian giữ ngón tay (ms)
        press_duration = random.randint(90, 140)

        # Dùng lệnh swipe tọa độ điểm đầu và cuối cực ngắn để tạo cảm giác chạm giữ người thật
        self.run_adb_cmd([
            "adb", "shell", "input", "swipe",
            str(rx), str(ry), str(ex), str(ey), str(press_duration)
        ])

    # --- QUÉT VÙNG NHẬN XU (OCR + TEMPLATE) ---
    def scan_screen_for_coins(self, screen):
        """
        Quét khu vực góc trên bên phải của màn hình:
        - has_phan_thuong: Phát hiện có biểu tượng 'PHẦN THƯỞNG'
        - watching_tasks: Danh sách nhiệm vụ đếm ngược [{'time_str': '04:22', 'seconds': 262, 'is_gt_4m': True}, ...]
        - has_ready: Phát hiện có chữ 'Nhấn để nhận thưởng!'
        - luu_coords: (cx, cy, bw, bh) của nút 'Lưu' màu cam
        """
        if screen is None:
            return {
                "has_phan_thuong": False,
                "watching_tasks": [],
                "has_ready": False,
                "luu_coords": None,
            }

        h, w = screen.shape[:2]
        # ROI góc trên bên phải nơi ô nhận thưởng xuất hiện
        roi_y1, roi_y2 = int(h * 0.12), int(h * 0.65)
        roi_x1, roi_x2 = int(w * 0.40), w
        roi = screen[roi_y1:roi_y2, roi_x1:roi_x2]

        has_phan_thuong = False
        watching_tasks = []
        has_ready = False

        # 1. Kiểm tra Template Banner 'PHẦN THƯỞNG'
        if self.tpl_banner is not None:
            best_v_banner = -1
            scales = [1.85, 1.95, 2.05, 2.15, 2.25]
            for s in scales:
                resz = cv2.resize(self.tpl_banner, (0, 0), fx=s, fy=s)
                if resz.shape[0] > roi.shape[0] or resz.shape[1] > roi.shape[1]:
                    continue
                res = cv2.matchTemplate(roi, resz, cv2.TM_CCOEFF_NORMED)
                _, max_v, _, _ = cv2.minMaxLoc(res)
                if max_v > best_v_banner:
                    best_v_banner = max_v
            if best_v_banner >= 0.70:
                has_phan_thuong = True

        # 2. OCR nhận diện văn bản trong vùng ROI
        ocr_res, _ = self.ocr(roi)
        if ocr_res:
            for item in ocr_res:
                _, txt, conf = item
                raw_txt = txt.lower()
                clean = raw_txt.replace(" ", "")

                # Hỗ trợ nhận diện 'PHẦN THƯỞNG' qua OCR nếu có
                if "phan" in clean and ("thu" in clean or "th" in clean or "ng" in clean):
                    has_phan_thuong = True

                # Kiểm tra các dòng đếm ngược: 'Xem xx:xx...'
                if "xem" in raw_txt:
                    m = re.search(r"(\d{1,2})[:\.](\d{2})", txt)
                    if m:
                        mins = int(m.group(1))
                        secs = int(m.group(2))
                        total_s = mins * 60 + secs
                        watching_tasks.append({
                            "time_str": m.group(0),
                            "seconds": total_s,
                            "is_gt_4m": (total_s >= 240),
                            "raw_text": txt,
                        })

                # Kiểm tra dòng: 'Nhấn để nhận thưởng!'
                if "nhan" in raw_txt and "thuong" in raw_txt and ("de" in raw_txt or "!" in raw_txt):
                    if "xem" not in raw_txt:
                        has_ready = True

        # 3. Template matching tìm nút 'Lưu' màu cam
        luu_coords = None
        if self.tpl_luu is not None:
            best_v = -1
            best_loc = None
            best_scale = 1.0

            scales = np.linspace(0.85, 1.85, 11)
            for s in scales:
                resz = cv2.resize(self.tpl_luu, (0, 0), fx=s, fy=s)
                if resz.shape[0] > roi.shape[0] or resz.shape[1] > roi.shape[1]:
                    continue
                res = cv2.matchTemplate(roi, resz, cv2.TM_CCOEFF_NORMED)
                _, max_v, _, max_l = cv2.minMaxLoc(res)
                if max_v > best_v:
                    best_v = max_v
                    best_loc = max_l
                    best_scale = s

            if best_v >= 0.70:
                bx = best_loc[0] + roi_x1
                by = best_loc[1] + roi_y1
                bw = int(self.tpl_luu.shape[1] * best_scale)
                bh = int(self.tpl_luu.shape[0] * best_scale)
                cx = bx + bw // 2
                cy = by + bh // 2

                # Xác thực màu cam đặc trưng của nút Lưu
                if 0 <= cy < h and 0 <= cx < w:
                    b, g, r = screen[cy, cx]
                    if int(r) > 160 and int(r) > int(b) + 35:
                        luu_coords = (cx, cy, bw, bh)

        return {
            "has_phan_thuong": has_phan_thuong,
            "watching_tasks": watching_tasks,
            "has_ready": has_ready,
            "luu_coords": luu_coords,
        }

    # --- BÓC TÁCH LINK & THÔNG TIN ---
    def parse_coin_and_slots(self, text):
        coins = 0
        slots = 0
        if not text:
            return coins, slots

        coin_m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:k\s*)?(?:xu|coin)", text, re.IGNORECASE)
        if not coin_m:
            coin_m = re.search(r"(?:xu|coin)[\s:]*(\d+(?:[.,]\d+)?)", text, re.IGNORECASE)
        if coin_m:
            val = coin_m.group(1).replace(".", "").replace(",", "")
            try:
                coins = int(val)
                if "k" in coin_m.group(0).lower():
                    coins *= 1000
            except ValueError:
                coins = 0

        slot_m = re.search(
            r"(?:còn|con)?\s*(\d+)(?:/\d+)?\s*(?:lượt|luot|slot|turn|vé|ve|suất|suat)",
            text,
            re.IGNORECASE,
        )
        if not slot_m:
            slot_m = re.search(r"(?:lượt|luot|slot|còn|con)[\s:]*(\d+)", text, re.IGNORECASE)
        if slot_m:
            try:
                slots = int(slot_m.group(1))
            except ValueError:
                slots = 0

        return coins, slots

    def extract_shopee_url(self, text):
        if not text:
            return None
        urls = re.findall(r"(https?://[^\s]+)", text)
        for u in urls:
            clean = u.rstrip(" .,;!?)>")
            if any(k in clean for k in ["shopee.vn", "shp.ee", "vn.shp.ee", "s.shopee.vn"]):
                return clean
        return None

    def process_message_data(self, msg_obj):
        text = msg_obj.message or ""
        date = msg_obj.date
        coins, slots = self.parse_coin_and_slots(text)
        url = self.extract_shopee_url(text)

        if not url and msg_obj.entities:
            for ent, ent_text in msg_obj.get_entities_text():
                if hasattr(ent, "url") and ent.url:
                    if any(k in ent.url for k in ["shopee.vn", "shp.ee", "vn.shp.ee", "s.shopee.vn"]):
                        url = ent.url.rstrip(" .,;!?)>")
                        break

        return {
            "text": text,
            "date": date,
            "coins": coins,
            "slots": slots,
            "url": url,
        }

    # --- AUTO HUNTER WORKER (QUY TRÌNH CHÍNH THEO KỊCH BẢN) ---
    def toggle_auto_hunter(self):
        if not self.auto_hunting_enabled:
            self.auto_hunting_enabled = True
            self.auto_toggle_btn.configure(
                text="⏹ DỪNG TỰ ĐỘNG",
                fg_color="#E53E3E",
                hover_color="#C53030",
            )
            self.update_auto_status("🟢 Đang bật tự động săn xu...", "#48BB78")
            self.auto_thread = threading.Thread(target=self.auto_hunter_worker, daemon=True)
            self.auto_thread.start()
        else:
            self.auto_hunting_enabled = False
            self.auto_toggle_btn.configure(
                text="▶ BẬT TỰ ĐỘNG SĂN XU",
                fg_color="#38A169",
                hover_color="#2F855A",
            )
            self.update_auto_status("⚪ Đang Tắt", "gray")

    def auto_hunter_worker(self):
        # 1. Bắt đầu kịch bản: Vào app Shopee sẵn sàng
        self.update_auto_status("📱 Đang vào app Shopee sẵn sàng...", "#4299E1")
        self.launch_shopee_app()
        time.sleep(3.5)

        while self.auto_hunting_enabled:
            # 2. Kiểm tra ADB
            if not self.check_adb_device():
                self.update_auto_status("⚠️ ADB chưa kết nối thiết bị!", "orange")
                time.sleep(3)
                continue

            # 3. Kiểm tra tin nhắn Telegram
            if not self.latest_messages:
                self.update_auto_status("⏳ Đang chờ tin nhắn từ kênh...", "white")
                time.sleep(2)
                continue

            now = datetime.now(timezone.utc)
            newest_msg = self.latest_messages[0]
            newest_date = newest_msg.get("date")
            if newest_date and newest_date.tzinfo is None:
                newest_date = newest_date.replace(tzinfo=timezone.utc)

            newest_age = (now - newest_date).total_seconds() if newest_date else 999999

            # ĐIỀU KIỆN: Link mới nhất > 3 phút (> 180s) -> Đợi tin mới hơn
            if newest_age > 180:
                age_text = self.format_age_seconds(newest_age)
                self.update_auto_status(
                    f"⏳ Link mới nhất đã {age_text} (> 3p). Đang chờ link mới...",
                    "#F6AD55",
                )
                time.sleep(2)
                continue

            # LỌC LINK: Trong vòng 1 phút trước (<= 60s) chưa vào
            candidates = []
            for msg in self.latest_messages:
                msg_date = msg.get("date")
                if msg_date and msg_date.tzinfo is None:
                    msg_date = msg_date.replace(tzinfo=timezone.utc)
                age = (now - msg_date).total_seconds() if msg_date else 999999

                if age <= 60:
                    url = msg.get("url")
                    if url and url not in self.opened_urls:
                        candidates.append(msg)

            if not candidates:
                self.update_auto_status("⏳ Đang chờ link mới (< 1 phút)...", "#63B3ED")
                time.sleep(1.5)
                continue

            # SẮP XẾP: Nhiều xu nhất -> Nhiều lượt nhất -> Mới nhất
            candidates.sort(
                key=lambda m: (m.get("coins", 0), m.get("slots", 0), m.get("date")),
                reverse=True,
            )
            target = candidates[0]
            url = target["url"]
            coins = target.get("coins", 0)
            slots = target.get("slots", 0)

            self.update_auto_status(f"🚀 Mở link: [{coins} Xu | {slots} Lượt]...", "#4299E1")
            self.opened_urls.add(url)
            self.after(0, self.update_cards_gui)

            # Mở link qua ADB
            if not self.open_url_via_adb(url):
                self.update_auto_status("❌ Lỗi mở link qua ADB!", "red")
                time.sleep(2)
                continue

            # Chờ 3.5s cho Shopee mở livestream
            time.sleep(3.5)

            # Thực thi kịch bản kiểm tra và nhận xu
            self.monitor_and_claim_coins()

    def monitor_and_claim_coins(self):
        """
        KỊCH BẢN THỰC THI CHUẨN XÁC:
        1. Check biểu tượng 'PHẦN THƯỞNG':
           - Nếu KHÔNG thấy: Đang lỗi hoặc Shopee phát hiện -> Thoát app Shopee, vào lại app Shopee, rồi mới tiếp tục nhận link.
        2. Check ô xu với thời gian > 4 phút (loại bỏ ô lướt video / điểm danh ngắn):
           - Nếu KHÔNG có ô xu nào > 4p: Thoát app Shopee, vào lại app Shopee, chuyển sang link khác.
        3. Sau đó theo logic đã định:
           - Đợi hết thời gian đếm ngược đến khi hiện dòng: 'Nhấn để nhận thưởng!'
           - Tìm nút 'Lưu', nhấn (chống auto click)
           - Đợi 3s -> Thoát app Shopee -> Vào lại Shopee -> Nhận link mới.
        """
        # --- BƯỚC 1: CHECK BIỂU TƯỢNG 'PHẦN THƯỞNG' ---
        found_banner = False
        last_scan_data = None

        for attempt in range(3):
            if not self.auto_hunting_enabled:
                return

            self.update_auto_status(f"🔍 [1/3] Đang check biểu tượng 'PHẦN THƯỞNG' (lần {attempt+1}/3)...", "#90CDF4")
            screen = self.capture_screen_cv2()
            if screen is not None:
                last_scan_data = self.scan_screen_for_coins(screen)
                if last_scan_data.get("has_phan_thuong"):
                    found_banner = True
                    break
            time.sleep(2.0)

        # NẾU KHÔNG THẤY BIỂU TƯỢNG 'PHẦN THƯỞNG' -> LỖI / SHOPEE PHÁT HIỆN
        if not found_banner:
            self.update_auto_status("🚨 KHÔNG THẤY 'PHẦN THƯỞNG' (Lỗi / Shopee phát hiện)!", "#E53E3E")
            time.sleep(1.0)

            # Thoát app Shopee
            self.update_auto_status("🚪 Đang thoát app Shopee...", "#ED8936")
            self.force_stop_shopee()
            time.sleep(2.0)

            # Vào lại app Shopee
            self.update_auto_status("📱 Đang vào lại app Shopee để làm mới phiên...", "#4299E1")
            self.launch_shopee_app()

            time.sleep(5.0)
            self.update_auto_status("✅ Đã vào lại Shopee. Tiếp tục nhận link mới...", "#38A169")
            time.sleep(1.5)
            return

        # --- BƯỚC 2: CHECK Ô XU VỚI THỜI GIAN LỚN HƠN 4P (LOẠI BỎ LƯỚT VIDEO) ---
        found_gt_4m_task = False
        initial_target_task = None

        for attempt in range(3):
            if not self.auto_hunting_enabled:
                return

            self.update_auto_status(f"🔍 [2/3] Check ô xu > 4 phút (loại bỏ lướt video) lần {attempt+1}/3...", "#90CDF4")
            tasks = last_scan_data.get("watching_tasks", [])
            for t in tasks:
                if t["is_gt_4m"]:
                    found_gt_4m_task = True
                    initial_target_task = t
                    break

            if found_gt_4m_task:
                break

            time.sleep(2.0)
            screen = self.capture_screen_cv2()
            if screen is not None:
                last_scan_data = self.scan_screen_for_coins(screen)

        # NẾU KHÔNG CÓ Ô XU > 4P (chỉ có lướt video hoặc hết xu)
        if not found_gt_4m_task:
            self.update_auto_status("⚠️ Không tìm thấy ô xu > 4p (chỉ có lướt video hoặc hết xu)!", "#ED8936")
            time.sleep(1.0)
            self.force_stop_shopee()
            time.sleep(2.0)
            self.update_auto_status("📱 Đang vào lại Shopee để chuyển link khác...", "#4299E1")
            self.launch_shopee_app()
            time.sleep(4.0)
            return

        # --- BƯỚC 3: ĐÃ XÁC NHẬN Ô XU > 4P -> THEO LOGIC ĐÃ ĐỊNH (ĐỢI HẾT GIỜ) ---
        t_str = initial_target_task.get("time_str", "")
        self.update_auto_status(f"✅ Đã tìm thấy ô xu hợp lệ: {t_str} (> 4p)! Đang chờ đếm ngược...", "#48BB78")
        start_wait_time = time.time()

        while self.auto_hunting_enabled:
            # Nếu đã xuất hiện 'Nhấn để nhận thưởng!' hoặc nút Lưu đã sẵn sàng
            if last_scan_data.get("has_ready") or (last_scan_data.get("luu_coords") is not None):
                break

            # Cập nhật thời gian còn lại
            tasks = last_scan_data.get("watching_tasks", [])
            current_time_str = tasks[0]["time_str"] if tasks else ""
            time_display = f" ({current_time_str})" if current_time_str else ""
            self.update_auto_status(f"⏳ Đang xem livestream đếm ngược{time_display}... Đợi 'Nhấn để nhận thưởng!'", "#ECC94B")

            time.sleep(2.5)
            screen = self.capture_screen_cv2()
            if screen is not None:
                last_scan_data = self.scan_screen_for_coins(screen)

            # Timeout bảo vệ tối đa 12 phút (đủ cho livestream 10 phút)
            if time.time() - start_wait_time > 720:
                self.update_auto_status("⚠️ Quá thời gian chờ (timeout). Thoát Shopee...", "#ED8936")
                self.force_stop_shopee()
                self.launch_shopee_app()
                time.sleep(4.0)
                return

        if not self.auto_hunting_enabled:
            return

        # --- BƯỚC 4: HIỆN DÒNG 'Nhấn để nhận thưởng!' -> TÌM NÚT LƯU ---
        self.update_auto_status("🎯 Đã hiện 'Nhấn để nhận thưởng!'. Đang tìm nút Lưu...", "#48BB78")

        luu_coords = last_scan_data.get("luu_coords")
        if luu_coords is None:
            for _ in range(4):
                time.sleep(1.0)
                screen = self.capture_screen_cv2()
                if screen is not None:
                    last_scan_data = self.scan_screen_for_coins(screen)
                    if last_scan_data.get("luu_coords") is not None:
                        luu_coords = last_scan_data.get("luu_coords")
                        break

        # --- BƯỚC 5: NHẤN LƯU (CHỐNG AUTO CLICK) -> ĐỢI 3S -> THOÁT APP -> VÀO LẠI APP -> LINK MỚI ---
        if luu_coords is not None:
            cx, cy, bw, bh = luu_coords
            self.update_auto_status(f"👆 Nhấn Lưu (chống auto click) tại ({cx}, {cy})...", "#38A169")

            # Thực hiện nhấn chống auto-click
            self.human_like_tap(cx, cy, bw, bh)

            # Đợi 3s
            self.update_auto_status("⏳ Đã nhấn Lưu! Đợi 3s và hoàn tất nhận xu...", "#48BB78")
            time.sleep(3.0)

            # Thoát app Shopee
            self.update_auto_status("🚪 Thoát Shopee sau khi nhận thưởng...", "#4299E1")
            self.force_stop_shopee()
            time.sleep(2.0)

            # Vào lại app Shopee để sẵn sàng nhận link tiếp theo
            self.update_auto_status("📱 Vào lại app Shopee chuẩn bị nhận link mới...", "#4299E1")
            self.launch_shopee_app()
            time.sleep(4.0)
        else:
            self.update_auto_status("⚠️ Không tìm thấy nút Lưu. Thoát và mở lại Shopee...", "orange")
            self.force_stop_shopee()
            time.sleep(2.0)
            self.launch_shopee_app()
            time.sleep(4.0)

    def format_age_seconds(self, seconds):
        seconds = max(0, int(seconds))
        if seconds < 60:
            return f"{seconds}s trước"
        elif seconds < 3600:
            return f"{seconds // 60}p trước"
        else:
            return f"{seconds // 3600}h trước"

    def get_message_age(self, msg_date):
        if not msg_date:
            return ""
        now = datetime.now(timezone.utc)
        if msg_date.tzinfo is None:
            msg_date = msg_date.replace(tzinfo=timezone.utc)
        return self.format_age_seconds((now - msg_date).total_seconds())

    # --- XỬ LÝ GIAO DIỆN CARDS ---
    def on_card_click(self, index):
        if index < len(self.latest_messages):
            msg = self.latest_messages[index]
            url = msg.get("url")
            if url:
                if self.open_url_via_adb(url):
                    self.opened_urls.add(url)
                    self.update_cards_gui()
            else:
                self.update_status("⚠️ Tin nhắn không chứa link Shopee hợp lệ!", "orange")

    def update_cards_gui(self):
        for i in range(3):
            if i < len(self.latest_messages):
                msg = self.latest_messages[i]
                url = msg.get("url")
                coins = msg.get("coins", 0)
                slots = msg.get("slots", 0)
                age = self.get_message_age(msg.get("date"))

                coin_tag = f"💰 {coins} Xu" if coins > 0 else "Xu ??"
                slot_tag = f"🎟 {slots} Lượt" if slots > 0 else "Lượt ??"
                opened_tag = " ✅ ĐÃ VÀO" if url and url in self.opened_urls else ""

                if i == 0:
                    badge = "🔥 [MỚI NHẤT] "
                    bg_color = "#2C5282"
                    border_color = "#3182CE"
                else:
                    badge = f"[{i+1}] "
                    bg_color = "#1A202C"
                    border_color = "#2D3748"

                display_text = f"{badge}{coin_tag} | {slot_tag}{opened_tag}\n⏱ {age} • Link: {url or 'Không có'}"

                self.card_buttons[i].configure(
                    text=display_text,
                    fg_color=bg_color,
                    border_color=border_color,
                    border_width=1,
                )
            else:
                self.card_buttons[i].configure(
                    text=f"[{i+1}] Đang chờ tin...", fg_color="#2D3748", border_width=0
                )

    def open_manual_link(self):
        url = self.url_entry.get().strip()
        if self.open_url_via_adb(url):
            self.url_entry.delete(0, tk.END)

    # --- TELEGRAM WORKFLOW ---
    def request_otp(self):
        phone = self.phone_entry.get().strip().replace(" ", "")
        if not phone:
            self.update_status("⚠️ Vui lòng nhập Số điện thoại!", "orange")
            return

        if phone.startswith("0"):
            phone = "+84" + phone[1:]
        elif not phone.startswith("+"):
            phone = "+" + phone

        self.phone_entry.delete(0, tk.END)
        self.phone_entry.insert(0, phone)

        self.save_user_config(phone)
        self.update_status("🔄 Đang gửi mã OTP tới Telegram...", "white")
        self.send_otp_btn.configure(state="disabled")

        asyncio.run_coroutine_threadsafe(self._async_request_otp(phone), self.loop)

    async def _async_request_otp(self, phone):
        try:
            self.client = TelegramClient("user_session", API_ID, API_HASH, loop=self.loop)
            await self.client.connect()
            if not await self.client.is_user_authorized():
                res = await self.client.send_code_request(phone)
                self.phone_code_hash = res.phone_code_hash
                self.after(0, self.enable_otp_input)
                self.update_status("📩 Mã OTP đã gửi! Vui lòng nhập vào ô bên dưới.", "green")
            else:
                self.update_status("✅ Đã đăng nhập từ trước!", "green")
                await self._start_listening_async()
        except Exception as e:
            self.update_status(f"❌ Lỗi gửi OTP: {e}", "red")
            self.after(0, lambda: self.send_otp_btn.configure(state="normal"))

    def enable_otp_input(self):
        self.otp_entry.configure(state="normal")
        self.verify_otp_btn.configure(state="normal")
        self.otp_entry.focus()

    def submit_otp(self):
        code = self.otp_entry.get().strip()
        phone = self.phone_entry.get().strip()

        if not code:
            self.update_status("⚠️ Vui lòng nhập mã OTP!", "orange")
            return

        self.verify_otp_btn.configure(state="disabled")
        self.update_status("🔄 Đang xác thực OTP...", "white")

        asyncio.run_coroutine_threadsafe(self._async_submit_otp(phone, code), self.loop)

    async def _async_submit_otp(self, phone, code):
        try:
            await self.client.sign_in(phone=phone, code=code, phone_code_hash=self.phone_code_hash)
            self.update_status("✅ Xác thực thành công!", "green")
            await self._start_listening_async()
        except Exception as e:
            self.update_status(f"❌ Mã OTP không đúng: {e}", "red")
            self.after(0, lambda: self.verify_otp_btn.configure(state="normal"))

    async def _start_listening_async(self):
        try:
            entity = await self.client.get_entity(TARGET_CHANNEL)
            messages = await self.client.get_messages(entity, limit=20)
            self.latest_messages = [
                self.process_message_data(msg) for msg in messages if msg.message
            ]
            self.latest_messages = [m for m in self.latest_messages if m.get("url")]
            self.after(0, self.update_cards_gui)
            self.update_status(f"✅ Đang theo dõi @{TARGET_CHANNEL}", "green")
        except Exception as e:
            self.update_status(f"❌ Lỗi lấy tin nhắn: {e}", "red")

        @self.client.on(events.NewMessage(chats=TARGET_CHANNEL))
        async def new_msg_handler(event):
            data = self.process_message_data(event.message)
            if data.get("url"):
                self.latest_messages.insert(0, data)
                self.latest_messages = self.latest_messages[:20]
                self.after(0, self.update_cards_gui)


if __name__ == "__main__":
    app = ShopeeCoinHunter()
    app.mainloop()
