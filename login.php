<?php

header('Content-Type: application/json');

$users = [
    [
        "login" => "test",
        "password" => "123",
        "expires_at" => "31.12.2025",
        "subscription_type" => "Premium"
    ]
];

$input = $_POST;

if (!isset($input['login']) || !isset($input['password'])) {
    echo json_encode([
        "status" => "error",
        "message" => "no_data"
    ]);
    exit;
}

foreach ($users as $user) {

    if ($user['login'] == $input['login']) {

        if ($user['password'] != $input['password']) {

            echo json_encode([
                "status" => "error",
                "message" => "wrong_password"
            ]);
            exit;
        }

        echo json_encode([
            "status" => "success",
            "expires_at" => $user['expires_at'],
            "subscription_type" => $user['subscription_type']
        ]);

        exit;
    }
}

echo json_encode([
    "status" => "error",
    "message" => "user_not_found"
]);
