import asyncio
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR
from telethon import TelegramClient, events

# Đảm bảo mã hóa UTF-8 cho console Windows
sys.stdout.reconfigure(encoding="utf-8")
os.system("")  # Kích hoạt ANSI VT100 colors trên Windows Terminal / CMD

# --- CẤU HÌNH API TELEGRAM & KÊNH MẶC ĐỊNH ---
API_ID = 35941628
API_HASH = "4ff2740f67c881028c1ae826a3765f47"
TARGET_CHANNEL = "xueshopee"
CONFIG_FILE = "config.json"
SESSION_NAME = "user_session"
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

# ANSI Color Codes
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_CYAN = "\033[1;36m"
COLOR_GREEN = "\033[1;32m"
COLOR_YELLOW = "\033[1;33m"
COLOR_RED = "\033[1;31m"
COLOR_MAGENTA = "\033[1;35m"
COLOR_BLUE = "\033[1;34m"
COLOR_GRAY = "\033[90m"


class CmdLineInterface:
    r"""
    Lớp cơ sở giao diện dòng lệnh (CLI Base Class)
    Tương tự mô hình CmdLineInterface trong D:\C++\cli.h / cli.cpp
    """

    def __init__(self, prompt="shopee> "):
        self.cmd_prompt = prompt
        self.b_running = False
        self.commands = {}
        self.cmd_syntax = {}
        self.cmd_help = {}
        self.log_lock = threading.Lock()

    def set_cmd_prompt(self, prompt):
        self.cmd_prompt = prompt

    def show_cmd_prompt(self):
        sys.stdout.write(f"\r\033[K{COLOR_CYAN}{self.cmd_prompt}{COLOR_RESET}")
        sys.stdout.flush()

    def clear_screen(self):
        os.system("cls" if os.name == "nt" else "clear")

    def add_cmd(self, name, func, syntax="", help_desc=""):
        name_lower = name.lower()
        self.commands[name_lower] = func
        self.cmd_syntax[name_lower] = syntax or name
        self.cmd_help[name_lower] = help_desc

    def parse_cmd(self, line):
        parts = line.strip().split()
        if not parts:
            return "", []
        return parts[0].lower(), parts[1:]

    def get_tag_color(self, tag):
        t = tag.upper()
        if t in ["TELEGRAM", "INFO"]:
            return COLOR_CYAN
        elif t in ["ADB", "REWARD", "SUCCESS", "OK"]:
            return COLOR_GREEN
        elif t in ["OCR", "WAIT"]:
            return COLOR_YELLOW
        elif t in ["AUTO"]:
            return COLOR_MAGENTA
        elif t in ["WARN", "ERROR", "FAIL"]:
            return COLOR_RED
        return COLOR_BLUE

    def log(self, tag, message):
        """Ghi log vào Vùng Log mà không làm hỏng dòng lệnh đang nhập"""
        now = datetime.now().strftime("%H:%M:%S")
        color = self.get_tag_color(tag)
        formatted_line = f"[{now}] {color}[{tag}]{COLOR_RESET} {message}"
        with self.log_lock:
            # Xóa dòng nhắc hiện tại, in log, và vẽ lại dòng nhắc lệnh
            sys.stdout.write(f"\r\033[K{formatted_line}\n")
            sys.stdout.write(f"{COLOR_CYAN}{self.cmd_prompt}{COLOR_RESET}")
            sys.stdout.flush()

    def do_unknown(self, cmd_name):
        print(f"{COLOR_RED}[!] Lệnh '{cmd_name}' không được hỗ trợ! Gõ 'help' để xem danh sách lệnh.{COLOR_RESET}")

    def do_quit(self, args):
        self.b_running = False
        print(f"{COLOR_YELLOW}[*] Đang đóng chương trình... Tạm biệt!{COLOR_RESET}")

    def run(self):
        self.b_running = True
        while self.b_running:
            try:
                self.show_cmd_prompt()
                line = sys.stdin.readline()
                if not line:
                    break
                cmd_str = line.strip()
                if not cmd_str:
                    continue

                cmd_name, args = self.parse_cmd(cmd_str)
                if cmd_name in self.commands:
                    self.commands[cmd_name](args)
                else:
                    self.do_unknown(cmd_name)
            except (KeyboardInterrupt, EOFError):
                print()
                self.do_quit([])
                break
            except Exception as e:
                self.log("ERROR", f"Lỗi thực thi lệnh: {e}")


class ShopeeCoinHunterCLI(CmdLineInterface):
    """
    Công cụ Shopee Coin Hunter dạng CLI
    Kế thừa CmdLineInterface và phân chia màn hình:
    - Phần 1: Khung thông tin & Log theo thời gian thực
    - Phần 2: Khung dòng lệnh nhập tương tác
    """

    def __init__(self):
        super().__init__("shopee> ")

        # Trạng thái Telegram
        self.client = None
        self.loop = None
        self.phone_code_hash = None
        self.user_authorized = False
        self.user_name = "Chưa đăng nhập"
        self.phone_number = ""
        self.latest_messages = []
        self.opened_urls = set()

        # Trạng thái ADB
        self.device_id = None
        self.device_connected = False

        # Trạng thái Auto
        self.auto_hunting_enabled = False
        self.auto_thread = None
        self.auto_status_desc = "Đang Tắt"

        # OCR & Templates
        self.ocr = RapidOCR()
        self.tpl_luu = None
        self.tpl_banner = None
        self.load_templates()

        # Khởi tạo lệnh CLI
        self.init_cmd()

        # Nạp cấu hình & kiểm tra thiết bị
        self.load_user_config()
        self.check_adb_device()

        # Khởi chạy asyncio loop ngầm cho Telegram
        self.start_async_loop()
        self.auto_connect_if_logged_in()

    # --- KHỞI TẠO DANH SÁCH LỆNH (Tương tự ServerCLI / ClientCLI) ---
    def init_cmd(self):
        self.add_cmd("start", self.do_start, "start", "Bật chế độ tự động săn xu theo kịch bản")
        self.add_cmd("stop", self.do_stop, "stop", "Dừng chế độ tự động săn xu")
        self.add_cmd("status", self.do_status, "status", "Xem chi tiết trạng thái hệ thống (ADB, Tele, Auto)")
        self.add_cmd("latest", self.do_latest, "latest", "Xem các tin nhắn / link mới nhất từ Telegram")
        self.add_cmd("open", self.do_open, "open <url>", "Mở link Shopee thủ công qua ADB")
        self.add_cmd("otp", self.do_otp, "otp [sdt]", "Gửi mã OTP đăng nhập Telegram (mặc định SĐT đã lưu)")
        self.add_cmd("verify", self.do_verify, "verify <code>", "Xác nhận mã OTP gồm 5 chữ số từ Telegram")
        self.add_cmd("logout", self.do_logout, "logout", "Đăng xuất tài khoản Telegram và xóa phiên")
        self.add_cmd("device", self.do_device, "device", "Kiểm tra / làm mới kết nối thiết bị ADB")
        self.add_cmd("clear", self.do_clear, "clear", "Xóa màn hình và vẽ lại giao diện chia 2 phần")
        self.add_cmd("cls", self.do_clear, "cls", "Xóa màn hình (alias của clear)")
        self.add_cmd("help", self.do_help, "help", "Hiển thị danh sách các lệnh hỗ trợ")
        self.add_cmd("quit", self.do_quit, "quit", "Thoát chương trình an toàn")
        self.add_cmd("exit", self.do_quit, "exit", "Thoát chương trình (alias của quit)")

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

    # --- KHỞI TẠO ASYNCIO LOOP RIÊNG CHO TELEGRAM ---
    def start_async_loop(self):
        self.loop = asyncio.new_event_loop()

        def _run_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        t = threading.Thread(target=_run_loop, daemon=True)
        t.start()

    # --- LƯU & TẢI USER CONFIG ---
    def load_user_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.phone_number = data.get("phone", "")
            except Exception:
                pass

    def save_user_config(self, phone):
        self.phone_number = phone
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"phone": phone}, f)
        except Exception:
            pass

    # --- TELEGRAM WORKFLOW ---
    def auto_connect_if_logged_in(self):
        if os.path.exists(f"{SESSION_NAME}.session"):
            self.log("INFO", "Phát hiện session cũ, đang tự động kết nối Telegram...")
            asyncio.run_coroutine_threadsafe(self._async_auto_login(), self.loop)

    async def _async_auto_login(self):
        try:
            self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH, loop=self.loop)
            await self.client.connect()
            if await self.client.is_user_authorized():
                me = await self.client.get_me()
                self.user_authorized = True
                self.user_name = me.first_name or "User"
                if me.phone:
                    self.phone_number = f"+{me.phone}"
                self.set_cmd_prompt(f"{self.user_name}@shopee> ")
                self.log("TELEGRAM", f"✅ Tự động đăng nhập thành công: {self.user_name} ({self.phone_number})")
                await self._start_listening_async()
            else:
                self.user_authorized = False
                self.log("WARN", "Phiên Telegram đã hết hạn! Vui lòng dùng lệnh 'otp' để đăng nhập lại.")
        except Exception as e:
            self.log("ERROR", f"Lỗi tự động kết nối Telegram: {e}")

    async def _start_listening_async(self):
        try:
            entity = await self.client.get_entity(TARGET_CHANNEL)
            messages = await self.client.get_messages(entity, limit=15)
            self.latest_messages = [
                self.process_message_data(msg) for msg in messages if msg.message
            ]
            self.latest_messages = [m for m in self.latest_messages if m.get("url")]
            self.log("TELEGRAM", f"Đã kết nối theo dõi kênh @{TARGET_CHANNEL} (Lấy được {len(self.latest_messages)} link gần nhất).")
        except Exception as e:
            self.log("ERROR", f"Lỗi nạp tin nhắn từ @{TARGET_CHANNEL}: {e}")

        @self.client.on(events.NewMessage(chats=TARGET_CHANNEL))
        async def new_msg_handler(event):
            data = self.process_message_data(event.message)
            if data.get("url"):
                self.latest_messages.insert(0, data)
                self.latest_messages = self.latest_messages[:25]
                coins = data.get("coins", 0)
                slots = data.get("slots", 0)
                url = data.get("url")
                self.log("TELEGRAM", f"Tin mới: 💰 {coins} Xu | 🎟 {slots} Lượt ➔ {url}")

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
            self.device_connected = False
            self.device_id = None
            return False

        lines = output.split("\n")[1:]
        devices = [
            line.split("\t")[0]
            for line in lines
            if line.endswith("device") and line.strip()
        ]
        if devices:
            self.device_id = devices[0]
            self.device_connected = True
            return True
        else:
            self.device_id = None
            self.device_connected = False
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
            return False

        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        adb_cmd = [
            "adb", "shell", "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", url,
        ]
        output = self.run_adb_cmd(adb_cmd)
        return bool(output and "Error" not in output)

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
        time.sleep(random.uniform(0.35, 0.75))

        max_dx = max(3, int(bw * 0.22))
        max_dy = max(2, int(bh * 0.22))
        rx = cx + random.randint(-max_dx, max_dx)
        ry = cy + random.randint(-max_dy, max_dy)

        ex = rx + random.randint(-1, 1)
        ey = ry + random.randint(-1, 1)
        press_duration = random.randint(90, 140)

        self.run_adb_cmd([
            "adb", "shell", "input", "swipe",
            str(rx), str(ry), str(ex), str(ey), str(press_duration)
        ])

    # --- QUÉT VÙNG NHẬN XU (OCR + TEMPLATE) ---
    def scan_screen_for_coins(self, screen):
        if screen is None:
            return {
                "has_phan_thuong": False,
                "watching_tasks": [],
                "has_ready": False,
                "luu_coords": None,
            }

        h, w = screen.shape[:2]
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

        # 2. OCR nhận diện văn bản trong ROI
        ocr_res, _ = self.ocr(roi)
        if ocr_res:
            for item in ocr_res:
                _, txt, conf = item
                raw_txt = txt.lower()
                clean = raw_txt.replace(" ", "")

                if "phan" in clean and ("thu" in clean or "th" in clean or "ng" in clean):
                    has_phan_thuong = True

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

    # --- KỊCH BẢN TỰ ĐỘNG SĂN XU ---
    def auto_hunter_worker(self):
        self.log("AUTO", "📱 Đang vào app Shopee sẵn sàng...")
        self.launch_shopee_app()
        time.sleep(3.5)

        while self.auto_hunting_enabled:
            # 1. Kiểm tra ADB
            if not self.check_adb_device():
                self.log("WARN", "Thiết bị ADB chưa kết nối! Đang thử lại...")
                time.sleep(3)
                continue

            # 2. Kiểm tra tin nhắn Telegram
            if not self.latest_messages:
                self.log("AUTO", "⏳ Đang chờ tin nhắn từ kênh @xueshopee...")
                time.sleep(2)
                continue

            now = datetime.now(timezone.utc)
            newest_msg = self.latest_messages[0]
            newest_date = newest_msg.get("date")
            if newest_date and newest_date.tzinfo is None:
                newest_date = newest_date.replace(tzinfo=timezone.utc)

            newest_age = (now - newest_date).total_seconds() if newest_date else 999999

            # ĐIỀU KIỆN: Link mới nhất > 3 phút -> Đợi tin mới
            if newest_age > 180:
                age_text = self.format_age_seconds(newest_age)
                self.log("AUTO", f"⏳ Link mới nhất đã {age_text} (> 3p). Đang chờ link mới hơn...")
                time.sleep(2)
                continue

            # LỌC LINK: <= 60s chưa vào
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

            self.log("AUTO", f"🚀 Mở link ngon nhất: [{coins} Xu | {slots} Lượt] ➔ {url}")
            self.opened_urls.add(url)

            if not self.open_url_via_adb(url):
                self.log("ERROR", "Gửi lệnh mở link qua ADB thất bại!")
                time.sleep(2)
                continue

            time.sleep(3.5)
            self.monitor_and_claim_coins()

    def monitor_and_claim_coins(self):
        # BƯỚC 1: CHECK BIỂU TƯỢNG 'PHẦN THƯỞNG'
        found_banner = False
        last_scan_data = None

        for attempt in range(3):
            if not self.auto_hunting_enabled:
                return

            self.log("OCR", f"Check biểu tượng 'PHẦN THƯỞNG' (lần {attempt+1}/3)...")
            screen = self.capture_screen_cv2()
            if screen is not None:
                last_scan_data = self.scan_screen_for_coins(screen)
                if last_scan_data.get("has_phan_thuong"):
                    found_banner = True
                    break
            time.sleep(2.0)

        # KHÔNG THẤY BIỂU TƯỢNG -> LỖI / SHOPEE PHÁT HIỆN
        if not found_banner:
            self.log("WARN", "🚨 KHÔNG THẤY 'PHẦN THƯỞNG' (Nghi ngờ Shopee phát hiện/lỗi)! Thoát app Shopee...")
            self.force_stop_shopee()
            time.sleep(2.0)
            self.log("AUTO", "📱 Đang vào lại app Shopee để làm mới phiên...")
            self.launch_shopee_app()
            time.sleep(5.0)
            self.log("SUCCESS", "✅ Đã vào lại Shopee. Tiếp tục nhận link mới...")
            return

        # BƯỚC 2: CHECK Ô XU VỚI THỜI GIAN > 4 PHÚT (LOẠI BỎ LƯỚT VIDEO)
        found_gt_4m_task = False
        initial_target_task = None

        for attempt in range(3):
            if not self.auto_hunting_enabled:
                return

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

        if not found_gt_4m_task:
            self.log("WARN", "⚠️ Không tìm thấy ô xu > 4p (chỉ có lướt video hoặc đã hết xu). Chuyển link...")
            self.force_stop_shopee()
            time.sleep(2.0)
            self.launch_shopee_app()
            time.sleep(4.0)
            return

        # BƯỚC 3: ĐÃ XÁC NHẬN Ô XU > 4P -> ĐỢI HẾT GIỜ
        t_str = initial_target_task.get("time_str", "")
        self.log("OCR", f"✅ Đã tìm thấy ô xu hợp lệ: {t_str} (> 4p)! Đang chờ đếm ngược...")
        start_wait_time = time.time()
        last_logged_time = ""

        while self.auto_hunting_enabled:
            if last_scan_data.get("has_ready") or (last_scan_data.get("luu_coords") is not None):
                break

            tasks = last_scan_data.get("watching_tasks", [])
            cur_time_str = tasks[0]["time_str"] if tasks else ""
            if cur_time_str and cur_time_str != last_logged_time:
                last_logged_time = cur_time_str
                self.log("WAIT", f"⏳ Đang xem livestream đếm ngược: còn {cur_time_str}...")

            time.sleep(2.5)
            screen = self.capture_screen_cv2()
            if screen is not None:
                last_scan_data = self.scan_screen_for_coins(screen)

            if time.time() - start_wait_time > 720:
                self.log("WARN", "Quá thời gian chờ livestream (timeout 12p)! Thoát Shopee...")
                self.force_stop_shopee()
                self.launch_shopee_app()
                time.sleep(4.0)
                return

        if not self.auto_hunting_enabled:
            return

        # BƯỚC 4: HIỆN 'Nhấn để nhận thưởng!' -> TÌM NÚT LƯU
        self.log("REWARD", "🎯 Đã hết giờ! Xuất hiện 'Nhấn để nhận thưởng!'. Đang tìm nút Lưu...")
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

        # BƯỚC 5: NHẤN LƯU (CHỐNG AUTO CLICK) -> ĐỢI 3S -> THOÁT APP -> VÀO LẠI APP -> LINK MỚI
        if luu_coords is not None:
            cx, cy, bw, bh = luu_coords
            self.log("REWARD", f"👆 Nhấn Lưu (chống auto-click) tại ({cx}, {cy})...")
            self.human_like_tap(cx, cy, bw, bh)

            self.log("REWARD", "⏳ Đã nhấn Lưu! Đợi 3s ghi nhận xu...")
            time.sleep(3.0)

            self.log("AUTO", "🚪 Thoát app Shopee...")
            self.force_stop_shopee()
            time.sleep(2.0)

            self.log("AUTO", "📱 Vào lại app Shopee chuẩn bị nhận link mới...")
            self.launch_shopee_app()
            time.sleep(4.0)
        else:
            self.log("WARN", "Không tìm thấy tọa độ nút Lưu. Thoát và mở lại Shopee...")
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

    # --- CÁC HÀM XỬ LÝ LỆNH TƯƠNG TÁC (CLI COMMANDS) ---
    def do_start(self, args):
        """Bật kịch bản tự động săn xu"""
        if self.auto_hunting_enabled:
            print(f"{COLOR_YELLOW}[!] Tự động săn xu ĐÃ BẬT từ trước!{COLOR_RESET}")
            return

        if not self.device_connected:
            self.check_adb_device()
            if not self.device_connected:
                print(f"{COLOR_RED}[-] Chưa kết nối thiết bị ADB! Hãy cắm cáp và bật USB Debugging.{COLOR_RESET}")
                return

        self.auto_hunting_enabled = True
        self.auto_status_desc = "ĐANG CHẠY (RUNNING)"
        self.log("AUTO", "🟢 ĐÃ BẬT TỰ ĐỘNG SĂN XU THEO KỊCH BẢN.")
        self.auto_thread = threading.Thread(target=self.auto_hunter_worker, daemon=True)
        self.auto_thread.start()

    def do_stop(self, args):
        """Dừng kịch bản tự động săn xu"""
        if not self.auto_hunting_enabled:
            print(f"{COLOR_YELLOW}[!] Tự động săn xu hiện đang ở trạng thái TẮT.{COLOR_RESET}")
            return

        self.auto_hunting_enabled = False
        self.auto_status_desc = "ĐÃ DỪNG (STOPPED)"
        self.log("AUTO", "⚪ ĐÃ TẮT TỰ ĐỘNG SĂN XU.")

    def do_status(self, args):
        """Xem chi tiết trạng thái hệ thống"""
        self.check_adb_device()
        print("\n" + f"{COLOR_CYAN}═" * 75 + f"{COLOR_RESET}")
        print(f"             {COLOR_BOLD}THÔNG TIN TRẠNG THÁI HỆ THỐNG (STATUS){COLOR_RESET}")
        print(f"{COLOR_CYAN}═" * 75 + f"{COLOR_RESET}")

        adb_status = f"{COLOR_GREEN}Đã kết nối: {self.device_id}{COLOR_RESET}" if self.device_connected else f"{COLOR_RED}Chưa kết nối thiết bị{COLOR_RESET}"
        tele_status = f"{COLOR_GREEN}Đã đăng nhập ({self.user_name} | {self.phone_number}){COLOR_RESET}" if self.user_authorized else f"{COLOR_YELLOW}Chưa đăng nhập (dùng 'otp'){COLOR_RESET}"
        auto_status = f"{COLOR_GREEN}BẬT (RUNNING){COLOR_RESET}" if self.auto_hunting_enabled else f"{COLOR_GRAY}TẮT (STOPPED){COLOR_RESET}"

        print(f"  • Thiết bị ADB     : {adb_status}")
        print(f"  • Tài khoản Telegram: {tele_status}")
        print(f"  • Kênh theo dõi     : @{TARGET_CHANNEL}")
        print(f"  • Chế độ Tự động    : {auto_status}")
        print(f"  • Số link đã mở     : {len(self.opened_urls)} link")
        print(f"  • Tin nhắn trong queue: {len(self.latest_messages)} tin")

        if self.latest_messages:
            top = self.latest_messages[0]
            print(f"  • Tin nhắn mới nhất : 💰 {top.get('coins', 0)} Xu | 🎟 {top.get('slots', 0)} Slot | Link: {top.get('url')}")
        print(f"{COLOR_CYAN}═" * 75 + f"{COLOR_RESET}\n")

    def do_latest(self, args):
        """Xem danh sách các tin nhắn / link mới nhất"""
        print("\n" + f"{COLOR_CYAN}─" * 75 + f"{COLOR_RESET}")
        print(f"       {COLOR_BOLD}DANH SÁCH TIN NHẮN / LINK MỚI NHẤT TỪ @{TARGET_CHANNEL}{COLOR_RESET}")
        print(f"{COLOR_CYAN}─" * 75 + f"{COLOR_RESET}")

        if not self.latest_messages:
            print("  (Chưa có tin nhắn nào được tải hoặc chưa kết nối Telegram)")
        else:
            now = datetime.now(timezone.utc)
            for idx, msg in enumerate(self.latest_messages[:7]):
                d = msg.get("date")
                if d and d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                age = self.format_age_seconds((now - d).total_seconds()) if d else "N/A"
                coins = msg.get("coins", 0)
                slots = msg.get("slots", 0)
                url = msg.get("url")
                opened = f"{COLOR_GREEN}[ĐÃ MỞ]{COLOR_RESET}" if url in self.opened_urls else f"{COLOR_YELLOW}[CHƯA MỞ]{COLOR_RESET}"
                print(f"  [{idx+1}] 💰 {coins:4d} Xu | 🎟 {slots:3d} Slot | ⏱ {age:8s} | {opened} ➔ {url}")
        print(f"{COLOR_CYAN}─" * 75 + f"{COLOR_RESET}\n")

    def do_open(self, args):
        """Mở link Shopee thủ công qua ADB"""
        if not args:
            print(f"{COLOR_RED}[!] Cú pháp: open <url_shopee>{COLOR_RESET}")
            return

        url = args[0].strip()
        print(f"[*] Đang mở link qua ADB: {url} ...")
        if self.open_url_via_adb(url):
            self.opened_urls.add(url)
            print(f"{COLOR_GREEN}[+] Mở link thành công!{COLOR_RESET}")
        else:
            print(f"{COLOR_RED}[-] Mở link thất bại qua ADB!{COLOR_RESET}")

    def do_otp(self, args):
        """Gửi mã OTP đăng nhập Telegram"""
        phone = args[0].strip() if args else self.phone_number
        if not phone:
            print(f"{COLOR_RED}[!] Vui lòng nhập số điện thoại: otp <sdt> (Ví dụ: otp 0357677359){COLOR_RESET}")
            return

        phone = phone.replace(" ", "")
        if phone.startswith("0"):
            phone = "+84" + phone[1:]
        elif not phone.startswith("+"):
            phone = "+" + phone

        self.save_user_config(phone)
        print(f"[*] Đang gửi yêu cầu mã OTP tới số {phone} ...")

        async def _req():
            try:
                self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH, loop=self.loop)
                await self.client.connect()
                if not await self.client.is_user_authorized():
                    res = await self.client.send_code_request(phone)
                    self.phone_code_hash = res.phone_code_hash
                    self.log("TELEGRAM", f"📩 Mã OTP đã gửi tới Telegram của {phone}! Dùng lệnh: verify <mã_otp>")
                else:
                    me = await self.client.get_me()
                    self.user_authorized = True
                    self.user_name = me.first_name or "User"
                    self.set_cmd_prompt(f"{self.user_name}@shopee> ")
                    self.log("TELEGRAM", f"✅ Tài khoản đã đăng nhập từ trước: {self.user_name}")
                    await self._start_listening_async()
            except Exception as e:
                self.log("ERROR", f"Lỗi gửi OTP: {e}")

        asyncio.run_coroutine_threadsafe(_req(), self.loop)

    def do_verify(self, args):
        """Xác thực mã OTP Telegram"""
        if not args:
            print(f"{COLOR_RED}[!] Cú pháp: verify <mã_otp> (Ví dụ: verify 12345){COLOR_RESET}")
            return

        code = args[0].strip()
        print(f"[*] Đang xác thực OTP: {code} ...")

        async def _sub():
            try:
                await self.client.sign_in(
                    phone=self.phone_number,
                    code=code,
                    phone_code_hash=self.phone_code_hash,
                )
                me = await self.client.get_me()
                self.user_authorized = True
                self.user_name = me.first_name or "User"
                self.set_cmd_prompt(f"{self.user_name}@shopee> ")
                self.log("TELEGRAM", f"✅ Đăng nhập Telegram thành công: {self.user_name}")
                await self._start_listening_async()
            except Exception as e:
                self.log("ERROR", f"Xác thực OTP thất bại: {e}")

        asyncio.run_coroutine_threadsafe(_sub(), self.loop)

    def do_logout(self, args):
        """Đăng xuất tài khoản Telegram"""
        if os.path.exists(f"{SESSION_NAME}.session"):
            try:
                os.remove(f"{SESSION_NAME}.session")
            except Exception:
                pass
        self.user_authorized = False
        self.user_name = "Chưa đăng nhập"
        self.set_cmd_prompt("shopee> ")
        print(f"{COLOR_YELLOW}[+] Đã đăng xuất và xóa phiên Telegram.{COLOR_RESET}")

    def do_device(self, args):
        """Kiểm tra lại thiết bị ADB"""
        if self.check_adb_device():
            print(f"{COLOR_GREEN}[+] Đã kết nối thiết bị ADB: {self.device_id}{COLOR_RESET}")
        else:
            print(f"{COLOR_RED}[-] Chưa tìm thấy thiết bị ADB kết nối! Hãy kiểm tra cáp và USB Debugging.{COLOR_RESET}")

    def do_clear(self, args):
        """Xóa màn hình và vẽ lại giao diện"""
        self.clear_screen()
        self.draw_header()

    def do_help(self, args):
        """Hiển thị hướng dẫn các lệnh (Tương tự ClientCLI::doHelp / ServerCLI::doHelp)"""
        print("\n" + f"{COLOR_CYAN}═" * 75 + f"{COLOR_RESET}")
        print(f"             {COLOR_BOLD}DANH SÁCH LỆNH ĐIỀU KHIỂN SHOPEE CLI{COLOR_RESET}")
        print(f"{COLOR_CYAN}═" * 75 + f"{COLOR_RESET}")
        for name in sorted(self.commands.keys()):
            # Bỏ qua các alias trùng lặp
            if name in ["cls", "exit"]:
                continue
            syntax = self.cmd_syntax.get(name, name)
            help_desc = self.cmd_help.get(name, "")
            print(f"  {COLOR_GREEN}{syntax:16s}{COLOR_RESET} : {help_desc}")
        print(f"{COLOR_CYAN}═" * 75 + f"{COLOR_RESET}\n")

    def draw_header(self):
        """Vẽ phần đầu giao diện phân chia rõ rệt: Phần Log và Phần Nhập lệnh"""
        self.check_adb_device()
        adb_status = f"{COLOR_GREEN}{self.device_id}{COLOR_RESET}" if self.device_connected else f"{COLOR_RED}Chưa kết nối{COLOR_RESET}"
        tele_status = f"{COLOR_GREEN}{self.user_name}{COLOR_RESET}" if self.user_authorized else f"{COLOR_YELLOW}Chưa đăng nhập{COLOR_RESET}"
        auto_status = f"{COLOR_GREEN}BẬT{COLOR_RESET}" if self.auto_hunting_enabled else f"{COLOR_GRAY}TẮT{COLOR_RESET}"

        print(f"{COLOR_CYAN}╔═════════════════════════════════════════════════════════════════════════════╗{COLOR_RESET}")
        print(f"{COLOR_CYAN}║{COLOR_RESET}        {COLOR_BOLD}🎯 SHOPEE COIN HUNTER - CLI CONTROLLER (@xueshopee){COLOR_RESET}                  {COLOR_CYAN}║{COLOR_RESET}")
        print(f"{COLOR_CYAN}║{COLOR_RESET}  Thiết bị ADB: {adb_status:20s} | Telegram: {tele_status:20s}  {COLOR_CYAN}║{COLOR_RESET}")
        print(f"{COLOR_CYAN}║{COLOR_RESET}  Tự động săn xu: [{auto_status}] | Kênh theo dõi: @{TARGET_CHANNEL:<22s}     {COLOR_CYAN}║{COLOR_RESET}")
        print(f"{COLOR_CYAN}╚═════════════════════════════════════════════════════════════════════════════╝{COLOR_RESET}")
        print(f"{COLOR_GRAY}┌── [PHẦN 1: NHẬT KÝ HOẠT ĐỘNG / LOGS] ───────────────────────────────────────┐{COLOR_RESET}")
        print(f"{COLOR_GRAY}│ Hệ thống đã sẵn sàng. Gõ 'help' để xem danh sách lệnh, 'start' để bật auto. │{COLOR_RESET}")
        print(f"{COLOR_GRAY}└── [PHẦN 2: DÒNG LỆNH NHẬP / COMMAND PROMPT] ────────────────────────────────┘{COLOR_RESET}")


if __name__ == "__main__":
    app = ShopeeCoinHunterCLI()
    app.draw_header()
    app.run()
