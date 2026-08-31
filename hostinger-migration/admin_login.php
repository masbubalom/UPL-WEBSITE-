<?php
require_once __DIR__.'/lib/db.php';
if(!empty($_SESSION['upl_admin_id'])){header('Location:/admin');exit;}
$error='';
if($_SERVER['REQUEST_METHOD']==='POST'){
 upl_check_csrf(); $u=trim($_POST['username']??'');$p=$_POST['password']??'';
 $s=upl_db()->prepare('SELECT * FROM admins WHERE username=? LIMIT 1');$s->execute([$u]);$a=$s->fetch();
 if($a&&password_verify($p,$a['password_hash'])){session_regenerate_id(true);$_SESSION['upl_admin_id']=$a['id'];header('Location:/admin');exit;}
 $error='Invalid username or password.';
}
?><!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UPL Admin Login</title><link rel="stylesheet" href="/static/style.css"></head><body><main class="wrap"><div class="card"><h1>UPL Admin</h1><?php if($error):?><p><?=upl_e($error)?></p><?php endif;?><form method="post"><input type="hidden" name="csrf" value="<?=upl_csrf()?>"><input name="username" placeholder="Username" required><input name="password" type="password" placeholder="Password" required><button class="btn">Login</button></form></div></main></body></html>