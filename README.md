# 🎯 Shopee Coin Hunter - Auto Săn Xu Livestream Qua ADB & OCR

Công cụ tự động lắng nghe tin nhắn chia sẻ link xu từ kênh Telegram, tự động mở livestream Shopee qua ADB trên thiết bị Android, nhận diện hình ảnh/OCR để chờ đếm ngược và bấm nhận xu (có cơ chế chống auto-click giả lập hành vi người dùng).

---

## ⚡ Các Tính Năng Chính

* **Lắng nghe Telegram theo thời gian thực (Userbot Telethon)**:
  * Tự động lọc các link gửi trong vòng 1 phút gần nhất.
  * Ưu tiên mở link: Nhiều Xu nhất > Nhiều Lượt nhất > Mới nhất.
  * Tự động chờ khi link mới nhất gửi cách đây quá 3 phút.

* **Nhận diện hình ảnh & OCR thông minh (OpenCV + RapidOCR)**:
  * **Check biểu tượng "PHẦN THƯỞNG"**: Nếu không thấy biểu tượng này (lỗi hoặc Shopee phát hiện bot) $\rightarrow$ Thoát app Shopee, mở lại app để làm mới phiên rồi mới tiếp tục nhận link.
  * **Check ô xu thời gian > 4 phút**: Tự động bóc tách thời gian đếm ngược để loại bỏ các ô nhận xu ngắn từ việc lướt video / điểm danh (30s, 1p). Chỉ săn các phòng livestream có sự kiện xu $\ge 4$ phút.
  * **Đợi đếm ngược và bấm nhận xu**: Chờ đến khi dòng chữ chuyển thành *"Nhấn để nhận thưởng!"* và nút `Lưu` sáng màu cam $\rightarrow$ Tự động bấm nhận thưởng.

* **Cơ chế Chống Auto-Click (Human-like Tap)**:
  * Tọa độ nhấn ngẫu nhiên trong vùng nút.
  * Độ trễ phản xạ ngẫu nhiên (0.35s - 0.75s).
  * Thời gian chạm giữ thực tế (90ms - 140ms).
  * Micro-jitter (độ rung ngón tay tiếp xúc 1-2px).

* **Giao diện trực quan (CustomTkinter)**:
  * Đăng nhập Telegram bằng OTP trực tiếp trên giao diện.
  * Xem trạng thái kết nối thiết bị ADB.
  * Hiển thị trạng thái hoạt động và 3 tin nhắn link mới nhất kèm thời gian.

---

## 🛠 Yêu Cầu Cài Đặt

1. **Python**: Phiên bản 3.10 trở lên.
2. **Android Debug Bridge (ADB)**:
   * Bật **Tùy chọn cho nhà phát triển (Developer Options)** trên điện thoại.
   * Bật **Gỡ lỗi USB (USB Debugging)**.
   * Kết nối điện thoại với máy tính qua cáp USB và gõ lệnh `adb devices` để kiểm tra kết nối.

---

## 🚀 Hướng Dẫn Sử Dụng

1. **Cài đặt thư viện**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Khởi chạy ứng dụng**:
   ```bash
   python "tool v2.py"
   ```

3. **Thao tác trên giao diện**:
   * Nhập số điện thoại Telegram của bạn (ví dụ: `0357677359` hoặc `+84357677359`).
   * Bấm **Lấy Mã OTP**, nhập mã OTP gửi về app Telegram và xác nhận.
   * Bấm **▶ BẬT TỰ ĐỘNG SĂN XU** để bắt đầu.
