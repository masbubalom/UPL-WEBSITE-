# UPL Hostinger deployment

This migration keeps the existing UPL visual design while replacing the Flask/PostgreSQL runtime with a Hostinger-compatible PHP/MySQL runtime.

## Deployment flow

GitHub (`hostinger-migration` branch) -> Hostinger PHP hosting -> MySQL

## Required server setup

1. Create a MySQL database and user in Hostinger hPanel.
2. Upload the contents of this migration to the domain's `public_html` directory.
3. Copy `config.example.php` to `config.php` and enter the database credentials and Razorpay keys.
4. Import the generated MySQL schema.
5. Ensure PHP 8.x is selected.
6. Test `/health`, player registration, team registration, admin login, and all public pages before switching production traffic.

## Security

- `config.php` must not be committed to GitHub.
- Use HTTPS.
- Keep Razorpay secret keys server-side only.
- Restrict admin access with a strong password.
- Do not expose database credentials in templates or JavaScript.
