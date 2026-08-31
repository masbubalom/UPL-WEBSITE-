<?php
require_once __DIR__ . '/db.php';

global $config;
function razorpay_request(string $method, string $path, array $payload=[]): array {
    global $config;
    $ch=curl_init('https://api.razorpay.com/v1'.$path);
    curl_setopt_array($ch,[CURLOPT_RETURNTRANSFER=>true,CURLOPT_CUSTOMREQUEST=>$method,CURLOPT_USERPWD=>$config['razorpay_key_id'].':'.$config['razorpay_key_secret'],CURLOPT_HTTPHEADER=>['Content-Type: application/json']]);
    if($method!=='GET') curl_setopt($ch,CURLOPT_POSTFIELDS,json_encode($payload));
    $raw=curl_exec($ch); $code=curl_getinfo($ch,CURLINFO_HTTP_CODE); curl_close($ch);
    $data=json_decode($raw ?: '{}',true);
    if($code<200 || $code>=300) throw new RuntimeException($data['error']['description'] ?? 'Razorpay request failed');
    return $data;
}
function razorpay_signature_valid(string $orderId,string $paymentId,string $signature): bool {
    global $config;
    $expected=hash_hmac('sha256',$orderId.'|'.$paymentId,$config['razorpay_key_secret']);
    return hash_equals($expected,$signature);
}
