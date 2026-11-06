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

sys.stdout.reconfigure(encoding="utf-8")
os.system("")

API_ID = 35941628
API_HASH = "4ff2740f67c881028c1ae826a3765f47"
TARGET_CHANNEL = "xueshopee"
CONFIG_FILE = "config.json"
SESSION_NAME = "user_session"
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

COLOR_RESET = "\033[0m"
COLOR_CYAN = "\033[1;36m"
COLOR_GREEN = "\033[1;32m"
COLOR_YELLOW = "\033[1;33m"
COLOR_RED = "\033[1;31m"
COLOR_MAGENTA = "\033[1;35m"


class CmdLineInterface:
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
        t = tag.lower()
        if t in ["tele", "info"]:
            return COLOR_CYAN
        elif t in ["adb", "reward", "ok"]:
            return COLOR_GREEN
        elif t in ["ocr", "wait"]:
            return COLOR_YELLOW
        elif t in ["auto"]:
            return COLOR_MAGENTA
        elif t in ["warn", "error"]:
            return COLOR_RED
        return COLOR_CYAN

    def log(self, tag, message):
        now = datetime.now().strftime("%H:%M:%S")
        color = self.get_tag_color(tag)
        formatted_line = f"[{now}] {color}[{tag}]{COLOR_RESET} {message}"
        with self.log_lock:
            sys.stdout.write(f"\r\033[K{formatted_line}\n")
            sys.stdout.write(f"{COLOR_CYAN}{self.cmd_prompt}{COLOR_RESET}")
            sys.stdout.flush()

    def do_unknown(self, cmd_name):
        print(f"{COLOR_RED}[!] Lenh '{cmd_name}' khong hop le. Go 'help'{COLOR_RESET}")

    def do_quit(self, args):
        self.b_running = False
        print(f"{COLOR_YELLOW}[*] Thoat chuong trinh.{COLOR_RESET}")

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
                self.log("error", f"{e}")


class ShopeeCoinHunterCLI(CmdLineInterface):
    def __init__(self):
        super().__init__("shopee> ")

        self.client = None
        self.loop = None
        self.phone_code_hash = None
        self.user_authorized = False
        self.user_name = "N/A"
        self.phone_number = ""
        self.latest_messages = []
        self.opened_urls = set()

        self.device_id = None
        self.device_connected = False

        self.auto_hunting_enabled = False
        self.auto_thread = None

        self.ocr = RapidOCR()
        self.tpl_luu = None
        self.tpl_banner = None
        self.load_templates()

        self.init_cmd()
        self.load_user_config()
        self.check_adb_device()

        self.start_async_loop()
        self.auto_connect_if_logged_in()

    def init_cmd(self):
        self.add_cmd("start", self.do_start, "start", "Bat auto san xu")
        self.add_cmd("stop", self.do_stop, "stop", "Tat auto san xu")
        self.add_cmd("status", self.do_status, "status", "Xem trang thai (ADB, Tele, Auto)")
        self.add_cmd("latest", self.do_latest, "latest", "Xem link/tin Telegram moi nhat")
        self.add_cmd("open", self.do_open, "open <url>", "Mo link qua ADB")
        self.add_cmd("otp", self.do_otp, "otp [sdt]", "Gui ma OTP Telegram")
        self.add_cmd("verify", self.do_verify, "verify <code>", "Xac thuc ma OTP")
        self.add_cmd("logout", self.do_logout, "logout", "Dang xuat Telegram")
        self.add_cmd("device", self.do_device, "device", "Kiem tra ADB")
        self.add_cmd("clear", self.do_clear, "clear", "Xoa man hinh")
        self.add_cmd("cls", self.do_clear, "cls", "Xoa man hinh")
        self.add_cmd("help", self.do_help, "help", "Danh sach lenh")
        self.add_cmd("quit", self.do_quit, "quit", "Thoat")
        self.add_cmd("exit", self.do_quit, "exit", "Thoat")

    def load_templates(self):
        luu_path = os.path.join(TEMPLATES_DIR, "btn_luu_target.png")
        if not os.path.exists(luu_path):
            luu_path = os.path.join(TEMPLATES_DIR, "btn_claim.png")
        if os.path.exists(luu_path):
            self.tpl_luu = cv2.imread(luu_path)

        banner_path = os.path.join(TEMPLATES_DIR, "phan_thuong_banner.png")
        if os.path.exists(banner_path):
            self.tpl_banner = cv2.imread(banner_path)

    def start_async_loop(self):
        self.loop = asyncio.new_event_loop()

        def _run_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        t = threading.Thread(target=_run_loop, daemon=True)
        t.start()

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

    def auto_connect_if_logged_in(self):
        if os.path.exists(f"{SESSION_NAME}.session"):
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
                self.log("Tele", f"Dang nhap: {self.user_name} ({self.phone_number})")
                await self._start_listening_async()
            else:
                self.user_authorized = False
                self.log("Tele", "Session het han. Nhap: otp <sdt>")
        except Exception as e:
            self.log("error", f"Tele connect: {e}")

    async def _start_listening_async(self):
        try:
            entity = await self.client.get_entity(TARGET_CHANNEL)
            messages = await self.client.get_messages(entity, limit=15)
            self.latest_messages = [
                self.process_message_data(msg) for msg in messages if msg.message
            ]
            self.latest_messages = [m for m in self.latest_messages if m.get("url")]
            self.log("Tele", f"Theo doi @{TARGET_CHANNEL} ({len(self.latest_messages)} link san sang)")
        except Exception as e:
            self.log("error", f"Tele get msg: {e}")

        @self.client.on(events.NewMessage(chats=TARGET_CHANNEL))
        async def new_msg_handler(event):
            data = self.process_message_data(event.message)
            if data.get("url"):
                self.latest_messages.insert(0, data)
                self.latest_messages = self.latest_messages[:25]
                coins = data.get("coins", 0)
                slots = data.get("slots", 0)
                url = data.get("url")
                self.log("Tele", f"Tin: {coins} xu | {slots} slot | {url}")

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
        self.run_adb_cmd(["adb", "shell", "am", "force-stop", "com.shopee.vn"])

    def launch_shopee_app(self):
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
                        })

                if "nhan" in raw_txt and "thuong" in raw_txt and ("de" in raw_txt or "!" in raw_txt):
                    if "xem" not in raw_txt:
                        has_ready = True

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

    def auto_hunter_worker(self):
        self.launch_shopee_app()
        time.sleep(3.5)

        while self.auto_hunting_enabled:
            if not self.check_adb_device():
                self.log("ADB", "Chua ket noi thiet bi")
                time.sleep(3)
                continue

            if not self.latest_messages:
                time.sleep(2)
                continue

            now = datetime.now(timezone.utc)
            newest_msg = self.latest_messages[0]
            newest_date = newest_msg.get("date")
            if newest_date and newest_date.tzinfo is None:
                newest_date = newest_date.replace(tzinfo=timezone.utc)

            newest_age = (now - newest_date).total_seconds() if newest_date else 999999

            if newest_age > 180:
                time.sleep(2)
                continue

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

            candidates.sort(
                key=lambda m: (m.get("coins", 0), m.get("slots", 0), m.get("date")),
                reverse=True,
            )
            target = candidates[0]
            url = target["url"]
            coins = target.get("coins", 0)
            slots = target.get("slots", 0)

            self.log("Auto", f"Mo link: [{coins} xu | {slots} slot] -> {url}")
            self.opened_urls.add(url)

            if not self.open_url_via_adb(url):
                self.log("error", "Mo link ADB that bai")
                time.sleep(2)
                continue

            time.sleep(3.5)
            self.monitor_and_claim_coins()

    def monitor_and_claim_coins(self):
        found_banner = False
        last_scan_data = None

        for attempt in range(3):
            if not self.auto_hunting_enabled:
                return

            screen = self.capture_screen_cv2()
            if screen is not None:
                last_scan_data = self.scan_screen_for_coins(screen)
                if last_scan_data.get("has_phan_thuong"):
                    found_banner = True
                    break
            time.sleep(2.0)

        if not found_banner:
            self.log("warn", "Khong thay 'PHAN THUONG'. Restart Shopee")
            self.force_stop_shopee()
            time.sleep(1.5)
            self.launch_shopee_app()
            time.sleep(4.0)
            return

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
            self.log("warn", "Khong co xu >4p. Bo qua")
            self.force_stop_shopee()
            time.sleep(1.5)
            self.launch_shopee_app()
            time.sleep(3.5)
            return

        t_str = initial_target_task.get("time_str", "")
        self.log("OCR", f"Xu: {t_str} (>4p) - Hop le")
        start_wait_time = time.time()
        last_logged_time = ""

        while self.auto_hunting_enabled:
            if last_scan_data.get("has_ready") or (last_scan_data.get("luu_coords") is not None):
                break

            tasks = last_scan_data.get("watching_tasks", [])
            cur_time_str = tasks[0]["time_str"] if tasks else ""
            if cur_time_str and cur_time_str != last_logged_time:
                last_logged_time = cur_time_str
                self.log("Wait", f"Con: {cur_time_str}")

            time.sleep(2.5)
            screen = self.capture_screen_cv2()
            if screen is not None:
                last_scan_data = self.scan_screen_for_coins(screen)

            if time.time() - start_wait_time > 720:
                self.log("warn", "Timeout live 12p")
                self.force_stop_shopee()
                self.launch_shopee_app()
                time.sleep(3.5)
                return

        if not self.auto_hunting_enabled:
            return

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

        if luu_coords is not None:
            cx, cy, bw, bh = luu_coords
            self.log("Reward", f"Nhan Luu: ({cx}, {cy})")
            self.human_like_tap(cx, cy, bw, bh)
            time.sleep(3.0)
            self.log("Reward", "Hoan tat")
            self.force_stop_shopee()
            time.sleep(1.5)
            self.launch_shopee_app()
            time.sleep(3.5)
        else:
            self.log("warn", "Khong tim thay nut Luu")
            self.force_stop_shopee()
            time.sleep(1.5)
            self.launch_shopee_app()
            time.sleep(3.5)

    def format_age_seconds(self, seconds):
        seconds = max(0, int(seconds))
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}p"
        else:
            return f"{seconds // 3600}h"

    def do_start(self, args):
        if self.auto_hunting_enabled:
            print(f"{COLOR_YELLOW}[!] Auto da bat{COLOR_RESET}")
            return

        if not self.check_adb_device():
            print(f"{COLOR_RED}[-] ADB chua ket noi{COLOR_RESET}")
            return

        self.auto_hunting_enabled = True
        self.log("Auto", "BAT")
        self.auto_thread = threading.Thread(target=self.auto_hunter_worker, daemon=True)
        self.auto_thread.start()

    def do_stop(self, args):
        if not self.auto_hunting_enabled:
            print(f"{COLOR_YELLOW}[!] Auto da tat{COLOR_RESET}")
            return

        self.auto_hunting_enabled = False
        self.log("Auto", "TAT")

    def do_status(self, args):
        self.check_adb_device()
        adb_str = self.device_id if self.device_connected else "Chua ket noi"
        tele_str = f"{self.phone_number} ({self.user_name})" if self.user_authorized else "Chua dang nhap"
        auto_str = "ON" if self.auto_hunting_enabled else "OFF"

        print(f"ADB      : {adb_str}")
        print(f"Telegram : {tele_str}")
        print(f"Auto     : {auto_str}")
        print(f"Queue    : {len(self.latest_messages)} tin")
        print(f"Opened   : {len(self.opened_urls)} link")

    def do_latest(self, args):
        if not self.latest_messages:
            print("Chua co tin")
            return

        now = datetime.now(timezone.utc)
        for idx, msg in enumerate(self.latest_messages[:7]):
            d = msg.get("date")
            if d and d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            age = self.format_age_seconds((now - d).total_seconds()) if d else "N/A"
            coins = msg.get("coins", 0)
            slots = msg.get("slots", 0)
            url = msg.get("url")
            opened = "[X]" if url in self.opened_urls else "[ ]"
            print(f"[{idx+1}] {coins} xu | {slots} slot | {age} | {opened} {url}")

    def do_open(self, args):
        if not args:
            print(f"{COLOR_RED}[!] Cu phap: open <url>{COLOR_RESET}")
            return

        url = args[0].strip()
        if self.open_url_via_adb(url):
            self.opened_urls.add(url)
            print(f"{COLOR_GREEN}[+] OK{COLOR_RESET}")
        else:
            print(f"{COLOR_RED}[-] Loi{COLOR_RESET}")

    def do_otp(self, args):
        phone = args[0].strip() if args else self.phone_number
        if not phone:
            print(f"{COLOR_RED}[!] Cu phap: otp <sdt>{COLOR_RESET}")
            return

        phone = phone.replace(" ", "")
        if phone.startswith("0"):
            phone = "+84" + phone[1:]
        elif not phone.startswith("+"):
            phone = "+" + phone

        self.save_user_config(phone)
        print(f"[*] Gui OTP: {phone}")

        async def _req():
            try:
                self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH, loop=self.loop)
                await self.client.connect()
                if not await self.client.is_user_authorized():
                    res = await self.client.send_code_request(phone)
                    self.phone_code_hash = res.phone_code_hash
                    self.log("Tele", f"OTP da gui. Nhap: verify <ma>")
                else:
                    me = await self.client.get_me()
                    self.user_authorized = True
                    self.user_name = me.first_name or "User"
                    self.set_cmd_prompt(f"{self.user_name}@shopee> ")
                    self.log("Tele", f"Dang nhap: {self.user_name}")
                    await self._start_listening_async()
            except Exception as e:
                self.log("error", f"OTP: {e}")

        asyncio.run_coroutine_threadsafe(_req(), self.loop)

    def do_verify(self, args):
        if not args:
            print(f"{COLOR_RED}[!] Cu phap: verify <ma>{COLOR_RESET}")
            return

        code = args[0].strip()
        print(f"[*] Xac thuc: {code}")

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
                self.log("Tele", f"Dang nhap thanh cong: {self.user_name}")
                await self._start_listening_async()
            except Exception as e:
                self.log("error", f"Verify: {e}")

        asyncio.run_coroutine_threadsafe(_sub(), self.loop)

    def do_logout(self, args):
        if os.path.exists(f"{SESSION_NAME}.session"):
            try:
                os.remove(f"{SESSION_NAME}.session")
            except Exception:
                pass
        self.user_authorized = False
        self.user_name = "N/A"
        self.set_cmd_prompt("shopee> ")
        print(f"{COLOR_YELLOW}[+] Da dang xuat{COLOR_RESET}")

    def do_device(self, args):
        if self.check_adb_device():
            print(f"{COLOR_GREEN}[+] ADB: {self.device_id}{COLOR_RESET}")
        else:
            print(f"{COLOR_RED}[-] ADB: Chua ket noi{COLOR_RESET}")

    def do_clear(self, args):
        self.clear_screen()
        self.draw_header()

    def do_help(self, args):
        for name in sorted(self.commands.keys()):
            if name in ["cls", "exit"]:
                continue
            syntax = self.cmd_syntax.get(name, name)
            help_desc = self.cmd_help.get(name, "")
            print(f"  {syntax:14s} : {help_desc}")

    def draw_header(self):
        self.check_adb_device()
        adb_str = self.device_id if self.device_connected else "Chua ket noi"
        tele_str = f"{self.user_name} ({self.phone_number})" if self.user_authorized else "Chua dang nhap"
        auto_str = "ON" if self.auto_hunting_enabled else "OFF"

        print(f"[ADB: {adb_str} | Tele: {tele_str} | Auto: {auto_str}]")
        print("-" * 65)


if __name__ == "__main__":
    app = ShopeeCoinHunterCLI()
    app.draw_header()
    app.run()
