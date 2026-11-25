<?php
// Adminer automatic login behind Microgateway (plugin login-auth-proxy, vendored unchanged from
// https://github.com/omattsson/adminer-login-auth-proxy, commit efbef4c, Apache-2.0 or GPL-2.0).
// ADMINER_AUTH_KEY: $_SERVER key of the user header set by Microgateway (unguessable name, from the
// project settings); DB_USERNAME/DB_PASSWORD: IAM database account (secret adminer-db).
require_once '/var/www/html/adminer-plugins/login-auth-proxy.php';
return new AdminerLoginAuthProxy(getenv('ADMINER_AUTH_KEY'), 'server',
	'iam-mariadb.iam.svc.cluster.local:3306', getenv('DB_USERNAME'), getenv('DB_PASSWORD'), 'iam');
