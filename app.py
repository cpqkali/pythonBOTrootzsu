import os
import subprocess
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

# --- App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rootzsu_bot.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='eventlet')
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Global State ---
bot_process = None

# --- Database Models ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True)
    first_name = db.Column(db.String)
    password_hash = db.Column(db.String)

    def get_id(self):
        return str(self.user_id)

class Service(db.Model):
    __tablename__ = 'services'
    service_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    price_usd = db.Column(db.Float)
    price_btc = db.Column(db.Float)
    price_stars = db.Column(db.Integer)

class Order(db.Model):
    __tablename__ = 'orders'
    order_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    service_id = db.Column(db.Integer, db.ForeignKey('services.service_id'))
    payment_method = db.Column(db.String)
    status = db.Column(db.String, default='pending_payment')
    
    user = db.relationship('User', backref='orders')
    service = db.relationship('Service', backref='orders')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Bot Management ---
def is_bot_running():
    global bot_process
    return bot_process is not None and bot_process.poll() is None

def start_bot():
    global bot_process
    if not is_bot_running():
        bot_process = subprocess.Popen(['python', 'bot.py'])
        print("Bot started!")
        return True
    return False

def stop_bot():
    global bot_process
    if is_bot_running():
        bot_process.terminate()
        bot_process = None
        print("Bot stopped!")
        return True
    return False

# --- General Routes ---
@app.route('/')
def index():
    return render_template('index.html')

# --- User Authentication Routes ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if not user:
            flash('This username is not found in the bot database. Please start the bot first.', 'danger')
            return redirect(url_for('register'))
        
        if user.password_hash:
            flash('This user is already registered. Please log in.', 'warning')
            return redirect(url_for('login'))
            
        user.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        db.session.commit()
        
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))
        
        login_user(user)
        return redirect(url_for('dashboard'))
        
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_orders = Order.query.filter_by(user_id=current_user.user_id).order_by(Order.order_id.desc()).all()
    # Placeholder for profile photo logic
    profile_photo = f"https://api.dicebear.com/8.x/initials/svg?seed={current_user.first_name}"
    return render_template('dashboard.html', orders=user_orders, photo=profile_photo)

# --- Admin Routes ---
class AdminUser(UserMixin):
    def __init__(self):
        self.id = 'admin'

admin_user = AdminUser()

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')
        if login == os.getenv('ADMIN_LOGIN') and password == os.getenv('ADMIN_PASSWORD'):
            login_user(admin_user)
            return redirect(url_for('admin_panel'))
        else:
            flash('Invalid admin credentials.', 'danger')
    return render_template('admin_login.html')

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.id != 'admin':
        return redirect(url_for('index'))
    
    all_users = User.query.all()
    all_services = Service.query.all()
    all_orders = Order.query.all()

    return render_template(
        'admin_panel.html', 
        users=all_users, 
        services=all_services,
        orders=all_orders,
        bot_status=is_bot_running()
    )

# --- API Routes for Admin Panel ---
@app.route('/admin/api/service/update', methods=['POST'])
@login_required
def update_service():
    if current_user.id != 'admin': return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    data = request.json
    service = Service.query.get(data['id'])
    if service:
        service.name = data['name']
        service.description = data['description']
        service.price_usd = data['price_usd']
        service.price_btc = data['price_btc']
        service.price_stars = data['price_stars']
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Service not found'}), 404

# --- SocketIO Events for Real-Time ---
@socketio.on('connect')
def handle_connect():
    emit('bot_status_update', {'running': is_bot_running()})

@socketio.on('toggle_bot')
def handle_toggle_bot():
    if current_user.is_authenticated and current_user.id == 'admin':
        if is_bot_running():
            stop_bot()
        else:
            start_bot()
        socketio.emit('bot_status_update', {'running': is_bot_running()})

# --- Main Entry ---
if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)

