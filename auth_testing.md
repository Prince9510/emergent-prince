# Authentication testing playbook

1. Use credentials in `/app/memory/test_credentials.md`.
2. POST `/api/auth/login` with JSON email/password and confirm `access_token` plus user data.
3. Call `/api/auth/me` with `Authorization: Bearer <access_token>` and confirm the password is never returned.
4. Call a protected endpoint without a token and confirm `401`.
5. Call `POST /api/auth/logout`, clear the token, and confirm protected access is denied.
6. Confirm invalid credentials return a friendly `401` message.