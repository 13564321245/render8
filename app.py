import os
import sys
import json
import base64
from datetime import datetime
import hashlib
import uuid

# DON'T CHANGE THIS PATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_from_directory, send_file, redirect
from flask_cors import CORS
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

app.config['SECRET_KEY'] = 'your-secret-key-here'

# Debug: Print environment variables (without secrets)
print("=== CLOUDINARY CONFIGURATION DEBUG ===")
cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
api_key = os.getenv('CLOUDINARY_API_KEY')
api_secret = os.getenv('CLOUDINARY_API_SECRET')

print(f"CLOUDINARY_CLOUD_NAME: {'✅ SET' if cloud_name else '❌ MISSING'}")
print(f"CLOUDINARY_API_KEY: {'✅ SET' if api_key else '❌ MISSING'}")
print(f"CLOUDINARY_API_SECRET: {'✅ SET' if api_secret else '❌ MISSING'}")

# Configure Cloudinary
cloudinary_configured = False
if cloud_name and api_key and api_secret:
    try:
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret
        )
        # Test Cloudinary connection
        cloudinary.api.ping()
        cloudinary_configured = True
        print("✅ CLOUDINARY: Successfully configured and connected!")
    except Exception as e:
        print(f"❌ CLOUDINARY: Configuration failed - {e}")
        cloudinary_configured = False
else:
    print("❌ CLOUDINARY: Missing environment variables")
    cloudinary_configured = False

print(f"CLOUDINARY STATUS: {'✅ READY' if cloudinary_configured else '❌ NOT CONFIGURED'}")
print("==========================================")

# JSON file for metadata storage
PHOTOS_JSON_FILE = 'photos_data.json'

def load_photos_data():
    """Load photos metadata from JSON file"""
    try:
        if os.path.exists(PHOTOS_JSON_FILE):
            with open(PHOTOS_JSON_FILE, 'r') as f:
                data = json.load(f)
                print(f"📁 Loaded {len(data)} photos from JSON file")
                return data
        print("📁 No existing photos file found")
        return []
    except Exception as e:
        print(f"❌ Error loading photos data: {e}")
        return []

def save_photos_data(photos_data):
    """Save photos metadata to JSON file"""
    try:
        with open(PHOTOS_JSON_FILE, 'w') as f:
            json.dump(photos_data, f, indent=2)
        print(f"💾 Saved {len(photos_data)} photos to JSON file")
        return True
    except Exception as e:
        print(f"❌ Error saving photos data: {e}")
        return False

def get_next_photo_id():
    """Get the next available photo ID"""
    photos_data = load_photos_data()
    if not photos_data:
        return 1
    return max(photo['id'] for photo in photos_data) + 1

# Debug endpoint
@app.route('/api/debug')
def debug_info():
    """Debug endpoint to check configuration"""
    return jsonify({
        'cloudinary_configured': cloudinary_configured,
        'environment_variables': {
            'CLOUDINARY_CLOUD_NAME': '✅ SET' if os.getenv('CLOUDINARY_CLOUD_NAME') else '❌ MISSING',
            'CLOUDINARY_API_KEY': '✅ SET' if os.getenv('CLOUDINARY_API_KEY') else '❌ MISSING',
            'CLOUDINARY_API_SECRET': '✅ SET' if os.getenv('CLOUDINARY_API_SECRET') else '❌ MISSING'
        },
        'photos_count': len(load_photos_data()),
        'json_file_exists': os.path.exists(PHOTOS_JSON_FILE),
        'storage_type': 'cloudinary' if cloudinary_configured else 'local_fallback'
    })

# Routes
@app.route('/api/photos', methods=['GET'])
def get_photos():
    try:
        photos_data = load_photos_data()
        # Sort by upload_date descending
        photos_data.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
        return jsonify({
            'success': True,
            'photos': photos_data,
            'storage_type': 'cloudinary' if cloudinary_configured else 'local_fallback',
            'total_count': len(photos_data)
        })
    except Exception as e:
        print(f"❌ Error getting photos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/photos', methods=['POST'])
def upload_photo():
    try:
        data = request.get_json()
        
        # Verify admin password
        password = request.headers.get('X-Admin-Password')
        if password != 'Hanshow99@':
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        # Extract image data
        image_data = data.get('image_data')
        if not image_data:
            return jsonify({'success': False, 'error': 'No image data provided'}), 400
        
        # Generate unique filename
        filename = data.get('filename', 'photo.jpg')
        unique_filename = f"{uuid.uuid4()}_{filename}"
        
        print(f"📸 Uploading photo: {filename}")
        print(f"🔧 Cloudinary configured: {cloudinary_configured}")
        
        if cloudinary_configured:
            try:
                print("☁️ Attempting Cloudinary upload...")
                # Upload to Cloudinary
                upload_result = cloudinary.uploader.upload(
                    image_data,
                    public_id=unique_filename.split('.')[0],  # Remove extension for public_id
                    folder="georges_photo_gallery",
                    resource_type="image"
                )
                
                print(f"✅ Cloudinary upload successful: {upload_result['secure_url']}")
                
                # Create photo metadata
                photo_data = {
                    'id': get_next_photo_id(),
                    'filename': filename,
                    'title': data.get('title', 'Untitled'),
                    'description': data.get('description', ''),
                    'cloudinary_url': upload_result['secure_url'],
                    'cloudinary_public_id': upload_result['public_id'],
                    'image_url': upload_result['secure_url'],  # For compatibility
                    'upload_date': datetime.utcnow().isoformat(),
                    'storage_type': 'cloudinary'
                }
                
                # Load existing photos and add new one
                photos_data = load_photos_data()
                photos_data.append(photo_data)
                
                # Save to JSON file
                if save_photos_data(photos_data):
                    print("✅ Photo metadata saved successfully")
                    return jsonify({
                        'success': True,
                        'photo': photo_data,
                        'storage_type': 'cloudinary'
                    })
                else:
                    # If JSON save fails, try to delete from Cloudinary
                    try:
                        cloudinary.uploader.destroy(upload_result['public_id'])
                        print("🗑️ Cleaned up Cloudinary upload due to metadata save failure")
                    except:
                        pass
                    return jsonify({'success': False, 'error': 'Failed to save photo metadata'}), 500
                    
            except Exception as cloudinary_error:
                print(f"❌ Cloudinary upload error: {cloudinary_error}")
                return jsonify({
                    'success': False, 
                    'error': f'Cloudinary upload failed: {str(cloudinary_error)}',
                    'suggestion': 'Please check your Cloudinary environment variables in Render dashboard'
                }), 500
        else:
            # Cloudinary not configured - return clear error
            return jsonify({
                'success': False,
                'error': 'Cloudinary not configured - photos will not persist after restart',
                'suggestion': 'Please set up Cloudinary environment variables: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET',
                'debug_url': '/api/debug'
            }), 500
        
    except Exception as e:
        print(f"❌ Upload error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/photos/<int:photo_id>/image')
def get_photo_image(photo_id):
    """Serve image for base64 fallback storage"""
    try:
        photos_data = load_photos_data()
        photo = next((p for p in photos_data if p['id'] == photo_id), None)
        
        if not photo:
            return jsonify({'error': 'Photo not found'}), 404
        
        # If it's stored in Cloudinary, redirect to Cloudinary URL
        if 'cloudinary_url' in photo:
            return redirect(photo['cloudinary_url'])
        
        # If it's base64 fallback storage
        if 'image_data' in photo:
            image_data = photo['image_data']
            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]
            
            import base64
            from flask import Response
            image_bytes = base64.b64decode(image_data)
            return Response(image_bytes, mimetype='image/jpeg')
        
        return jsonify({'error': 'Image data not found'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/photos/<int:photo_id>', methods=['DELETE'])
def delete_photo(photo_id):
    try:
        # Verify admin password
        password = request.headers.get('X-Admin-Password')
        if password != 'Hanshow99@':
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        photos_data = load_photos_data()
        photo = next((p for p in photos_data if p['id'] == photo_id), None)
        
        if not photo:
            return jsonify({'success': False, 'error': 'Photo not found'}), 404
        
        print(f"🗑️ Deleting photo: {photo.get('title', 'Unknown')}")
        
        # Delete from Cloudinary if it exists there
        if 'cloudinary_public_id' in photo and cloudinary_configured:
            try:
                cloudinary.uploader.destroy(photo['cloudinary_public_id'])
                print("✅ Deleted from Cloudinary")
            except Exception as e:
                print(f"⚠️ Error deleting from Cloudinary: {e}")
        
        # Remove from photos data
        photos_data = [p for p in photos_data if p['id'] != photo_id]
        
        if save_photos_data(photos_data):
            print("✅ Photo deleted successfully")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to update photo data'}), 500
        
    except Exception as e:
        print(f"❌ Delete error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/verify', methods=['POST'])
def verify_admin():
    try:
        data = request.get_json()
        password = data.get('password')
        
        if password == 'Hanshow99@':
            return jsonify({
                'success': True, 
                'message': 'Admin verified',
                'cloudinary_configured': cloudinary_configured,
                'storage_type': 'cloudinary' if cloudinary_configured else 'local_fallback'
            })
        else:
            return jsonify({'success': False, 'error': 'Invalid password'}), 401
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Health check endpoint
@app.route('/api/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'cloudinary_configured': cloudinary_configured,
        'storage': 'cloudinary' if cloudinary_configured else 'local_fallback',
        'photos_count': len(load_photos_data()),
        'environment_check': {
            'CLOUDINARY_CLOUD_NAME': bool(os.getenv('CLOUDINARY_CLOUD_NAME')),
            'CLOUDINARY_API_KEY': bool(os.getenv('CLOUDINARY_API_KEY')),
            'CLOUDINARY_API_SECRET': bool(os.getenv('CLOUDINARY_API_SECRET'))
        }
    })

# Explicit admin route
@app.route('/admin')
def admin_page():
    index_path = os.path.join(app.static_folder, 'index.html')
    if os.path.exists(index_path):
        return send_file(index_path)
    else:
        return "index.html not found", 404

# Serve React app
@app.route('/')
@app.route('/<path:path>')
def serve_react_app(path=''):
    # Handle API routes first
    if path and path.startswith('api/'):
        return "API endpoint not found", 404
    
    # For any other path, serve the React app
    index_path = os.path.join(app.static_folder, 'index.html')
    if os.path.exists(index_path):
        return send_file(index_path)
    else:
        return "index.html not found", 404

# Initialize with test photo if no photos exist
def initialize_test_data():
    """Add a test photo if no photos exist"""
    photos_data = load_photos_data()
    if not photos_data:
        test_photo = {
            'id': 1,
            'filename': 'test_photo.jpg',
            'title': 'Welcome to Your Photo Gallery!',
            'description': 'This is a test photo. Upload your own photos via the admin panel! Note: Photos will only persist if Cloudinary is configured.',
            'image_url': 'https://via.placeholder.com/800x600/4F46E5/FFFFFF?text=Welcome+to+Your+Gallery',
            'upload_date': datetime.utcnow().isoformat(),
            'storage_type': 'placeholder'
        }
        save_photos_data([test_photo])
        print("📸 Initialized with test photo")

if __name__ == '__main__':
    initialize_test_data()
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Starting Flask app on port {port}")
    print(f"📁 Static folder: {app.static_folder}")
    print(f"☁️ Cloudinary status: {'✅ CONFIGURED' if cloudinary_configured else '❌ NOT CONFIGURED'}")
    if not cloudinary_configured:
        print("⚠️  WARNING: Photos will NOT persist without Cloudinary configuration!")
        print("🔧 Set these environment variables: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET")
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # For gunicorn
    initialize_test_data()
    print("🚀 Running with gunicorn")
    print(f"📁 Static folder: {app.static_folder}")
    print(f"☁️ Cloudinary status: {'✅ CONFIGURED' if cloudinary_configured else '❌ NOT CONFIGURED'}")
    if not cloudinary_configured:
        print("⚠️  WARNING: Photos will NOT persist without Cloudinary configuration!")
        print("🔧 Visit /api/debug for configuration details")

