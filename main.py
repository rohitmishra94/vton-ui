from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import uuid
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

API_URL = 'https://uskb92zf7oamx1-8000.proxy.runpod.net/try_on/'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists')
            return redirect(url_for('register'))
        new_user = User(username=username, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('upload'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'person_image' not in request.files or 'cloth_image' not in request.files:
            return jsonify({'error': 'Missing required files'}), 400
        
        person_image = request.files['person_image']
        cloth_image = request.files['cloth_image']
        cloth_type = request.form.get('cloth_type', 'upper')
        
        if person_image.filename == '' or cloth_image.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        
        if person_image and cloth_image:
            person_filename = secure_filename(person_image.filename)
            cloth_filename = secure_filename(cloth_image.filename)
            
            person_unique_filename = f"{uuid.uuid4()}_{person_filename}"
            cloth_unique_filename = f"{uuid.uuid4()}_{cloth_filename}"
            
            person_file_path = os.path.join(app.config['UPLOAD_FOLDER'], person_unique_filename)
            cloth_file_path = os.path.join(app.config['UPLOAD_FOLDER'], cloth_unique_filename)
            
            person_image.save(person_file_path)
            cloth_image.save(cloth_file_path)
            
            try:
                processed_image = process_image(person_file_path, cloth_file_path, cloth_type)
                return render_template('result.html', 
                                       original_image=person_unique_filename,
                                       cloth_image=cloth_unique_filename,
                                       processed_image=processed_image)
            except Exception as e:
                return jsonify({'error': f"Error processing image: {str(e)}"}), 500
    
    return render_template('upload.html')

def process_image(person_file_path, cloth_file_path, cloth_type):
    with open(person_file_path, 'rb') as person_file, open(cloth_file_path, 'rb') as cloth_file:
        files = {
            'person_image': (os.path.basename(person_file_path), person_file, 'image/jpeg'),
            'cloth_image': (os.path.basename(cloth_file_path), cloth_file, 'image/jpeg')
        }
        data = {'cloth_type': cloth_type}
        
        response = requests.post(API_URL, files=files, data=data)
        
        if response.status_code == 200:
            processed_filename = f"processed_{os.path.basename(person_file_path)}"
            processed_path = os.path.join(app.config['UPLOAD_FOLDER'], processed_filename)
            
            with open(processed_path, 'wb') as f:
                f.write(response.content)
            
            return processed_filename
        else:
            raise Exception(f"API request failed with status code: {response.status_code}")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)