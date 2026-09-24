# Đồ án Công cụ phương pháp thiết kế & quản lý phần mềm - CS 434

Xây dựng Website hỗ trợ tìm kiếm địa điểm du lịch và đặt phòng ở Đà Nẵng

1. **Cách kết nối để xem được DB**
    - B1: Tải MySQL v8. và MySQL Workbench
    - B2: Sau khi tải xong vào MySQL Workbench tạo New Connection
    - B3: Nhập như sau:
      | Trường | Giá trị |
      |---------------|----------------------------------|
      |Connection Name|ưa đặt gì đó đặt |
      |Hostname |hopper.proxy.rlwy.net |
      |Port | 50949 |
      |Username | root |
      |Password | FBWIjbpQrQBmrCTBJbUXFZUIEzFMRMHW |
      |Default Schema | railway |
    - B4: OK để connect
    - **Lưu ý: Chỉ được sửa đổi cấu trúc dữ liệu trong DB khi cần dữ liệu để tương thích với giao diện, nếu sửa gì phải thông báo, còn nếu không thì hạn chế sửa**
    - **Đây là DB đã được host, vậy nên các máy cùng kết nối và dùng chung 1 DB**

2. **Cấu trúc source code**
    - Chức năng đăng nhập đăng ký xử lý sau
    - Hardcode ID của Customer, Host hay Admin để xử lý các chức năng đã

```
├── routes - Xử lý logic
│   ├── admin_routes.py     : Logic Admin
│   ├── auth_routes.py      : Logic Xác thực
│   ├── customer_routes.py  : Logic Khách hàng
│   ├── host_routes.py      : Logic Chủ cơ sở
│   └── public_routes.py    : Logic Dùng chung
├── templates - Giao diện
│   ├── admin
│   │   ├── accommodations_management.html  : Quản lý cơ sở
│   │   ├── dashboard.html                  : Bảng điều khiển
│   │   ├── destinations_management.html    : Quản lý địa điểm du lịch
│   │   ├── hosts_approval.html             : Kiểm duyệt Host mới
│   │   ├── notifications.html              : Quản lý thông báo cá nhân
│   │   ├── profile.html                    : Quản lý tài khoản cá nhân
│   │   ├── reviews_moderation.html         : Kiểm duyệt đánh giá
│   │   ├── system_reports.html             : Xuất báo cáo thống kê
│   │   └── users_management.html           : Quản lý người dùng
│   ├── auth
│   │   ├── login.html      : Đăng nhập
│   │   └── register.html   : Đăng ký
│   ├── customer
│   │   ├── booking_history.html  : Lịch sử đặt phòng
│   │   ├── checkout.html         : Thanh toán
│   │   ├── home.html             : Trang chủ
│   │   ├── notifications.html    : Quản lý thông báo cá nhân
│   │   ├── profile.html          : Quản lý tài khoản cá nhân
│   │   ├── review_form.html      : Viết đánh giá
│   │   └── wishlist.html         : Danh sách yêu thích
│   ├── host
│   │   ├── accommodation_info.html   : Quản lý thông tin cơ sở
│   │   ├── analytics.html            : Thống kê doanh thu
│   │   ├── bookings_management.html  : Quản lý đặt phòng
│   │   ├── dashboard.html            : Bảng điều khiển
│   │   ├── notifications.html        : Quản lý thông báo cá nhân
│   │   ├── profile.html              : Quản lý tài khoản cá nhân
│   │   ├── reviews.html              : Xem phản hồi KH
│   │   └── rooms_management.html     : Quản lý phòng
│   └── public
│       ├── destination_detail.html   : Chi tiết địa điểm du lịch
│       ├── home.html                 : Trang chủ
│       ├── room_detail.html          : Chi tiết phòng
│       ├── search_destinations.html  : Tìm kiếm địa điểm du lịch
│       └── search_rooms.html         : Tìm kiếm phòng
├── app.py              : File khởi chạy chính
├── config.py           : Cấu hình hệ thống
├── database.py         : Thiết lập kết nối DB
└── requirements.txt    : Thư viện cần cài
```
