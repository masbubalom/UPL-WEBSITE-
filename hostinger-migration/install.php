<?php
// Run once on Hostinger after importing schema.sql, then DELETE this file.
require_once __DIR__.'/lib/db.php';
$c=upl_config();$user=$c['admin_user']??'admin';$pass=getenv('UPL_ADMIN_PASSWORD')?:'';
if($_SERVER['REQUEST_METHOD']!=='POST'){?><form method="post"><input name="password" type="password" placeholder="New admin password" required minlength="8"><button>Create admin</button></form><?php exit;}
$pass=$_POST['password']??'';if(strlen($pass)<8)exit('Password must be at least 8 characters.');
$s=upl_db()->prepare('INSERT INTO admins(username,password_hash) VALUES(?,?) ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash)');$s->execute([$user,password_hash($pass,PASSWORD_DEFAULT)]);echo 'Admin created. Delete install.php now.';
