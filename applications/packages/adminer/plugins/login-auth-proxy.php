<?php

/** Log in automatically to a fixed server behind an authenticating proxy which sends the user in a header
* Adminer must be reachable only through the proxy, which must set or remove the header on every request, including its variants with underscores.
* PHP maps X-Auth-Request-Email and X_Auth_Request_Email to the same key, and some proxy versions strip only the dashed name.
* A server variable set by the web server, such as REMOTE_USER, can't come from the client.
* All users share the database account, so limit it by GRANT; $database only limits the list of databases and the URL.
* Log out through the proxy, e.g. /oauth2/sign_out; Adminer's logout logs in again.
* Use it as the only login plugin.
* @link https://www.adminer.org/plugins/#use
* @author Olof Mattsson, https://github.com/omattsson
* @license https://www.apache.org/licenses/LICENSE-2.0 Apache License, Version 2.0
* @license https://www.gnu.org/licenses/gpl-2.0.html GNU General Public License, version 2 (one or other)
*/
class AdminerLoginAuthProxy extends Adminer\Plugin {
	protected $key, $driver, $server, $username, $password, $database;
	private $posted = false;

	/**
	* @param string $key key of $_SERVER with the user, e.g. "HTTP_X_AUTH_REQUEST_EMAIL" for the header X-Auth-Request-Email from oauth2-proxy, or "REMOTE_USER"
	* @param string $driver note that the driver for MySQL is called 'server'
	* @param string $server
	* @param string $username
	* @param string $password
	* @param string $database "" to list all databases
	*/
	function __construct($key, $driver, $server, $username, $password, $database = "") {
		if (!preg_match('~^[A-Z][A-Z0-9_]*$~', $key)) {
			// not an exception, its stack trace can print the password
			header("HTTP/1.1 500 Internal Server Error");
			exit("AdminerLoginAuthProxy: The first parameter must be a key of \$_SERVER, e.g. HTTP_X_AUTH_REQUEST_EMAIL or REMOTE_USER.\n");
		}
		$this->key = $key;
		$this->driver = $driver;
		$this->server = $server;
		$this->username = $username;
		$this->password = $password;
		$this->database = $database;
		$submitted = $_POST["auth"];
		unset($_POST["auth"]); // restored below only for a logged in proxy user with a valid token
		$user = $this->proxyUser();
		if ($user != "") {
			if ($_SESSION["login_auth_proxy"] !== $user) {
				$_SESSION = array("login_auth_proxy" => $user); // another user in the same browser doesn't get the session of the previous one
			}
			if (!$_SESSION["token"] && (!$_COOKIE[session_name()] || !in_array($_SERVER["HTTP_SEC_FETCH_SITE"], array("", "same-origin")))) {
				$_POST = array(); // sent from another website, the button in loginForm() would run its action by a single click
			}
			// the same request as the login form; credentials() adds the password, so the session doesn't keep it
			$auth = array("driver" => $driver, "server" => $server, "username" => $username, "password" => "");
			if ($_POST && $submitted && $_SESSION["token"] && Adminer\verify_token()) { // the button in loginForm()
				$_POST["auth"] = $auth + array("db" => "$_GET[db]"); // the same db performs the action instead of redirecting
			} elseif (!$_POST && ($_GET["username"] !== $username || !isset($_SESSION["pwds"][$driver][$server][$username]))) { // isset() tells the stored "" of a login from the null of a failed one
				$_POST["auth"] = $auth + array("db" => ($database != "" ? $database : "$_GET[db]"));
				$this->posted = true;
			}
		}
	}

	function credentials() {
		// the URL can name another driver or server, send the password only to the configured one
		return array($this->server, $this->username, ($this->configured($_GET["username"]) ? $this->password : ""));
	}

	function bruteForceKey() {
		return Adminer\rand_string(); // the user doesn't enter any password, so a failure is not an attempt to guess it and must not lock the user out
	}

	function verifyLoginToken() {
		if ($this->posted) {
			return false; // the automatic login has no token
		}
	}

	function login($login, $password) {
		// called on every request, so a session doesn't outlive the proxy
		if ($this->proxyUser() == "") {
			return $this->lang('Log in through the authenticating proxy.');
		}
		return ($this->configured($login) && ($this->database == "" || Adminer\DB == "" || Adminer\DB === $this->database));
	}

	function databases($flush = true) {
		if ($this->database != "") {
			return array($this->database);
		}
	}

	function loginForm() {
		if ($this->proxyUser() == "") {
			// phpcs:ignore Squiz.PHP.DiscouragedFunctions -- the page must not tell a client which key to forge
			error_log("AdminerLoginAuthProxy: \$_SERVER['$this->key'] is empty, the request didn't come through the proxy or the key is wrong");
			echo "<p>" . $this->lang('Log in through the authenticating proxy.') . "\n";
		} else {
			echo ($_POST ? "" : "<p>" . $this->lang('The automatic login failed.') . "\n");
			echo "<p><input type='submit' name='auth' value='" . Adminer\h($this->lang('Log in')) . "'>\n"; // the constructor replaces the value
		}
		return true;
	}

	/** Check if the request uses the configured driver, server and user */
	private function configured($login) {
		return (Adminer\DRIVER === $this->driver && Adminer\SERVER === $this->server && $login === $this->username);
	}

	/** Get the user sent by the proxy, "" without the proxy */
	private function proxyUser() {
		return ($this->key != "" ? trim(strval($_SERVER[$this->key])) : "");
	}

	protected $translations = array(
		'cs' => array(
			'' => 'Automaticky přihlásí k pevně danému serveru za ověřující proxy, která posílá uživatele v hlavičce', // Claude Opus 5.5
			'Log in through the authenticating proxy.' => 'Přihlaste se přes ověřující proxy.', // Claude Opus 5.5
			'The automatic login failed.' => 'Automatické přihlášení selhalo.', // Claude Opus 5.5
			'Log in' => 'Přihlásit se', // Claude Opus 5.5
		),
		'de' => array(
			'' => 'Automatische Anmeldung an einem festen Server hinter einem authentifizierenden Proxy, der den Benutzer in einem Header sendet', // Claude Opus 5.5
			'Log in through the authenticating proxy.' => 'Melden Sie sich über den authentifizierenden Proxy an.', // Claude Opus 5.5
			'The automatic login failed.' => 'Die automatische Anmeldung ist fehlgeschlagen.', // Claude Opus 5.5
			'Log in' => 'Anmelden', // Claude Opus 5.5
		),
	);
}
