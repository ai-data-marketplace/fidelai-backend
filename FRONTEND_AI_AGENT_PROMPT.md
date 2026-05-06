# Frontend AI Agent Prompt: Backend API Integration Guide

You are assisting with integrating the FidelAI backend authentication APIs into the frontend. Here is the complete specification of all authentication endpoints you need to work with.

## Backend Base URL
The backend API base URL for users endpoints is: `/api/users/`

All endpoints are prefixed with this URL. For example, registration endpoint is: `/api/users/register/`

---

## API Endpoints Specification

### 1. REGISTER
- **HTTP Method:** POST
- **Endpoint:** `/api/users/register/`
- **Authentication:** No
- **Request Body:**
  ```
  {
    "full_name": "string (required, max 255 chars)",
    "email": "string (required, valid email)",
    "password": "string (required)"
  }
  ```
- **Password Rules:** Min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char
- **Success Response:** HTTP 201
  ```
  {
    "message": "Verification code sent to email",
    "email": "user@example.com"
  }
  ```
- **Error Examples:**
  - Email already exists: HTTP 400 → `{"message": "A user with this email already exists."}`
  - Weak password: HTTP 400 → `{"password": ["error message about password requirement"]}`

---

### 2. VERIFY EMAIL
- **HTTP Method:** POST
- **Endpoint:** `/api/users/verify-email/`
- **Authentication:** No
- **Request Body:**
  ```
  {
    "email": "string (required, valid email)",
    "code": "string (required, exactly 6 digits)"
  }
  ```
- **Code Validity:** 10 minutes from creation
- **Success Response:** HTTP 200
  ```
  {
    "message": "Email verified successfully"
  }
  ```
- **Error Examples:**
  - Invalid code: HTTP 400 → `{"message": "Invalid verification code."}`
  - Expired code: HTTP 400 → `{"message": "Verification code expired or unavailable."}`
  - User not found: HTTP 400 → `{"message": "Invalid email or code."}`

---

### 3. RESEND CODE
- **HTTP Method:** POST
- **Endpoint:** `/api/users/resend-code/`
- **Authentication:** No
- **Request Body:**
  ```
  {
    "email": "string (required, valid email)"
  }
  ```
- **Rate Limit:** Max once per 60 seconds
- **Success Response:** HTTP 200
  ```
  {
    "message": "Verification code sent to email"
  }
  ```
- **Error Examples:**
  - Rate limited: HTTP 429 → `{"message": "Please wait before requesting another code."}`
  - User not found: HTTP 400 → `{"message": "User not found."}`

---

### 4. LOGIN
- **HTTP Method:** POST
- **Endpoint:** `/api/users/login/`
- **Authentication:** No
- **Request Body:**
  ```
  {
    "email": "string (required, valid email)",
    "password": "string (required)"
  }
  ```
- **Success Response:** HTTP 200
  ```
  {
    "access": "eyJhbGciOiJIUzI1NiIs...",
    "refresh": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
      "id": "uuid-string",
      "email": "user@example.com",
      "full_name": "Full Name",
      "role": "UNKNOWN"
    }
  }
  ```
- **Token Validity:**
  - Access token: 60 minutes
  - Refresh token: 7 days
- **Account Lock:** After 5 failed attempts, account locks for 15 minutes
- **Error Examples:**
  - Invalid credentials: HTTP 401 → `{"message": "Invalid credentials."}`
  - Email not verified: HTTP 403 → `{"message": "Please verify your email before logging in."}`
  - Account locked: HTTP 423 → `{"message": "Account locked for 15 minutes due to repeated failed logins."}`

---

### 5. ME (Get Current User)
- **HTTP Method:** GET
- **Endpoint:** `/api/users/me/`
- **Authentication:** Yes (Bearer access_token)
- **Request Headers:**
  ```
  Authorization: Bearer <access_token>
  ```
- **Request Body:** None
- **Success Response:** HTTP 200
  ```
  {
    "id": "uuid-string",
    "email": "user@example.com",
    "full_name": "Full Name",
    "role": "UNKNOWN",
    "is_verified": true
  }
  ```
- **Error Examples:**
  - Missing token: HTTP 401 → `{"detail": "Authentication credentials were not provided."}`
  - Expired token: HTTP 401 → `{"detail": "Given token is invalid for any token type"}`
  - Invalid token: HTTP 401 → `{"detail": "Given token is invalid for any token type"}`

---

### 6. TOKEN REFRESH
- **HTTP Method:** POST
- **Endpoint:** `/api/users/token/refresh/`
- **Authentication:** No
- **Request Body:**
  ```
  {
    "refresh": "string (required, refresh token)"
  }
  ```
- **Success Response:** HTTP 200
  ```
  {
    "access": "eyJhbGciOiJIUzI1NiIs...",
    "refresh": "eyJhbGciOiJIUzI1NiIs..."
  }
  ```
- **Important:** Both access and refresh tokens are rotated. Store both new tokens.
- **Error Examples:**
  - Invalid token: HTTP 400 → `{"detail": "Token is invalid or expired"}`
  - Expired token: HTTP 400 → `{"detail": "Token is invalid or expired"}`
  - Missing token: HTTP 400 → `{"refresh": ["This field may not be blank."]}`

---

### 7. TOKEN VERIFY
- **HTTP Method:** POST
- **Endpoint:** `/api/users/token/verify/`
- **Authentication:** No
- **Request Body:**
  ```
  {
    "token": "string (required, access token)"
  }
  ```
- **Success Response:** HTTP 200
  ```
  {}
  ```
- **Use Case:** Verify if a token is valid without using it for actual requests
- **Error Examples:**
  - Invalid token: HTTP 400 → `{"detail": "Token is invalid or expired"}`
  - Expired token: HTTP 400 → `{"detail": "Token is invalid or expired"}`
  - Missing token: HTTP 400 → `{"token": ["This field may not be blank."]}`

---

### 8. FORGOT PASSWORD
- **HTTP Method:** POST
- **Endpoint:** `/api/users/forgot-password/`
- **Authentication:** No
- **Request Body:**
  ```
  {
    "email": "string (required, valid email)"
  }
  ```
- **Success Response:** HTTP 200 (Always, regardless of email existence)
  ```
  {
    "message": "A password reset link has been sent."
  }
  ```
- **Important:** This endpoint always returns HTTP 200 with the same message for security. Do not use it to check if an email exists.
- **Email Content:** Contains a link in format: `https://your-frontend.com/account/reset-password/{uid}/{token}/`

---

### 9. RESET PASSWORD
- **HTTP Method:** POST
- **Endpoint:** `/api/users/reset-password/`
- **Authentication:** No
- **Request Body:**
  ```
  {
    "uid": "string (required, base64 encoded user ID from reset link)",
    "token": "string (required, token from reset link)",
    "new_password": "string (required)"
  }
  ```
- **Password Rules:** Min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char
- **How to get uid and token:** Extract from the reset link URL path: `/account/reset-password/{uid}/{token}/`
- **Success Response:** HTTP 200
  ```
  {
    "message": "Password reset successful"
  }
  ```
- **Error Examples:**
  - Invalid link: HTTP 400 → `{"message": "Invalid password reset link."}`
  - Expired token: HTTP 400 → `{"message": "Invalid or expired password reset token."}`
  - Weak password: HTTP 400 → `{"message": "Password must include at least one [requirement]."`

---

## Frontend Implementation Checklist

- [ ] Store access and refresh tokens securely (HttpOnly cookies or secure storage)
- [ ] Implement automatic token refresh when access token expires
- [ ] Add Authorization header for authenticated requests: `Authorization: Bearer <access_token>`
- [ ] Handle 401 errors by redirecting to login
- [ ] Display appropriate error messages from response body
- [ ] Implement email verification UI with code input and resend option
- [ ] Implement password reset flow: request → check email → extract uid/token from link → reset
- [ ] Handle rate limiting (429) for resend-code endpoint
- [ ] Handle account lock (423) and display appropriate message
- [ ] Clear tokens on logout and redirect to login page

---

## Typical User Flows

### Sign Up Flow
1. User fills registration form (full_name, email, password)
2. POST to `/register/` 
3. Show email verification screen
4. User enters 6-digit code from email
5. POST to `/verify-email/`
6. Redirect to login

### Login Flow
1. User enters email and password
2. POST to `/login/`
3. Store access and refresh tokens
4. Redirect to dashboard
5. Use GET `/me/` to fetch user profile

### Protected API Calls
1. Before each request, check if access_token is expired
2. If expired, POST to `/token/refresh/` with refresh_token
3. Update stored tokens
4. Add `Authorization: Bearer <access_token>` header
5. Make the actual request

### Password Reset Flow
1. User enters email on "Forgot Password" page
2. POST to `/forgot-password/`
3. Show message: "Check your email for password reset link"
4. User receives email with link: `/account/reset-password/{uid}/{token}/`
5. User clicks link, frontend extracts uid and token
6. User enters new password
7. POST to `/reset-password/` with uid, token, new_password
8. Show success and redirect to login

