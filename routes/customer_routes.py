from flask import Blueprint, request, render_template, redirect, url_for
from sqlalchemy import text

from database import db
from flask import session


customer_bp = Blueprint('customer', __name__)


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