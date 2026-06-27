from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from backend.models import user_model

auth_bp = Blueprint('auth', __name__, url_prefix='/auth', template_folder='../frontend/templates')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        is_json = request.is_json
        if is_json:
            data = request.get_json()
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            confirm = data.get('confirm_password', data.get('password', ''))
        else:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            confirm = request.form.get('confirm_password', '')

        if not username or not email or not password:
            if is_json:
                return jsonify({'status': 'error', 'message': 'All fields are required.'}), 400
            flash('All fields are required.', 'error')
            return redirect(url_for('auth.register'))

        if password != confirm:
            if is_json:
                return jsonify({'status': 'error', 'message': 'Passwords do not match.'}), 400
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.register'))

        try:
            user, err = user_model.create_user(username, email, password)
        except Exception as e:
            print(f'Registration failed: {e}')
            if is_json:
                return jsonify({'status': 'error', 'message': 'Server error during registration.'}), 500
            flash('Server error during registration. Please try again.', 'error')
            return redirect(url_for('auth.register'))

        if err:
            if is_json:
                return jsonify({'status': 'error', 'message': err}), 400
            flash(err, 'error')
            return redirect(url_for('auth.register'))

        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_first_login'] = user['is_first_login']

        if is_json:
            return jsonify({'status': 'success', 'redirect': url_for('upload_file')})
        flash('Account created successfully!', 'success')
        return redirect(url_for('upload_file'))

    return render_template('auth.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        is_json = request.is_json
        if is_json:
            data = request.get_json()
            login_id = data.get('login', '').strip()
            password = data.get('password', '')
        else:
            login_id = request.form.get('login', '').strip()
            password = request.form.get('password', '')

        if not login_id or not password:
            if is_json:
                return jsonify({'status': 'error', 'message': 'Please enter credentials.'}), 400
            flash('Please enter credentials.', 'error')
            return redirect(url_for('auth.login'))

        try:
            user, err = user_model.authenticate(login_id, password)
        except Exception as e:
            print(f'Login failed: {e}')
            if is_json:
                return jsonify({'status': 'error', 'message': 'Server error during login.'}), 500
            flash('Server error during login. Please try again.', 'error')
            return redirect(url_for('auth.login'))

        if err:
            if is_json:
                return jsonify({'status': 'error', 'message': err}), 401
            flash(err, 'error')
            return redirect(url_for('auth.login'))

        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_first_login'] = user['is_first_login']

        if is_json:
            return jsonify({'status': 'success', 'redirect': url_for('upload_file')})

        if user.get('is_first_login'):
            flash('Welcome! Start by uploading your dataset.', 'success')
            return redirect(url_for('upload_file'))
        else:
            flash(f'Welcome Back, {user["username"]}!', 'success')
            return redirect(url_for('upload_file'))

    return render_template('auth.html')


@auth_bp.route('/onboarding')
def onboarding():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return render_template('onboarding.html', username=session.get('username', 'User'))


@auth_bp.route('/complete-onboarding', methods=['POST'])
def complete_onboarding():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    try:
        user_id = session['user_id']
        user_model.set_first_login_done(user_id)
        session['is_first_login'] = False
    except Exception as e:
        print(f'Onboarding error: {e}')
        return jsonify({'ok': False, 'error': 'Server error during onboarding.'}), 500

    flash('Welcome aboard! Start analyzing your data.', 'success')
    return jsonify({'ok': True, 'redirect': url_for('upload_file')})


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))