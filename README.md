# 🎯 Shopee Coin Hunter - CLI Controller (@xueshopee)

Công cụ tự động lắng nghe tin nhắn chia sẻ link xu từ kênh Telegram, tự động mở livestream Shopee qua ADB trên thiết bị Android, nhận diện hình ảnh/OCR để chờ đếm ngược và bấm nhận xu (có cơ chế chống auto-click giả lập hành vi người dùng).

Giao diện dòng lệnh (CLI) được thiết kế theo kiến trúc `CmdLineInterface` (tương tự mẫu C++ trong `D:\C++`), phân chia rõ rệt thành 2 phần:
* **Phần 1: Nhật ký hoạt động (Logs & Status)** theo thời gian thực.
* **Phần 2: Dòng lệnh nhập (Command Prompt)** tương tác trực tiếp (`shopee> `).

---

## ⚡ Các Tính Năng & Kịch Bản Tự Động

1. **Khởi động**: Tự động mở app Shopee về trang chủ sẵn sàng.
2. **Nhận link Telegram**: Lắng nghe kênh `@xueshopee` qua Telethon Userbot.
   * Lọc link gửi trong vòng 1 phút gần nhất.
   * Ưu tiên mở link: **Nhiều Xu nhất > Nhiều Lượt nhất > Mới nhất**.
   * Nếu link mới nhất > 3 phút: Tự động chờ tin mới.
3. **Check biểu tượng "PHẦN THƯỞNG"**:
   * Quét góc trên bên phải màn hình kiểm tra banner "PHẦN THƯỞNG".
   * Nếu không có (nghi ngờ lỗi hoặc Shopee phát hiện bot): Tắt app Shopee, mở lại app để làm mới phiên rồi mới tiếp tục nhận link.
4. **Check ô xu thời gian > 4 phút**:
   * OCR bóc tách thời gian đếm ngược để loại bỏ ô nhận xu lướt video / điểm danh ngắn (30s, 1p).
   * Chỉ săn các phòng livestream có sự kiện xu $\ge 4$ phút.
   * Nếu không có ô xu $> 4$p: Thoát Shopee, mở lại và chuyển sang link khác.
5. **Nhận xu & Chống Auto-Click (Human-like Tap)**:
   * Chờ hết giờ đến khi hiện *"Nhấn để nhận thưởng!"* và nút `Lưu` sáng màu cam.
   * Bấm `Lưu` với tọa độ ngẫu nhiên lệch vùng nút, trễ phản xạ tự nhiên (0.35s - 0.75s), micro-jitter 1-2px, thời gian chạm giữ thực tế (90ms - 140ms).
   * Đợi 3s $\rightarrow$ Thoát Shopee $\rightarrow$ Mở lại Shopee $\rightarrow$ Nhận link mới.

---

## 🛠 Danh Sách Lệnh CLI

| Lệnh | Cú pháp | Mô tả |
| :--- | :--- | :--- |
| `start` | `start` | Bật chế độ tự động săn xu theo kịch bản |
| `stop` | `stop` | Dừng chế độ tự động săn xu |
| `status` | `status` | Xem chi tiết trạng thái hệ thống (ADB, Tele, Auto) |
| `latest` | `latest` | Xem danh sách tin nhắn / link mới nhất từ Telegram |
| `open` | `open <url>` | Mở link Shopee thủ công qua ADB |
| `otp` | `otp [sdt]` | Gửi mã OTP đăng nhập Telegram (VD: `otp 0357677359`) |
| `verify` | `verify <code>` | Xác nhận mã OTP gồm 5 chữ số từ Telegram |
| `logout` | `logout` | Đăng xuất tài khoản Telegram và xóa phiên |
| `device` | `device` | Kiểm tra / làm mới kết nối thiết bị ADB |
| `clear` / `cls` | `clear` | Xóa màn hình và vẽ lại giao diện chia 2 phần |
| `help` | `help` | Hiển thị bảng hướng dẫn danh sách lệnh |
| `quit` / `exit` | `quit` | Thoát chương trình an toàn |

---

## 🚀 Hướng Dẫn Sử Dụng

1. **Cài đặt thư viện**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Khởi chạy ứng dụng CLI**:
   ```bash
   python main.py
   ```

3. **Thao tác**:
   * Tại dấu nhắc `shopee> `, gõ `status` để kiểm tra kết nối thiết bị ADB và Telegram.
   * Gõ `start` để bắt đầu kịch bản tự động săn xu.
   * Gõ `stop` khi muốn dừng lại.
