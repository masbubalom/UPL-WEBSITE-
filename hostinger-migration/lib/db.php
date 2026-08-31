<?php
declare(strict_types=1);
function upl_db(): PDO {
    static $db;
    if ($db instanceof PDO) return $db;
    $c = require __DIR__ . '/../config.php';
    $dsn = 'mysql:host='.$c['db_host'].';port='.$c['db_port'].';dbname='.$c['db_name'].';charset=utf8mb4';
    $db = new PDO($dsn, $c['db_user'], $c['db_pass'], [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC, PDO::ATTR_EMULATE_PREPARES=>false]);
    return $db;
}
function upl_config(): array { static $c; return $c ??= require __DIR__.'/../config.php'; }
function upl_e($v): string { return htmlspecialchars((string)$v, ENT_QUOTES, 'UTF-8'); }
function upl_json(array $data, int $status=200): never { http_response_code($status); header('Content-Type: application/json; charset=utf-8'); echo json_encode($data, JSON_UNESCAPED_UNICODE); exit; }
function upl_admin_required(): void { if (empty($_SESSION['upl_admin_id'])) { header('Location: /admin/login'); exit; } }
function upl_csrf(): string { if (empty($_SESSION['upl_csrf'])) $_SESSION['upl_csrf']=bin2hex(random_bytes(32)); return $_SESSION['upl_csrf']; }
function upl_check_csrf(): void { if (!hash_equals($_SESSION['upl_csrf'] ?? '', $_POST['csrf'] ?? '')) { http_response_code(419); exit('Invalid request token'); } }
