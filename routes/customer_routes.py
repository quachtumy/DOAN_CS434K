from flask import Blueprint, render_template, session, redirect, url_for, request
from sqlalchemy import text
from database import db
from datetime import datetime

# Tạo Blueprint cho Customer
customer_bp = Blueprint('customer', __name__, url_prefix='/customer')

@customer_bp.route('/')
def home():
    user_id = session.get('user_id')
    role = session.get('role')
    
    if not user_id:
        return redirect(url_for('auth.login'))
    
    if role == 'Host':
        return redirect(url_for('host.dashboard'))
    elif role == 'Admin':
        return redirect('/admin')
        
    user = db.session.execute(text("SELECT full_name FROM Users WHERE user_id = :uid"), {'uid': user_id}).fetchone()
    
    b_count_result = db.session.execute(text("SELECT COUNT(*) as total FROM Bookings WHERE customer_id = :uid"), {'uid': user_id}).fetchone()
    total_bookings_count = b_count_result.total if b_count_result else 0
    
    tier_name = "Thành viên Đồng (Bronze Tier)"
    if total_bookings_count >= 5: tier_name = "Thành viên Vàng (Gold Tier)"
    elif total_bookings_count >= 2: tier_name = "Thành viên Bạc (Silver Tier)"

    dest_query = "SELECT destination_id, name, category, area, main_image FROM TouristDestinations ORDER BY rating DESC LIMIT 4"
    destinations_raw = db.session.execute(text(dest_query)).fetchall()
    
    destinations = []
    for d in destinations_raw:
        img = d.main_image if d.main_image else 'https://images.unsplash.com/photo-1583417319070-4a69db38a482?q=80&w=800'
        destinations.append({'id': d.destination_id, 'name': d.name, 'category': d.category, 'area': d.area, 'image': img})

    hotels_query = """
        SELECT a.accommodation_id, a.name as acc_name, a.address, a.images,
               MIN(r.price_per_night) as min_price,
               AVG(rv.rating) as avg_rating,
               COUNT(rv.review_id) as review_count
        FROM Accommodations a
        LEFT JOIN Rooms r ON a.accommodation_id = r.accommodation_id
        LEFT JOIN Reviews rv ON a.accommodation_id = rv.accommodation_id
        WHERE a.status = 'Approved'
        GROUP BY a.accommodation_id
        ORDER BY avg_rating DESC, review_count DESC
        LIMIT 3
    """
    hotels_raw = db.session.execute(text(hotels_query)).fetchall()
    
    hotels = []
    for h in hotels_raw:
        first_img = h.images.split('|')[0] if h.images else 'https://images.unsplash.com/photo-1566073771259-6a8506099945?q=80&w=800'
        min_price = float(h.min_price or 0)
        formatted_price = "{:,.0f}".format(min_price).replace(",", ".") + " ₫"
        rating = round(float(h.avg_rating or 5.0), 1)
        star_tier = "5 Sao" if min_price > 2000000 else ("4 Sao" if min_price > 1000000 else "3 Sao")
        
        hotels.append({
            'id': h.accommodation_id,
            'name': h.acc_name,
            'address': h.address,
            'image': first_img,
            'price': formatted_price,
            'rating': rating,
            'review_count': h.review_count or 0,
            'star': star_tier
        })

    bookings_query = """
        SELECT b.booking_id, b.status, b.check_in_date, b.check_out_date, b.total_price, a.name as acc_name
        FROM Bookings b
        JOIN Rooms r ON b.room_id = r.room_id
        JOIN Accommodations a ON r.accommodation_id = a.accommodation_id
        WHERE b.customer_id = :uid
        ORDER BY b.created_at DESC LIMIT 2
    """
    bookings_raw = db.session.execute(text(bookings_query), {'uid': user_id}).fetchall()
    
    bookings = []
    for b in bookings_raw:
        nights = (b.check_out_date - b.check_in_date).days if b.check_out_date and b.check_in_date else 1
        nights = nights if nights > 0 else 1
        ci_str = b.check_in_date.strftime("%d Th%m, %Y") if b.check_in_date else ""
        co_str = b.check_out_date.strftime("%d Th%m, %Y") if b.check_out_date else ""
        
        ui_status = {'text': 'Chờ xác nhận', 'bg': 'bg-primary-container', 'text_color': 'text-on-primary-container', 'icon': 'hourglass_empty'}
        if b.status == 'Confirmed': ui_status = {'text': 'Đã xác nhận', 'bg': 'bg-secondary-fixed', 'text_color': 'text-on-secondary-fixed', 'icon': 'hotel'}
        elif b.status == 'Completed': ui_status = {'text': 'Đã hoàn thành', 'bg': 'bg-surface-container-high', 'text_color': 'text-on-surface-variant', 'icon': 'check_circle'}
        elif b.status == 'Cancelled': ui_status = {'text': 'Đã hủy', 'bg': 'bg-error-container', 'text_color': 'text-on-error-container', 'icon': 'cancel'}
            
        bookings.append({
            'id': b.booking_id,
            'code': f"DN-{b.booking_id * 1024}",
            'acc_name': b.acc_name,
            'date_str': f"{ci_str} - {co_str} ({nights} đêm)",
            'price': "{:,.0f}".format(float(b.total_price)).replace(",", ".") + " ₫",
            'status': ui_status
        })

    return render_template('customer/home.html', 
                           user=user, 
                           tier=tier_name,
                           destinations=destinations, 
                           hotels=hotels, 
                           bookings=bookings, 
                           total_bookings=total_bookings_count)

@customer_bp.route('/booking', methods=['GET', 'POST'])
def booking():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    room_id = request.args.get('room_id')

    if not room_id:
        return "Không tìm thấy phòng cần đặt.", 400

    query = """
        SELECT room_id,
               room_name,
               price_per_night,
               capacity
        FROM Rooms
        WHERE room_id = :room_id
          AND status = 'Available'
    """

    room = db.session.execute(
        text(query),
        {'room_id': room_id}
    ).fetchone()

    if not room:
        return "Phòng không tồn tại hoặc hiện không còn trống.", 404

    if request.method == 'POST':
        check_in_date = request.form.get('check_in_date')
        check_out_date = request.form.get('check_out_date')
        guest_name = request.form.get('guest_name')
        guest_phone = request.form.get('guest_phone')

        from datetime import datetime

        try:
            check_in = datetime.strptime(
                check_in_date, '%Y-%m-%d'
            ).date()

            check_out = datetime.strptime(
                check_out_date, '%Y-%m-%d'
            ).date()
        except (ValueError, TypeError):
            return "Ngày nhận hoặc ngày trả không hợp lệ.", 400

        if check_out <= check_in:
            error_message = 'Ngày trả phòng phải sau ngày nhận phòng.'
            return render_template(
                'customer/booking.html',
                room=room,
                error_message=error_message
            )

        number_of_nights = (check_out - check_in).days

        total_price = (
            room.price_per_night * number_of_nights
        )
        
        customer_id = session.get('user_id')

        insert_query = """
            INSERT INTO Bookings (
                customer_id,
                room_id,
                check_in_date,
                check_out_date,
                total_price,
                guest_name,
                guest_phone
            )
            VALUES (
                :customer_id,
                :room_id,
                :check_in_date,
                :check_out_date,
                :total_price,
                :guest_name,
                :guest_phone
            )
        """

        result = db.session.execute(
            text(insert_query),
            {
                'customer_id': customer_id,
                'room_id': room.room_id,
                'check_in_date': check_in,
                'check_out_date': check_out,
                'total_price': total_price,
                'guest_name': guest_name,
                'guest_phone': guest_phone
            }
        )

        db.session.commit()

        booking_id = result.lastrowid

        return render_template(
            'customer/booking_success.html',
            booking_id=booking_id,
            room=room,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            number_of_nights=number_of_nights,
            total_price=total_price,
            guest_name=guest_name,
            guest_phone=guest_phone
        )

    return render_template(
        'customer/booking.html',
        room=room
    )

@customer_bp.route('/profile')
def profile():
    return render_template('customer/profile.html')

@customer_bp.route('/wishlist')
def wishlist():
    return render_template('customer/wishlist.html')

@customer_bp.route('/booking-history')
def booking_history():
    return render_template('customer/booking_history.html')

@customer_bp.route('/notifications')
def notifications():
    return render_template('customer/notifications.html')