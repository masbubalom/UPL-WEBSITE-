<?php
// UPL Hostinger migration bootstrap.
declare(strict_types=1);
session_start();
$configFile = __DIR__ . '/../config.php';
if (!is_file($configFile)) {
    http_response_code(503);
    exit('UPL is not configured yet. Please create config.php on Hostinger.');
}
$config = require $configFile;
function db(): PDO {
    static $pdo = null;
    global $config;
    if ($pdo instanceof PDO) return $pdo;
    $dsn = sprintf('mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4', $config['db_host'], $config['db_port'], $config['db_name']);
    $pdo = new PDO($dsn, $config['db_user'], $config['db_pass'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC]);
    return $pdo;
}
function e(?string $v): string { return htmlspecialchars((string)$v, ENT_QUOTES, 'UTF-8'); }
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
if ($path === '/health') { header('Content-Type: application/json'); echo json_encode(['status'=>'ok','service'=>'UPL Website']); exit; }
try {
    if ($path === '/' || $path === '/index.php') {
        $fixtures=db()->query("SELECT * FROM fixtures ORDER BY match_date, match_time LIMIT 3")->fetchAll();
        $news=db()->query("SELECT * FROM news WHERE published=1 ORDER BY id DESC LIMIT 3")->fetchAll();
        require __DIR__.'/home.php'; exit;
    }
    if ($path === '/teams') { $teams=db()->query('SELECT * FROM teams ORDER BY name')->fetchAll(); require __DIR__.'/teams.php'; exit; }
    if ($path === '/players') { $players=db()->query("SELECT * FROM players WHERE status='Approved' ORDER BY full_name")->fetchAll(); require __DIR__.'/players.php'; exit; }
    if ($path === '/fixtures') { $fixtures=db()->query('SELECT * FROM fixtures ORDER BY match_date, match_time')->fetchAll(); require __DIR__.'/fixtures.php'; exit; }
    if ($path === '/points-table') { $points=db()->query('SELECT * FROM points_table ORDER BY group_name, points DESC, nrr DESC, team_name')->fetchAll(); require __DIR__.'/points.php'; exit; }
    if ($path === '/news') { $news=db()->query('SELECT * FROM news WHERE published=1 ORDER BY id DESC')->fetchAll(); require __DIR__.'/news.php'; exit; }
    if ($path === '/gallery') { $gallery=db()->query('SELECT * FROM gallery ORDER BY id DESC')->fetchAll(); require __DIR__.'/gallery.php'; exit; }
    if ($path === '/registration') { require __DIR__.'/registration.php'; exit; }
    if ($path === '/team-registration') { require __DIR__.'/team_registration.php'; exit; }
    http_response_code(404); echo 'UPL page not found';
} catch (Throwable $ex) {
    error_log('UPL error: '.$ex->getMessage());
    http_response_code(500); echo 'UPL is temporarily unavailable.';
}
