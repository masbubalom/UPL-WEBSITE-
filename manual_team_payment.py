import os
from pathlib import Path
from flask import request, jsonify

def register_manual_team_payment(app, db, next_team_interest, admin_required, cloudinary):
    @app.post('/api/team-interest/manual-submit')
    def manual_team_interest_submit():
        f = request.form
        image = request.files.get('payment_screenshot')
        required = ['team_name','contact_name','phone','email','village','panchayat']
        if any(not f.get(k,'').strip() for k in required):
            return jsonify(ok=False, error='Please complete all registration fields.'), 400
        if not image or not image.filename:
            return jsonify(ok=False, error='Please upload the successful ₹100 payment screenshot.'), 400
        if Path(image.filename).suffix.lower() not in {'.jpg','.jpeg','.png'}:
            return jsonify(ok=False, error='Payment screenshot must be JPG or PNG.'), 400
        if not os.environ.get('CLOUDINARY_CLOUD_NAME'):
            return jsonify(ok=False, error='Payment upload is temporarily unavailable. Please contact the UPL Organising Committee.'), 503
        c = db()
        try:
            interest_no = next_team_interest(c)
            upload = cloudinary.uploader.upload(image, folder='upl/team-payment-screenshots', resource_type='image')
            screenshot_url = upload['secure_url']
            c.execute("ALTER TABLE team_interest ADD COLUMN IF NOT EXISTS payment_screenshot_path TEXT")
            c.execute("INSERT INTO team_interest (interest_no,team_name,contact_name,phone,email,village,gram_panchayat,registration_fee,interest_charge,payment_status,status,paid_amount,payment_reference,payment_screenshot_path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (interest_no,f['team_name'].strip(),f['contact_name'].strip(),f['phone'].strip(),f['email'].strip(),f['village'].strip(),f['panchayat'].strip(),5000,100,'Manual Review','Pending Verification',100,'Manual QR Payment',screenshot_url))
            c.commit()
            return jsonify(ok=True, interest_no=interest_no)
        except Exception as e:
            c.rollback()
            print('MANUAL TEAM PAYMENT ERROR:', repr(e))
            return jsonify(ok=False, error='Unable to submit the registration right now. Please try again.'), 500
        finally:
            c.close()
