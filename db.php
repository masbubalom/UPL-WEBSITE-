<?php
$config = require __DIR__ . '/config.php';

function db(): PDO {
    static $pdo = null;
    global $config;
    if ($pdo instanceof PDO) return $pdo;
    $dsn = 'mysql:host=' . $config['db_host'] . ';port=' . ($config['db_port'] ?? 3306) . ';dbname=' . $config['db_name'] . ';charset=utf8mb4';
    $pdo = new PDO($dsn, $config['db_user'], $config['db_pass'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    return $pdo;
}

function e($value): string { return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8'); }
function redirect_to(string $url): never { header('Location: ' . $url); exit; }
function require_admin(): void { if (empty($_SESSION['admin'])) redirect_to('/?page=admin-login'); }
function next_no(string $prefix, string $table, string $column): string {
    $pdo = db();
    do { $no = $prefix . strtoupper(bin2hex(random_bytes(3))); $s=$pdo->prepare("SELECT 1 FROM `$table` WHERE `$column`=? LIMIT 1"); $s->execute([$no]); } while ($s->fetchColumn());
    return $no;
}
function upload_image(array $file, string $folder): ?string {
    if (($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) return null;
    $ext = strtolower(pathinfo($file['name'], PATHINFO_EXTENSION));
    if (!in_array($ext, ['jpg','jpeg','png','webp'], true)) return null;
    $dir = __DIR__ . '/uploads/' . trim($folder, '/');
    if (!is_dir($dir)) mkdir($dir, 0755, true);
    $name = bin2hex(random_bytes(12)) . '.' . $ext;
    if (!move_uploaded_file($file['tmp_name'], $dir . '/' . $name)) return null;
    return '/uploads/' . trim($folder, '/') . '/' . $name;
}
