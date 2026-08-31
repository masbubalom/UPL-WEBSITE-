<?php
require_once __DIR__.'/../lib/db.php';
if (!empty($_SESSION['upl_admin_id'])) { header('Location:/admin'); exit; }
$error='';
if ($_SERVER['REQUEST_METHOD']==='POST') {
    upl_check_csrf();
    $u=trim($_POST['username']??''); $p=$_POST['password']??'';
    $st=upl_db()->prepare('SELECT id,password_hash FROM admins WHERE username=? LIMIT 1'); $st->execute([$u]); $a=$st->fetch();
    if ($a && password_verify($p,$a['password_hash'])) { session_regenerate_id(true); $_SESSION['upl_admin_id']=$a['id']; header('Location:/admin'); exit; }
    $error='Invalid username or password.';
}
?><!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UPL Admin Login</title><link rel="stylesheet" href="/static/style.css"></head><body><main class="wrap"><div class="card" style="max-width:480px;margin:80px auto"><h1>UPL <span>Admin</span></h1><?php if($error):?><p class="error"><?=upl_e($error)?></p><?php endif;?><form method="post"><input type="hidden" name="csrf" value="<?=upl_e(upl_csrf())?>"><label>Username</label><input name="username" required autocomplete="username"><label>Password</label><input name="password" type="password" required autocomplete="current-password"><button class="btn" type="submit">LOGIN</button></form></div></main></body></html>