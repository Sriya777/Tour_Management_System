from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import database as db
import json
from datetime import datetime
import re
import random


app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Helper function for password validation
def is_valid_password(password):
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
    return True, ""

# Helper function for email validation
def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# Authentication routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        query = "SELECT * FROM users WHERE username = %s AND password = %s"
        user = db.execute_query(query, (username, password), fetch=True)
        
        if user:
            session['user_id'] = user[0]['id']
            session['username'] = user[0]['username']
            session['user_type'] = user[0]['user_type']
            session['full_name'] = user[0].get('full_name', '')
            
            if user[0]['user_type'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials. Please try again.', 'error')
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        email = request.form['email']
        full_name = request.form['full_name']
        phone = request.form.get('phone', '')
        user_type = request.form['user_type']
        
        # Debug logging
        print(f"Registration attempt: {username}, {email}")
        
        # Validation
        errors = []
        
        if password != confirm_password:
            errors.append('Passwords do not match!')
        
        is_valid, pwd_msg = is_valid_password(password)
        if not is_valid:
            errors.append(pwd_msg)
        
        if not is_valid_email(email):
            errors.append('Please enter a valid email address')
        
        if not username or not email or not full_name:
            errors.append('All required fields must be filled')
        
        # Check if username or email already exists
        if not errors:
            check_query = "SELECT id FROM users WHERE username = %s OR email = %s"
            existing_user = db.execute_query(check_query, (username, email), fetch=True)
            
            if existing_user:
                errors.append('Username or email already exists!')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register.html', 
                                 form_data=request.form)  # Pass form data back to repopulate
        
        # Insert new user
        insert_query = """
        INSERT INTO users (username, password, email, full_name, phone, user_type)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        result = db.execute_query(insert_query, (username, password, email, full_name, phone, user_type))
        
        if result:
            print(f"User registered successfully: {username}")
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            print("Registration failed - database error")
            flash('Registration failed due to database error. Please try again.', 'error')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

# User routes
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    try:
        # Get user stats
        bookings_query = "SELECT COUNT(*) as count FROM bookings WHERE user_id = %s"
        bookings_result = db.execute_query(bookings_query, (user_id,), fetch=True)
        bookings_count = bookings_result[0]['count'] if bookings_result else 0
        
        packages_query = "SELECT COUNT(*) as count FROM packages WHERE is_active = TRUE"
        packages_result = db.execute_query(packages_query, fetch=True)
        packages_count = packages_result[0]['count'] if packages_result else 0
        
        # Get total spent
        total_spent_query = "SELECT SUM(total_amount) as total FROM bookings WHERE user_id = %s AND status = 'confirmed'"
        total_spent_result = db.execute_query(total_spent_query, (user_id,), fetch=True)
        total_spent = total_spent_result[0]['total'] if total_spent_result and total_spent_result[0]['total'] else 0
        
        # Get pending bookings count
        pending_bookings_query = "SELECT COUNT(*) as count FROM bookings WHERE user_id = %s AND status = 'pending'"
        pending_bookings_result = db.execute_query(pending_bookings_query, (user_id,), fetch=True)
        pending_bookings_count = pending_bookings_result[0]['count'] if pending_bookings_result else 0
        
        # Recent bookings (last 5)
        recent_bookings_query = """
        SELECT b.*, p.name as package_name, p.destination, p.image_url, p.duration_days
        FROM bookings b 
        JOIN packages p ON b.package_id = p.id 
        WHERE b.user_id = %s 
        ORDER BY b.booking_date DESC 
        LIMIT 5
        """
        recent_bookings = db.execute_query(recent_bookings_query, (user_id,), fetch=True) or []
        
        # Recommended packages (based on user's preferences and booking history)
        recommended_query = """
        SELECT p.*, 
               COUNT(b.id) as popularity,
               (SELECT AVG(rating) FROM feedback WHERE package_id = p.id) as avg_rating
        FROM packages p
        LEFT JOIN bookings b ON p.id = b.package_id
        WHERE p.is_active = TRUE
        AND p.id NOT IN (SELECT package_id FROM bookings WHERE user_id = %s)
        GROUP BY p.id
        ORDER BY 
            CASE WHEN p.category IN (
                SELECT DISTINCT p2.category 
                FROM bookings b2 
                JOIN packages p2 ON b2.package_id = p2.id 
                WHERE b2.user_id = %s
            ) THEN 1 ELSE 0 END DESC,
            popularity DESC,
            avg_rating DESC
        LIMIT 6
        """
        recommended_packages = db.execute_query(recommended_query, (user_id, user_id), fetch=True) or []
        
        # If no recommendations based on history, show popular packages
        if not recommended_packages:
            popular_query = """
            SELECT p.*, 
                   COUNT(b.id) as booking_count,
                   (SELECT AVG(rating) FROM feedback WHERE package_id = p.id) as avg_rating
            FROM packages p
            LEFT JOIN bookings b ON p.id = b.package_id
            WHERE p.is_active = TRUE
            GROUP BY p.id
            ORDER BY booking_count DESC, avg_rating DESC
            LIMIT 6
            """
            recommended_packages = db.execute_query(popular_query, fetch=True) or []
        
        # Get user's favorite categories
        favorite_categories_query = """
        SELECT p.category, COUNT(*) as booking_count
        FROM bookings b
        JOIN packages p ON b.package_id = p.id
        WHERE b.user_id = %s
        GROUP BY p.category
        ORDER BY booking_count DESC
        LIMIT 3
        """
        favorite_categories = db.execute_query(favorite_categories_query, (user_id,), fetch=True) or []
        
        # Upcoming trips (confirmed bookings in future)
        upcoming_trips_query = """
        SELECT b.*, p.name as package_name, p.destination, p.image_url, p.duration_days
        FROM bookings b 
        JOIN packages p ON b.package_id = p.id 
        WHERE b.user_id = %s 
        AND b.status = 'confirmed'
        ORDER BY b.booking_date ASC
        LIMIT 3
        """
        upcoming_trips = db.execute_query(upcoming_trips_query, (user_id,), fetch=True) or []
        
        # Recent activity (bookings + feedback)
        recent_activity_query = """
        (SELECT 
            'booking' as type,
            b.booking_date as date,
            p.name as title,
            b.status as status,
            CONCAT('Booked ', p.name) as description,
            p.image_url
         FROM bookings b
         JOIN packages p ON b.package_id = p.id
         WHERE b.user_id = %s
         ORDER BY b.booking_date DESC
         LIMIT 5)
         
        UNION ALL
         
        (SELECT 
            'feedback' as type,
            f.created_at as date,
            p.name as title,
            'completed' as status,
            CONCAT('Rated ', p.name, ' - ', f.rating, ' stars') as description,
            p.image_url
         FROM feedback f
         JOIN packages p ON f.package_id = p.id
         WHERE f.user_id = %s
         ORDER BY f.created_at DESC
         LIMIT 5)
         
        ORDER BY date DESC
        LIMIT 8
        """
        recent_activity = db.execute_query(recent_activity_query, (user_id, user_id), fetch=True) or []
        
        # Travel statistics
        destinations_visited_query = """
        SELECT COUNT(DISTINCT p.destination) as count
        FROM bookings b
        JOIN packages p ON b.package_id = p.id
        WHERE b.user_id = %s AND b.status = 'confirmed'
        """
        destinations_visited_result = db.execute_query(destinations_visited_query, (user_id,), fetch=True)
        destinations_visited = destinations_visited_result[0]['count'] if destinations_visited_result else 0
        
        # Average rating given by user
        avg_rating_query = """
        SELECT AVG(rating) as avg_rating
        FROM feedback
        WHERE user_id = %s
        """
        avg_rating_result = db.execute_query(avg_rating_query, (user_id,), fetch=True)
        avg_rating = round(avg_rating_result[0]['avg_rating'], 1) if avg_rating_result and avg_rating_result[0]['avg_rating'] else 0
        
        return render_template('dashboard.html', 
                             username=session['username'],
                             full_name=session.get('full_name', ''),
                             user_type=session.get('user_type', 'user'),
                             bookings_count=bookings_count,
                             packages_count=packages_count,
                             pending_bookings_count=pending_bookings_count,
                             total_spent=total_spent,
                             destinations_visited=destinations_visited,
                             avg_rating=avg_rating,
                             recent_bookings=recent_bookings,
                             recommended_packages=recommended_packages,
                             favorite_categories=favorite_categories,
                             upcoming_trips=upcoming_trips,
                             recent_activity=recent_activity)
    
    except Exception as e:
        print(f"Error in dashboard: {e}")
        # Return basic dashboard even if there are errors
        return render_template('dashboard.html',
                             username=session['username'],
                             full_name=session.get('full_name', ''),
                             user_type=session.get('user_type', 'user'),
                             bookings_count=0,
                             packages_count=0,
                             pending_bookings_count=0,
                             total_spent=0,
                             destinations_visited=0,
                             avg_rating=0,
                             recent_bookings=[],
                             recommended_packages=[],
                             favorite_categories=[],
                             upcoming_trips=[],
                             recent_activity=[])

@app.route('/packages')
def packages():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    category = request.args.get('category', '')
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'name')
    
    query = "SELECT * FROM packages WHERE is_active = TRUE"
    params = []
    
    if category:
        query += " AND category = %s"
        params.append(category)
    
    if search:
        query += " AND (name LIKE %s OR destination LIKE %s OR description LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    
    # Improved sorting
    if sort == 'price_low':
        query += " ORDER BY price ASC"
    elif sort == 'price_high':
        query += " ORDER BY price DESC"
    elif sort == 'duration':
        query += " ORDER BY duration_days DESC"
    elif sort == 'slots':
        query += " ORDER BY available_slots DESC"
    else:  # name
        query += " ORDER BY name ASC"
    
    packages_data = db.execute_query(query, params, fetch=True) or []
    
    return render_template('packages.html', packages=packages_data)

@app.route('/package/<int:package_id>')
def package_detail(package_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    query = "SELECT * FROM packages WHERE id = %s AND is_active = TRUE"
    package = db.execute_query(query, (package_id,), fetch=True)
    
    if not package:
        flash('Package not found or unavailable.', 'error')
        return redirect(url_for('packages'))
    
    # Get feedback for this package
    feedback_query = """
    SELECT f.*, u.username, u.full_name
    FROM feedback f 
    JOIN users u ON f.user_id = u.id 
    WHERE f.package_id = %s 
    ORDER BY f.created_at DESC
    """
    feedback = db.execute_query(feedback_query, (package_id,), fetch=True) or []
    
    # Calculate average rating
    avg_rating_query = "SELECT AVG(rating) as avg_rating FROM feedback WHERE package_id = %s"
    avg_rating_result = db.execute_query(avg_rating_query, (package_id,), fetch=True)
    avg_rating = avg_rating_result[0]['avg_rating'] if avg_rating_result and avg_rating_result[0]['avg_rating'] else 0
    
    return render_template('package_detail.html', 
                         package=package[0], 
                         feedback=feedback, 
                         avg_rating=round(avg_rating, 1))

# Remove the old book_package route and replace it with this:

@app.route('/book_package/<int:package_id>', methods=['POST'])
def book_package(package_id):
    if 'user_id' not in session:
        flash('Please login to book packages.', 'error')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    travelers_count = int(request.form['travelers_count'])
    travel_date = request.form['travel_date']
    
    # Get package details
    package_query = "SELECT * FROM packages WHERE id = %s AND is_active = TRUE"
    package = db.execute_query(package_query, (package_id,), fetch=True)
    
    if not package:
        flash('Package not found or unavailable.', 'error')
        return redirect(url_for('packages'))
    
    package = package[0]
    
    # Check availability
    if package['available_slots'] < travelers_count:
        flash(f'Only {package["available_slots"]} slots available for this package.', 'error')
        return redirect(url_for('package_detail', package_id=package_id))
    
    total_amount = package['price'] * travelers_count
    
    # Create booking with pending payment status
    booking_query = """
    INSERT INTO bookings (user_id, package_id, travelers_count, total_amount, status, payment_status)
    VALUES (%s, %s, %s, %s, 'pending', 'pending')
    """
    result = db.execute_query(booking_query, (user_id, package_id, travelers_count, total_amount))
    
    if result:
        # Get the booking ID
        booking_id_query = "SELECT LAST_INSERT_ID() as booking_id"
        booking_id_result = db.execute_query(booking_id_query, fetch=True)
        booking_id = booking_id_result[0]['booking_id'] if booking_id_result else None
        
        # Redirect to payment page
        return redirect(url_for('payment_page', booking_id=booking_id))
    else:
        flash('Booking failed. Please try again.', 'error')
        return redirect(url_for('package_detail', package_id=package_id))

# Payment System Routes
@app.route('/payment/<int:booking_id>')
def payment_page(booking_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get booking details
    booking_query = """
    SELECT b.*, p.name as package_name, p.destination, p.duration_days, u.full_name, u.email
    FROM bookings b 
    JOIN packages p ON b.package_id = p.id 
    JOIN users u ON b.user_id = u.id 
    WHERE b.id = %s AND b.user_id = %s
    """
    booking = db.execute_query(booking_query, (booking_id, session['user_id']), fetch=True)
    
    if not booking:
        flash('Booking not found.', 'error')
        return redirect(url_for('bookings'))
    
    booking = booking[0]
    
    return render_template('payment.html', booking=booking)

@app.route('/process_payment/<int:booking_id>', methods=['POST'])
def process_payment(booking_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login first'})
    
    try:
        card_number = request.form['card_number']
        card_holder = request.form['card_holder']
        expiry_date = request.form['expiry_date']
        cvv = request.form['cvv']
        
        # Simple validation (in real app, use proper payment gateway)
        if len(card_number.replace(' ', '')) != 16 or not card_number.replace(' ', '').isdigit():
            return jsonify({'success': False, 'message': 'Invalid card number'})
        
        if len(cvv) != 3 or not cvv.isdigit():
            return jsonify({'success': False, 'message': 'Invalid CVV'})
        
        # Simulate payment processing
        import random
        transaction_id = f"TXN{random.randint(100000, 999999)}"
        
        # Update booking with payment details
        update_query = """
        UPDATE bookings 
        SET status = 'confirmed', 
            payment_status = 'completed',
            payment_method = 'Credit Card',
            transaction_id = %s,
            card_last_four = %s,
            payment_date = NOW()
        WHERE id = %s AND user_id = %s
        """
        result = db.execute_query(update_query, (
            transaction_id, 
            card_number[-4:], 
            booking_id, 
            session['user_id']
        ))
        
        if result:
            # Update package available slots
            booking_query = "SELECT * FROM bookings WHERE id = %s"
            booking = db.execute_query(booking_query, (booking_id,), fetch=True)
            if booking:
                update_slots_query = "UPDATE packages SET available_slots = available_slots - %s WHERE id = %s"
                db.execute_query(update_slots_query, (booking[0]['travelers_count'], booking[0]['package_id']))
            
            return jsonify({
                'success': True, 
                'message': 'Payment successful!',
                'transaction_id': transaction_id
            })
        else:
            return jsonify({'success': False, 'message': 'Payment processing failed'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Payment error: {str(e)}'})

@app.route('/booking_confirmation/<int:booking_id>')
def booking_confirmation(booking_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get booking details
    booking_query = """
    SELECT b.*, p.name as package_name, p.destination, p.duration_days, p.image_url,
           u.full_name, u.email, u.phone
    FROM bookings b 
    JOIN packages p ON b.package_id = p.id 
    JOIN users u ON b.user_id = u.id 
    WHERE b.id = %s AND b.user_id = %s
    """
    booking = db.execute_query(booking_query, (booking_id, session['user_id']), fetch=True)
    
    if not booking:
        flash('Booking not found.', 'error')
        return redirect(url_for('bookings'))
    
    return render_template('booking_confirmation.html', booking=booking[0])

# AI Chatbot Routes (add these at the end of your routes)
# AI Chatbot Routes
@app.route('/chatbot')
def chatbot():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('chatbot.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Please login first'}), 401
    
    user_message = request.json.get('message', '').lower().strip()
    
    # Generate bot response based on user message
    bot_response = generate_chatbot_response(user_message, session['user_id'])
    
    # Save conversation to database (optional)
    try:
        query = """
        INSERT INTO chatbot_conversations (user_id, session_id, user_message, bot_response)
        VALUES (%s, %s, %s, %s)
        """
        db.execute_query(query, (session['user_id'], session.sid, user_message, bot_response))
    except:
        pass  # Skip if saving fails
    
    return jsonify({'response': bot_response})

def generate_chatbot_response(user_message, user_id):
    """Simple AI chatbot that suggests Indian travel destinations"""
    
    # Greeting patterns
    greetings = ['hi', 'hello', 'hey', 'hola', 'namaste']
    if any(greet in user_message for greet in greetings):
        return "Namaste! 👋 I'm your travel assistant. I can help you discover amazing places in India! Where would you like to go? You can ask about beaches, mountains, cultural sites, adventure, or budget travel."
    
    # Help patterns
    if 'help' in user_message or 'what can you do' in user_message:
        return "I can help you: 🌴 Suggest travel destinations in India 💰 Recommend packages based on your budget 🏔️ Tell you about different types of tourism 🎯 Help you choose based on your interests Just tell me what you're looking for!"
    
    # Destination suggestions based on keywords
    responses = {
        'beach': "🏖️ Perfect! For beaches, I recommend:\n• Goa - Famous beaches & nightlife\n• Andaman - Crystal clear waters\n• Kerala - Serene backwaters & beaches\n• Karnataka - Unexplored coastal beauty\nWould you like details about any specific beach destination?",
        
        'mountain': "🏔️ Great choice! Mountain destinations:\n• Himachal - Manali, Shimla, Dharamshala\n• Uttarakhand - Rishikesh, Mussoorie, Nainital\n• Sikkim - Gangtok, beautiful monasteries\n• Kashmir - Paradise on earth\nWhich region interests you most?",
        
        'cultural': "🏛️ India's rich culture awaits!\n• Rajasthan - Palaces & forts\n• Varanasi - Spiritual capital\n• Tamil Nadu - Ancient temples\n• Delhi/Agra - Historical monuments\n• Kerala - Traditional art forms\nTell me which aspect of culture interests you!",
        
        'adventure': "🚀 Adventure time!\n• Rishikesh - River rafting & bungee\n• Manali - Trekking & skiing\n• Ladakh - Motorcycle trips\n• Andaman - Scuba diving\n• Goa - Water sports\nWhat kind of adventure excites you?",
        
        'budget': "💰 Budget-friendly options:\n• Rishikesh - Spiritual & affordable\n• McLeod Ganj - Tibetan culture\n• Hampi - Ancient ruins\n• Pushkar - Cultural experience\n• Varkala - Cliff beach\nWhat's your budget range?",
        
        'luxury': "✨ Luxury experiences:\n• Udaipur - Palace hotels\n• Kerala - Luxury houseboats\n• Goa - 5-star beach resorts\n• Jaipur - Heritage palaces\n• Shimla - Luxury mountain resorts\nInterested in any specific luxury experience?",
        
        'wildlife': "🦁 Wildlife adventures:\n• Ranthambore - Tiger safari\n• Jim Corbett - Oldest national park\n• Kaziranga - One-horned rhinos\n• Gir - Asiatic lions\n• Periyar - Elephant reserve\nWhich wildlife experience interests you?",
        
        'spiritual': "🕉️ Spiritual journeys:\n• Varanasi - Ganga Aarti\n• Amritsar - Golden Temple\n• Bodh Gaya - Buddhist pilgrimage\n• Tirupati - Temple visit\n• Haridwar - Religious ceremonies\nLooking for any specific spiritual experience?"
    }
    
    # Check for keywords in user message
    for keyword, response in responses.items():
        if keyword in user_message:
            return response
    
    # Budget queries
    if 'cheap' in user_message or 'low budget' in user_message or 'economy' in user_message:
        return "For budget travel (under ₹10,000):\n• Rishikesh - Yoga & adventure\n• McLeod Ganj - Tibetan culture\n• Hampi - Ancient ruins\n• Pushkar - Desert culture\n• Varkala - Cliff beach\nWould you like package details?"
    
    if 'medium' in user_message or 'moderate' in user_message or '15k' in user_message or '20k' in user_message:
        return "For moderate budget (₹15,000-25,000):\n• Goa - Beach vacation\n• Manali - Mountain escape\n• Rajasthan - Cultural tour\n• Kerala - Backwaters\n• Andaman - Island adventure\nShall I show you available packages?"
    
    if 'expensive' in user_message or 'luxury' in user_message or 'high' in user_message or '30k' in user_message:
        return "For luxury experiences (₹30,000+):\n• Udaipur - Palace stay\n• Kerala - Luxury houseboat\n• Goa - 5-star resorts\n• Shimla - Luxury mountain retreat\n• Andaman - Private island experience\nInterested in luxury packages?"
    
    # Package booking related
    if 'book' in user_message or 'package' in user_message or 'tour' in user_message:
        return "Great! You can browse all available packages in the 'Packages' section. Once you find one you like, click 'Book Now' and I'll guide you through the payment process. Would you like me to show you some popular packages?"
    
    # Payment related
    if 'payment' in user_message or 'pay' in user_message or 'card' in user_message or 'bank' in user_message:
        return "Our payment process is secure and easy:\n1. Select your package\n2. Choose number of travelers\n3. Review booking summary\n4. Enter payment details\n5. Get instant confirmation\nAll major credit/debit cards and UPI are accepted! 💳"
    
    # Default response
    default_responses = [
        "I'd love to help you plan your Indian adventure! Tell me what kind of experience you're looking for - beaches, mountains, culture, adventure, or something else?",
        "India has so much to offer! Are you interested in spiritual journeys, wildlife safaris, luxury stays, or budget travel?",
        "Let me help you discover incredible destinations! What's your travel style - relaxing beaches, adventurous mountains, cultural heritage, or spiritual retreats?",
        "I can suggest amazing places based on your interests. Do you prefer nature, history, adventure, relaxation, or cultural experiences?"
    ]
    
    return random.choice(default_responses)

@app.route('/bookings')
def bookings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    query = """
    SELECT b.*, p.name as package_name, p.destination, p.price, p.duration_days, p.image_url
    FROM bookings b 
    JOIN packages p ON b.package_id = p.id 
    WHERE b.user_id = %s 
    ORDER BY b.booking_date DESC
    """
    bookings_data = db.execute_query(query, (user_id,), fetch=True) or []
    
    return render_template('bookings.html', bookings=bookings_data)

@app.route('/cancel_booking/<int:booking_id>')
def cancel_booking(booking_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get booking details first
    booking_query = "SELECT * FROM bookings WHERE id = %s AND user_id = %s"
    booking = db.execute_query(booking_query, (booking_id, session['user_id']), fetch=True)
    
    if not booking:
        flash('Booking not found.', 'error')
        return redirect(url_for('bookings'))
    
    # Update booking status and restore slots
    update_query = "UPDATE bookings SET status = 'cancelled' WHERE id = %s"
    result = db.execute_query(update_query, (booking_id,))
    
    if result:
        # Restore available slots
        restore_slots_query = "UPDATE packages SET available_slots = available_slots + %s WHERE id = %s"
        db.execute_query(restore_slots_query, (booking[0]['travelers_count'], booking[0]['package_id']))
        flash('Booking cancelled successfully.', 'success')
    else:
        flash('Failed to cancel booking.', 'error')
    
    return redirect(url_for('bookings'))

@app.route('/feedback')
def feedback():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    # Get user's completed bookings for feedback
    bookings_query = """
    SELECT b.*, p.name as package_name, p.destination
    FROM bookings b 
    JOIN packages p ON b.package_id = p.id 
    WHERE b.user_id = %s AND b.status = 'confirmed'
    AND b.package_id NOT IN (
        SELECT package_id FROM feedback WHERE user_id = %s
    )
    """
    bookings_for_feedback = db.execute_query(bookings_query, (user_id, user_id), fetch=True) or []
    
    # Get user's previous feedback
    feedback_query = """
    SELECT f.*, p.name as package_name, p.destination
    FROM feedback f 
    JOIN packages p ON f.package_id = p.id 
    WHERE f.user_id = %s
    ORDER BY f.created_at DESC
    """
    user_feedback = db.execute_query(feedback_query, (user_id,), fetch=True) or []
    
    return render_template('feedback.html', 
                         bookings=bookings_for_feedback, 
                         feedback=user_feedback)

# ✅ ADD THIS ROUTE RIGHT HERE - AFTER /feedback BUT BEFORE /recommendations
@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        user_id = session['user_id']
        package_id = request.form.get('package_id')
        rating = request.form.get('rating')
        comment = request.form.get('comment', '').strip()
        
        print(f"DEBUG - Form data received:")
        print(f"  User ID: {user_id}")
        print(f"  Package ID: {package_id}")
        print(f"  Rating: {rating}")
        print(f"  Comment: {comment}")
        
        # Validate required fields
        if not package_id:
            flash('Package ID is missing.', 'error')
            return redirect(url_for('feedback'))
        
        if not rating:
            flash('Please select a rating before submitting.', 'error')
            return redirect(url_for('feedback'))
        
        # Convert rating to integer with validation
        try:
            rating_int = int(rating)
        except (ValueError, TypeError):
            flash('Invalid rating value. Please select a valid rating.', 'error')
            return redirect(url_for('feedback'))
        
        # Validate rating range
        if rating_int < 1 or rating_int > 5:
            flash('Rating must be between 1 and 5 stars.', 'error')
            return redirect(url_for('feedback'))
        
        # Validate that user has booked this package
        booking_check = """
        SELECT id FROM bookings 
        WHERE user_id = %s AND package_id = %s AND status = 'confirmed'
        """
        valid_booking = db.execute_query(booking_check, (user_id, package_id), fetch=True)
        
        if not valid_booking:
            flash('You can only provide feedback for packages you have booked and confirmed.', 'error')
            return redirect(url_for('feedback'))
        
        # Get booking_id for the feedback
        booking_id_query = """
        SELECT id FROM bookings 
        WHERE user_id = %s AND package_id = %s AND status = 'confirmed'
        LIMIT 1
        """
        booking_result = db.execute_query(booking_id_query, (user_id, package_id), fetch=True)
        
        if not booking_result:
            flash('No valid booking found for this package.', 'error')
            return redirect(url_for('feedback'))
        
        booking_id = booking_result[0]['id']
        
        # Check if feedback already exists for this booking
        check_query = "SELECT id FROM feedback WHERE user_id = %s AND booking_id = %s"
        existing_feedback = db.execute_query(check_query, (user_id, booking_id), fetch=True)
        
        if existing_feedback:
            # Update existing feedback
            update_query = """
            UPDATE feedback 
            SET rating = %s, comment = %s, updated_at = NOW() 
            WHERE id = %s
            """
            result = db.execute_query(update_query, (rating_int, comment, existing_feedback[0]['id']))
            
            if result:
                # Update booking to mark feedback as submitted
                update_booking_query = "UPDATE bookings SET feedback_submitted = TRUE, feedback_id = %s WHERE id = %s"
                db.execute_query(update_booking_query, (existing_feedback[0]['id'], booking_id))
                
                flash('Feedback updated successfully!', 'success')
            else:
                flash('Failed to update feedback. Please try again.', 'error')
        else:
            # Insert new feedback
            insert_query = """
            INSERT INTO feedback (user_id, package_id, booking_id, rating, comment) 
            VALUES (%s, %s, %s, %s, %s)
            """
            result = db.execute_query(insert_query, (user_id, package_id, booking_id, rating_int, comment))
            
            if result:
                # Get the new feedback ID
                feedback_id_query = "SELECT LAST_INSERT_ID() as feedback_id"
                feedback_id_result = db.execute_query(feedback_id_query, fetch=True)
                feedback_id = feedback_id_result[0]['feedback_id'] if feedback_id_result else None
                
                # Update booking to mark feedback as submitted
                if feedback_id:
                    update_booking_query = "UPDATE bookings SET feedback_submitted = TRUE, feedback_id = %s WHERE id = %s"
                    db.execute_query(update_booking_query, (feedback_id, booking_id))
                
                flash('Thank you for your feedback!', 'success')
            else:
                flash('Failed to submit feedback. Please try again.', 'error')
        
        return redirect(url_for('feedback', success='true'))
        
    except Exception as e:
        print(f"Error in submit_feedback: {str(e)}")
        flash('An error occurred while submitting feedback. Please try again.', 'error')
        return redirect(url_for('feedback'))

@app.route('/recommendations')
def recommendations():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    # Get user preferences
    pref_query = "SELECT * FROM user_preferences WHERE user_id = %s"
    preferences = db.execute_query(pref_query, (user_id,), fetch=True)
    
    # Get booking history for personalized recommendations
    booking_history_query = """
    SELECT p.category, p.destination, COUNT(*) as visit_count
    FROM bookings b 
    JOIN packages p ON b.package_id = p.id 
    WHERE b.user_id = %s AND b.status = 'confirmed'
    GROUP BY p.category, p.destination
    ORDER BY visit_count DESC
    """
    booking_history = db.execute_query(booking_history_query, (user_id,), fetch=True) or []
    
    # Generate recommendations based on preferences and history
    recommended_packages = []
    
    if preferences:
        pref = preferences[0]
        query = "SELECT * FROM packages WHERE is_active = TRUE"
        params = []
        
        conditions = []
        
        if pref.get('preferred_destinations'):
            destinations = [d.strip() for d in pref['preferred_destinations'].split(',')]
            placeholders = ','.join(['%s'] * len(destinations))
            conditions.append(f"destination IN ({placeholders})")
            params.extend(destinations)
        
        if pref.get('budget_range'):
            if pref['budget_range'] == 'low':
                conditions.append("price < 10000")
            elif pref['budget_range'] == 'medium':
                conditions.append("price BETWEEN 10000 AND 25000")
            elif pref['budget_range'] == 'high':
                conditions.append("price > 25000")
        
        if pref.get('travel_style'):
            conditions.append("category = %s")
            params.append(pref['travel_style'])
        
        if conditions:
            query += " AND " + " AND ".join(conditions)
        
        query += " ORDER BY RAND() LIMIT 6"
        recommended_packages = db.execute_query(query, params, fetch=True) or []
    
    # If no preferences or not enough recommendations, add popular packages
    if len(recommended_packages) < 3:
        popular_query = """
        SELECT p.*, COUNT(b.id) as booking_count
        FROM packages p 
        LEFT JOIN bookings b ON p.id = b.package_id 
        WHERE p.is_active = TRUE
        GROUP BY p.id 
        ORDER BY booking_count DESC 
        LIMIT %s
        """
        additional_count = 6 - len(recommended_packages)
        popular_packages = db.execute_query(popular_query, (additional_count,), fetch=True) or []
        recommended_packages.extend(popular_packages)
    
    return render_template('recommendations.html', 
                         packages=recommended_packages[:6], 
                         preferences=preferences[0] if preferences else None,
                         booking_history=booking_history)

@app.route('/update_preferences', methods=['POST'])
def update_preferences():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    destinations = request.form.get('preferred_destinations', '')
    budget_range = request.form.get('budget_range', '')
    travel_style = request.form.get('travel_style', '')
    interests = request.form.get('interests', '')
    
    # Check if preferences exist
    check_query = "SELECT id FROM user_preferences WHERE user_id = %s"
    existing = db.execute_query(check_query, (user_id,), fetch=True)
    
    if existing:
        # Update existing preferences
        query = """
        UPDATE user_preferences 
        SET preferred_destinations = %s, budget_range = %s, travel_style = %s, interests = %s 
        WHERE user_id = %s
        """
        result = db.execute_query(query, (destinations, budget_range, travel_style, interests, user_id))
        flash('Preferences updated successfully!', 'success')
    else:
        # Insert new preferences
        query = """
        INSERT INTO user_preferences (user_id, preferred_destinations, budget_range, travel_style, interests)
        VALUES (%s, %s, %s, %s, %s)
        """
        result = db.execute_query(query, (user_id, destinations, budget_range, travel_style, interests))
        flash('Preferences saved successfully!', 'success')
    
    return redirect(url_for('recommendations'))

# Admin routes
@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    try:
        # Basic statistics
        total_users_query = "SELECT COUNT(*) as count FROM users WHERE user_type = 'user'"
        total_users_result = db.execute_query(total_users_query, fetch=True)
        total_users = total_users_result[0]['count'] if total_users_result else 0
        
        total_packages_query = "SELECT COUNT(*) as count FROM packages WHERE is_active = TRUE"
        total_packages_result = db.execute_query(total_packages_query, fetch=True)
        total_packages = total_packages_result[0]['count'] if total_packages_result else 0
        
        total_bookings_query = "SELECT COUNT(*) as count FROM bookings"
        total_bookings_result = db.execute_query(total_bookings_query, fetch=True)
        total_bookings = total_bookings_result[0]['count'] if total_bookings_result else 0
        
        total_revenue_query = "SELECT SUM(total_amount) as revenue FROM bookings WHERE status = 'confirmed'"
        total_revenue_result = db.execute_query(total_revenue_query, fetch=True)
        total_revenue = total_revenue_result[0]['revenue'] if total_revenue_result and total_revenue_result[0]['revenue'] else 0
        
        # Enhanced revenue analytics
        detailed_revenue_query = """
        SELECT 
            DATE_FORMAT(booking_date, '%Y-%m') as month,
            SUM(total_amount) as revenue,
            COUNT(*) as booking_count,
            AVG(total_amount) as avg_booking_value,
            COUNT(DISTINCT user_id) as unique_customers
        FROM bookings 
        WHERE status = 'confirmed'
        GROUP BY DATE_FORMAT(booking_date, '%Y-%m')
        ORDER BY month DESC
        LIMIT 12
        """
        detailed_revenue = db.execute_query(detailed_revenue_query, fetch=True) or []
        
        # Package performance with revenue
        package_performance_query = """
        SELECT 
            p.id,
            p.name,
            p.destination,
            p.category,
            COUNT(b.id) as booking_count,
            SUM(b.total_amount) as total_revenue,
            AVG(b.total_amount) as avg_revenue_per_booking,
            p.available_slots,
            (SELECT AVG(rating) FROM feedback WHERE package_id = p.id) as avg_rating
        FROM packages p
        LEFT JOIN bookings b ON p.id = b.package_id AND b.status = 'confirmed'
        WHERE p.is_active = TRUE
        GROUP BY p.id
        ORDER BY total_revenue DESC
        LIMIT 10
        """
        package_performance = db.execute_query(package_performance_query, fetch=True) or []
        
        # Recent bookings for admin
        recent_bookings_query = """
        SELECT b.*, u.username, u.full_name, p.name as package_name, p.destination
        FROM bookings b 
        JOIN users u ON b.user_id = u.id 
        JOIN packages p ON b.package_id = p.id 
        ORDER BY b.booking_date DESC 
        LIMIT 8
        """
        recent_bookings = db.execute_query(recent_bookings_query, fetch=True) or []
        
        # Booking status distribution
        booking_stats_query = """
        SELECT status, COUNT(*) as count
        FROM bookings
        GROUP BY status
        """
        booking_stats = db.execute_query(booking_stats_query, fetch=True) or []
        
        # User registration trends
        user_registration_query = """
        SELECT DATE_FORMAT(created_at, '%Y-%m') as month, 
               COUNT(*) as registrations
        FROM users 
        WHERE user_type = 'user'
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month DESC
        LIMIT 6
        """
        user_registrations = db.execute_query(user_registration_query, fetch=True) or []
        
        # Package categories distribution
        category_stats_query = """
        SELECT category, COUNT(*) as count, 
               SUM(available_slots) as total_slots
        FROM packages 
        WHERE is_active = TRUE
        GROUP BY category
        """
        category_stats = db.execute_query(category_stats_query, fetch=True) or []
        
        # Low stock packages (less than 5 slots)
        low_stock_query = """
        SELECT name, destination, available_slots
        FROM packages 
        WHERE is_active = TRUE AND available_slots < 5
        ORDER BY available_slots ASC
        LIMIT 5
        """
        low_stock_packages = db.execute_query(low_stock_query, fetch=True) or []
        
        # Recent feedback for monitoring
        recent_feedback_query = """
        SELECT f.*, u.username, p.name as package_name,
               (SELECT AVG(rating) FROM feedback WHERE package_id = p.id) as avg_rating
        FROM feedback f
        JOIN users u ON f.user_id = u.id
        JOIN packages p ON f.package_id = p.id
        ORDER BY f.created_at DESC
        LIMIT 6
        """
        recent_feedback = db.execute_query(recent_feedback_query, fetch=True) or []
        
        # Customer growth analytics
        customer_growth_query = """
        SELECT 
            DATE_FORMAT(created_at, '%Y-%m') as month,
            COUNT(*) as new_users,
            SUM(COUNT(*)) OVER (ORDER BY DATE_FORMAT(created_at, '%Y-%m')) as cumulative_users
        FROM users 
        WHERE user_type = 'user'
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month DESC
        LIMIT 6
        """
        customer_growth = db.execute_query(customer_growth_query, fetch=True) or []
        
        # Real-time alerts
        alerts = []
        
        # Low stock alerts
        for package in low_stock_packages:
            alerts.append({
                'type': 'warning',
                'message': f'Low stock: {package["name"]} - only {package["available_slots"]} slots left',
                'icon': 'exclamation-triangle'
            })
        
        # Pending bookings alert
        pending_count = db.execute_query("SELECT COUNT(*) as count FROM bookings WHERE status = 'pending'", fetch=True)
        if pending_count and pending_count[0]['count'] > 0:
            alerts.append({
                'type': 'info', 
                'message': f'{pending_count[0]["count"]} pending bookings need review',
                'icon': 'clock'
            })
        
        # No recent bookings alert
        recent_bookings_count = db.execute_query("""
            SELECT COUNT(*) as count FROM bookings 
            WHERE booking_date >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """, fetch=True)
        if recent_bookings_count and recent_bookings_count[0]['count'] == 0:
            alerts.append({
                'type': 'danger',
                'message': 'No bookings in the last 24 hours',
                'icon': 'chart-line'
            })
        
        return render_template('admin_dashboard.html',
                             total_users=total_users,
                             total_packages=total_packages,
                             total_bookings=total_bookings,
                             total_revenue=total_revenue,
                             monthly_revenue=detailed_revenue,
                             detailed_revenue=detailed_revenue,
                             popular_packages=package_performance,
                             package_performance=package_performance,
                             recent_bookings=recent_bookings,
                             booking_stats=booking_stats,
                             user_registrations=user_registrations,
                             category_stats=category_stats,
                             low_stock_packages=low_stock_packages,
                             recent_feedback=recent_feedback,
                             alerts=alerts,
                             customer_growth=customer_growth)
    
    except Exception as e:
        print(f"Error in admin dashboard: {e}")
        return render_template('admin_dashboard.html',
                             total_users=0,
                             total_packages=0,
                             total_bookings=0,
                             total_revenue=0,
                             monthly_revenue=[],
                             detailed_revenue=[],
                             popular_packages=[],
                             package_performance=[],
                             recent_bookings=[],
                             booking_stats=[],
                             user_registrations=[],
                             category_stats=[],
                             low_stock_packages=[],
                             recent_feedback=[],
                             alerts=[],
                             customer_growth=[])

@app.route('/admin/users')
def admin_users():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    users_query = "SELECT id, username, email, full_name, phone, user_type, created_at FROM users ORDER BY created_at DESC"
    users_data = db.execute_query(users_query, fetch=True) or []
    
    return render_template('admin_users.html', users=users_data)

@app.route('/admin/packages')
def admin_packages():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    try:
        packages_query = """
        SELECT p.*, u.username as created_by_name 
        FROM packages p 
        LEFT JOIN users u ON p.created_by = u.id 
        ORDER BY p.created_at DESC
        """
        packages_data = db.execute_query(packages_query, fetch=True)
        
        # Handle case where database returns None
        if packages_data is None:
            packages_data = []
            flash('Database connection issue. Please check your database.', 'error')
        
        print(f"Found {len(packages_data)} packages")  # Debug line
        
        # Calculate statistics for the dashboard cards
        active_packages_count = 0
        low_stock_count = 0
        sold_out_count = 0
        
        for package in packages_data:
            if package.get('is_active'):
                active_packages_count += 1
            
            available_slots = package.get('available_slots', 0)
            if available_slots < 5 and available_slots > 0:
                low_stock_count += 1
            elif available_slots == 0:
                sold_out_count += 1
        
        return render_template('admin_packages.html', 
                             packages=packages_data,
                             active_packages_count=active_packages_count,
                             low_stock_count=low_stock_count,
                             sold_out_count=sold_out_count)
    
    except Exception as e:
        print(f"Error in admin_packages: {e}")
        flash('Error loading packages from database.', 'error')
        return render_template('admin_packages.html', 
                             packages=[],
                             active_packages_count=0,
                             low_stock_count=0,
                             sold_out_count=0)
    
@app.route('/admin/add_package', methods=['GET', 'POST'])
def add_package():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            name = request.form['name']
            description = request.form['description']
            destination = request.form['destination']
            duration_days = int(request.form['duration_days'])
            price = float(request.form['price'])
            category = request.form['category']
            image_url = request.form.get('image_url', '') or 'https://via.placeholder.com/600x400/007bff/ffffff?text=Tour+Package'
            available_slots = int(request.form['available_slots'])
            
            print(f"Attempting to add package: {name}, {destination}")

            # Use the correct column names from your schema
            query = """
            INSERT INTO packages (name, description, destination, duration_days, price, category, image_url, available_slots, created_by, is_active, max_slots)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
            """
            result = db.execute_query(query, (name, description, destination, duration_days, price, category, image_url, available_slots, session['user_id'], available_slots))
            
            if result:
                print(f"Package added successfully: {name}")
                flash('Package added successfully!', 'success')
                return redirect(url_for('admin_packages'))
            else:
                print("Package insertion failed")
                flash('Failed to add package to database. Please try again.', 'error')
                
        except Exception as e:
            print(f"Error in add_package: {e}")
            flash(f'Error adding package: {str(e)}', 'error')
    
    return render_template('admin_add_package.html')

@app.route('/admin/create_test_package')
def create_test_package():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    try:
        query = """
        INSERT INTO packages (name, description, destination, duration_days, price, category, image_url, available_slots, created_by, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        result = db.execute_query(query, (
            "Paradise Beach, Goa", 
            "Enjoy the beautiful beaches of Goa with luxury accommodation and water sports", 
            "Goa", 
            5, 
            6000.00, 
            "Beach", 
            "https://via.placeholder.com/600x400/28a745/ffffff?text=Goa+Beach", 
            20, 
            session['user_id'], 
            True
        ))
        
        if result:
            flash('Test package created successfully!', 'success')
        else:
            flash('Failed to create test package.', 'error')
            
    except Exception as e:
        flash(f'Error creating test package: {e}', 'error')
    
    return redirect(url_for('admin_packages'))


@app.route('/admin/edit_package/<int:package_id>', methods=['GET', 'POST'])
def edit_package(package_id):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            name = request.form['name']
            description = request.form['description']
            destination = request.form['destination']
            duration_days = int(request.form['duration_days'])
            price = float(request.form['price'])
            category = request.form['category']
            image_url = request.form.get('image_url', '') or 'https://via.placeholder.com/600x400/007bff/ffffff?text=Tour+Package'
            available_slots = int(request.form['available_slots'])
            is_active = 'is_active' in request.form
            
            query = """
            UPDATE packages 
            SET name = %s, description = %s, destination = %s, duration_days = %s, 
                price = %s, category = %s, image_url = %s, available_slots = %s, is_active = %s
            WHERE id = %s
            """
            result = db.execute_query(query, (name, description, destination, duration_days, price, category, image_url, available_slots, is_active, package_id))
            
            if result:
                flash('Package updated successfully!', 'success')
                return redirect(url_for('admin_packages'))
            else:
                flash('Failed to update package. Please try again.', 'error')
        except Exception as e:
            print(f"Error updating package: {e}")
            flash('Error updating package. Please check the form data.', 'error')
    
    # Get package details
    try:
        package_query = "SELECT * FROM packages WHERE id = %s"
        package_result = db.execute_query(package_query, (package_id,), fetch=True)
        
        print(f"Package query result: {package_result}")
        
        if not package_result:
            flash('Package not found in database.', 'error')
            return redirect(url_for('admin_packages'))
        
        package = package_result[0]
        print(f"Package data: {package}")
        
    except Exception as e:
        print(f"Error fetching package: {e}")
        flash('Error loading package details from database.', 'error')
        return redirect(url_for('admin_packages'))
    
    return render_template('admin_edit_package.html', package=package)

@app.route('/admin/toggle_package/<int:package_id>')
def toggle_package(package_id):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    try:
        # Get current status
        package_query = "SELECT * FROM packages WHERE id = %s"
        package_result = db.execute_query(package_query, (package_id,), fetch=True)
        
        print(f"Toggle package query result: {package_result}")  # Debug line
        
        if not package_result:
            flash('Package not found in database.', 'error')
            return redirect(url_for('admin_packages'))
        
        package = package_result[0]
        current_status = package.get('is_active', False)
        new_status = not current_status
        
        query = "UPDATE packages SET is_active = %s WHERE id = %s"
        result = db.execute_query(query, (new_status, package_id))
        
        if result:
            status_text = "activated" if new_status else "deactivated"
            flash(f'Package {status_text} successfully!', 'success')
        else:
            flash('Failed to update package status in database.', 'error')
    
    except Exception as e:
        print(f"Error toggling package {package_id}: {e}")
        flash('Error updating package status.', 'error')
    
    return redirect(url_for('admin_packages'))

@app.route('/admin/bookings')
def admin_bookings():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    status_filter = request.args.get('status', '')
    
    query = """
    SELECT b.*, u.username, u.full_name, p.name as package_name, p.destination
    FROM bookings b 
    JOIN users u ON b.user_id = u.id 
    JOIN packages p ON b.package_id = p.id 
    """
    
    if status_filter:
        query += " WHERE b.status = %s"
        bookings_data = db.execute_query(query, (status_filter,), fetch=True) or []
    else:
        query += " ORDER BY b.booking_date DESC"
        bookings_data = db.execute_query(query, fetch=True) or []
    
    return render_template('admin_bookings.html', bookings=bookings_data)

@app.route('/admin/confirm_booking/<int:booking_id>')
def admin_confirm_booking(booking_id):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    query = "UPDATE bookings SET status = 'confirmed' WHERE id = %s"
    result = db.execute_query(query, (booking_id,))
    
    if result:
        flash('Booking confirmed successfully!', 'success')
    else:
        flash('Failed to confirm booking.', 'error')
    
    return redirect(url_for('admin_bookings'))

@app.route('/admin/cancel_booking/<int:booking_id>')
def admin_cancel_booking(booking_id):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    # Get booking details to restore slots
    booking_query = "SELECT * FROM bookings WHERE id = %s"
    booking = db.execute_query(booking_query, (booking_id,), fetch=True)
    
    if booking:
        # Restore available slots
        restore_slots_query = "UPDATE packages SET available_slots = available_slots + %s WHERE id = %s"
        db.execute_query(restore_slots_query, (booking[0]['travelers_count'], booking[0]['package_id']))
    
    query = "UPDATE bookings SET status = 'cancelled' WHERE id = %s"
    result = db.execute_query(query, (booking_id,))
    
    if result:
        flash('Booking cancelled successfully!', 'success')
    else:
        flash('Failed to cancel booking.', 'error')
    
    return redirect(url_for('admin_bookings'))

@app.route('/admin/update_booking_status/<int:booking_id>/<status>')
def admin_update_booking_status(booking_id, status):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    if status not in ['pending', 'confirmed', 'cancelled']:
        flash('Invalid status.', 'error')
        return redirect(url_for('admin_bookings'))
    
    # If cancelling, restore slots
    if status == 'cancelled':
        booking_query = "SELECT * FROM bookings WHERE id = %s"
        booking = db.execute_query(booking_query, (booking_id,), fetch=True)
        if booking:
            restore_slots_query = "UPDATE packages SET available_slots = available_slots + %s WHERE id = %s"
            db.execute_query(restore_slots_query, (booking[0]['travelers_count'], booking[0]['package_id']))
    
    query = "UPDATE bookings SET status = %s WHERE id = %s"
    result = db.execute_query(query, (status, booking_id))
    
    if result:
        flash(f'Booking status updated to {status}.', 'success')
    else:
        flash('Failed to update booking status.', 'error')
    
    return redirect(url_for('admin_bookings'))

# Admin user management routes
@app.route('/admin/make_admin/<int:user_id>')
def make_admin(user_id):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    if user_id == session['user_id']:
        flash('You cannot change your own role.', 'error')
        return redirect(url_for('admin_users'))
    
    query = "UPDATE users SET user_type = 'admin' WHERE id = %s"
    result = db.execute_query(query, (user_id,))
    
    if result:
        flash('User promoted to administrator successfully!', 'success')
    else:
        flash('Failed to promote user.', 'error')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/revoke_admin/<int:user_id>')
def revoke_admin(user_id):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    if user_id == session['user_id']:
        flash('You cannot change your own role.', 'error')
        return redirect(url_for('admin_users'))
    
    query = "UPDATE users SET user_type = 'user' WHERE id = %s"
    result = db.execute_query(query, (user_id,))
    
    if result:
        flash('Administrator privileges revoked successfully!', 'success')
    else:
        flash('Failed to revoke admin privileges.', 'error')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_user/<int:user_id>')
def delete_user(user_id):
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    if user_id == session['user_id']:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin_users'))
    
    # First delete related records to maintain database integrity
    try:
        # Delete user's feedback
        db.execute_query("DELETE FROM feedback WHERE user_id = %s", (user_id,))
        # Delete user's preferences
        db.execute_query("DELETE FROM user_preferences WHERE user_id = %s", (user_id,))
        # Delete user's bookings
        db.execute_query("DELETE FROM bookings WHERE user_id = %s", (user_id,))
        # Finally delete the user
        result = db.execute_query("DELETE FROM users WHERE id = %s", (user_id,))
        
        if result:
            flash('User deleted successfully!', 'success')
        else:
            flash('Failed to delete user.', 'error')
            
    except Exception as e:
        flash(f'Error deleting user: {str(e)}', 'error')
    
    return redirect(url_for('admin_users'))

# API routes
@app.route('/admin/api/alerts')
def admin_api_alerts():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    alerts = []
    
    # Low stock alerts
    low_stock = db.execute_query("""
        SELECT name, available_slots 
        FROM packages 
        WHERE is_active = TRUE AND available_slots < 3
    """, fetch=True) or []
    
    for package in low_stock:
        alerts.append({
            'type': 'warning',
            'message': f'Low stock: {package["name"]} - only {package["available_slots"]} slots left',
            'icon': 'exclamation-triangle'
        })
    
    # Pending bookings
    pending = db.execute_query("SELECT COUNT(*) as count FROM bookings WHERE status = 'pending'", fetch=True)
    if pending and pending[0]['count'] > 0:
        alerts.append({
            'type': 'info',
            'message': f'{pending[0]["count"]} pending bookings need review',
            'icon': 'clock'
        })
    
    # No recent bookings (last 6 hours)
    recent_bookings = db.execute_query("""
        SELECT COUNT(*) as count FROM bookings 
        WHERE booking_date >= DATE_SUB(NOW(), INTERVAL 6 HOUR)
    """, fetch=True)
    if recent_bookings and recent_bookings[0]['count'] == 0:
        alerts.append({
            'type': 'danger',
            'message': 'No bookings in the last 6 hours',
            'icon': 'chart-line'
        })
    
    return jsonify({'alerts': alerts})

@app.route('/admin/api/stats')
def admin_api_stats():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    total_revenue_query = "SELECT SUM(total_amount) as revenue FROM bookings WHERE status = 'confirmed'"
    total_revenue_result = db.execute_query(total_revenue_query, fetch=True)
    total_revenue = total_revenue_result[0]['revenue'] if total_revenue_result and total_revenue_result[0]['revenue'] else 0
    
    total_bookings_query = "SELECT COUNT(*) as count FROM bookings"
    total_bookings_result = db.execute_query(total_bookings_query, fetch=True)
    total_bookings = total_bookings_result[0]['count'] if total_bookings_result else 0
    
    total_users_query = "SELECT COUNT(*) as count FROM users WHERE user_type = 'user'"
    total_users_result = db.execute_query(total_users_query, fetch=True)
    total_users = total_users_result[0]['count'] if total_users_result else 0
    
    total_packages_query = "SELECT COUNT(*) as count FROM packages WHERE is_active = TRUE"
    total_packages_result = db.execute_query(total_packages_query, fetch=True)
    total_packages = total_packages_result[0]['count'] if total_packages_result else 0
    
    return jsonify({
        'total_revenue': total_revenue,
        'total_bookings': total_bookings,
        'total_users': total_users,
        'total_packages': total_packages
    })


@app.route('/debug/packages')
def debug_packages():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    # Get all packages for debugging
    packages_query = "SELECT * FROM packages"
    packages = db.execute_query(packages_query, fetch=True) or []
    
    debug_info = {
        'total_packages': len(packages),
        'packages': packages
    }
    
    return jsonify(debug_info)

@app.route('/debug/routes')
def debug_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    return jsonify(routes)

# Context processor
@app.context_processor
def inject_today():
    return {'today': datetime.now().strftime('%Y-%m-%d')}

if __name__ == '__main__':
    app.run(debug=True)