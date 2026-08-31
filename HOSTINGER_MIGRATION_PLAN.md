# UPL Hostinger Migration

Target: keep the current UPL interface and move the backend from Flask/PostgreSQL to a Hostinger-compatible stack without changing the public design.

## Current architecture
- Flask/Python backend
- PostgreSQL database
- Existing templates/CSS and admin dashboard
- Razorpay for player registration
- Manual QR screenshot flow planned for team registration
- Cloudinary for image uploads

## Migration architecture
- PHP 8.x backend
- MySQL database
- Existing CSS/layout recreated as closely as possible
- Player Razorpay flow preserved where supported by the PHP implementation
- Team registration: QR payment + JPG/PNG proof + admin manual verification
- Admin: approve/reject/delete registrations; manage teams, fixtures/results, points table, news and gallery
- GitHub remains the source repository

## Safety
This branch is a migration branch. Do not change the existing `main` deployment until the Hostinger version is tested end-to-end.
