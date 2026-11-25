# Airlock IAM Salesdemo - use cases

What the salesdemo can demonstrate with the configuration template, one line per use case. Details (flows,
approvals, settings): [usage](https://github.com/airlock-presales/airlock-iam-salesdemo-instance-template/blob/main/docs/usage.md)
in the instance template. Features of a single instance (added with IAM snippets) are not listed.

## Registration and onboarding

- One **Self-registration** flow with two different options:
  - **Easy**: sign up with an email code, choose a password and register a second factor.
  - **With identity check**: PXL Vision scan of an ID document fills in name, document data and country.

## Login

- **Password and second factor**: Airlock 2FA, passkey, OATH OTP or email OTP, according to the user's preferred method.
- **Passwordless** login with a passkey.
- **Username-less login**: QR code scanned with the Airlock 2FA app.
- **Remember-me**: a recognized device skips steps at the next login.

## Self-services (portal)

- **Manage factors**: passkeys, Airlock 2FA devices, OATH OTP, email OTP - with approval before a factor is removed.
- **Change profile data**: password, name, email address.
- **Choose the preferred login method**: if not set, user is asked with every login.
- **Recovery data**: alternate email address; "Verify identity" with an ID document (step-up to a second factor).
- **Airlock 2FA recovery information** for a new phone (setting `airlock_iam_airlock2fa_recovery_info`).

## Account recovery

- **Forgotten password**: email code and approval with an existing second factor.
- **Recover second factor**: proof who you are by performing various, independently not very secure, identification flows collecting points until the threshold is reached, then register a new factor.
- **Administrator confirms a user's recovery** in the portal.

## Helpdesk

- **User management**: profile data, delete or create users.
- **Lock and unlock users**: the user gets a friendly notification email.
- **Remove a user's factor(s)** as a helpdesk action.
