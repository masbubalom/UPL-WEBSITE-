<?php
require __DIR__ . '/db.php';
$pdo=db();
if ((int)$pdo->query('SELECT COUNT(*) FROM admins')->fetchColumn() > 0) { http_response_code(403); exit('Admin already configured.'); }
$message='';
if ($_SERVER['REQUEST_METHOD']==='POST') {
    $u=trim($_POST['username']??''); $p=$_POST['password']??'';
    if($u!=='' && strlen($p)>=8){$s=$pdo->prepare('INSERT INTO admins(username,password_hash) VALUES(?,?)');$s->execute([$u,password_hash($p,PASSWORD_DEFAULT)]);$message='Admin created. Delete setup_admin.php now, then open /?page=admin-login';}
    else $message='Username is required and password must be at least 8 characters.';
}
?><!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UPL Admin Setup</title><link rel="stylesheet" href="/static/style.css"></head><body><main class="wrap"><div class="card" style="max-width:520px;margin:auto"><h2>UPL ADMIN SETUP</h2><p><?=htmlspecialchars($message)?></p><form method="post"><label>Username</label><input name="username" required><label>Password</label><input name="password" type="password" minlength="8" required><button class="btn" style="margin-top:15px">CREATE ADMIN</button></form></div></main></body></html>
