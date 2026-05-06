# FidelAI Backend Authentication API Documentation

This document outlines all authentication-related API endpoints that the frontend should integrate with. Each endpoint specifies the expected request format, response format, and possible error scenarios.

## Base URL
```
http://localhost:8000/api/users/  (or your deployed backend URL)
```

## Authentication Headers
For protected endpoints (those requiring authentication), include:
```
Authorization: Bearer <access_token>
```

---

## 1. Register (Create Account)

**Endpoint:** `POST /register/`

**Authentication:** Not required

**Description:** Creates a new user account and sends a verification code to their email.

### Request Body
```json
{
  "full_name": "string (max 255 characters)",
  "email": "string (valid email format)",
  "password": "string"
}
```

### Password Requirements
- Minimum 8 characters long
- At least one uppercase letter (A-Z)
- At least one lowercase letter (a-z)
- At least one digit (0-9)
- At least one special character (!@#$%^&*, etc.)

### Example Request
```json
{
  "full_name": "John Doe",
  "email": "john@example.com",
  "password": "SecurePass123!"
}
```

### Success Response (HTTP 201 Created)
```json
{
  "message": "Verification code sent to email",
  "email": "john@example.com"
}
```

### Error Responses
- **HTTP 400 Bad Request**
  - Missing required fields: `{"field": ["This field is required."]}`
  - Invalid email format: `{"email": ["Enter a valid email address."]}`
  - Weak password: `{"password": ["Password must include at least one uppercase letter."]}`
  - Email already exists: `{"message": "A user with this email already exists."}`

---

## 2. Verify Email

**Endpoint:** `POST /verify-email/`

**Authentication:** Not required

**Description:** Verifies the user's email using the 6-digit code sent during registration.

### Request Body
```json
{
  "email": "string (valid email format)",
  "code": "string (exactly 6 digits)"
}
```

### Example Request
```json
{
  "email": "john@example.com",
  "code": "123456"
}
```

### Success Response (HTTP 200 OK)
```json
{
  "message": "Email verified successfully"
}
```

### Error Responses
- **HTTP 400 Bad Request**
  - Invalid email: `{"message": "Invalid email or code."}`
  - Expired code: `{"message": "Verification code expired or unavailable."}`
  - Wrong code: `{"message": "Invalid verification code."}`
  - Invalid code format: `{"code": ["Ensure this field has no more than 6 characters."]}`

---

## 3. Resend Verification Code

**Endpoint:** `POST /resend-code/`

**Authentication:** Not required

**Description:** Resends the verification code to the user's email. Limited to one request per 60 seconds.

### Request Body
```json
{
  "email": "string (valid email format)"
}
```

### Example Request
```json
{
  "email": "john@example.com"
}
```

### Success Response (HTTP 200 OK)
```json
{
  "message": "Verification code sent to email"
}
```

### Error Responses
- **HTTP 400 Bad Request**
  - User not found: `{"message": "User not found."}`
  - Invalid email format: `{"email": ["Enter a valid email address."]}`
  
- **HTTP 429 Too Many Requests**
  - Rate limit exceeded: `{"message": "Please wait before requesting another code."}`

---

## 4. Login

**Endpoint:** `POST /login/`

**Authentication:** Not required

**Description:** Authenticates the user and returns JWT tokens along with user information.

### Request Body
```json
{
  "email": "string (valid email format)",
  "password": "string"
}
```

### Example Request
```json
{
  "email": "john@example.com",
  "password": "SecurePass123!"
}
```

### Success Response (HTTP 200 OK)
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "john@example.com",
    "full_name": "John Doe",
    "role": "UNKNOWN"
  }
}
```

### Token Information
- **access_token:** Valid for 60 minutes
- **refresh_token:** Valid for 7 days
- Use the access token in the Authorization header for authenticated requests
- When access token expires, use refresh token to get a new one

### Error Responses
- **HTTP 401 Unauthorized**
  - Invalid credentials: `{"message": "Invalid credentials."}`
  - User not found: `{"message": "Invalid credentials."}`

- **HTTP 403 Forbidden**
  - Email not verified: `{"message": "Please verify your email before logging in."}`

- **HTTP 423 Locked**
  - Account locked after 5 failed login attempts: `{"message": "Account locked for 15 minutes due to repeated failed logins."}`
  - Account temporarily locked: `{"message": "Account is locked. Try again later."}`

---

## 5. Get Current User (Me)

**Endpoint:** `GET /me/`

**Authentication:** Required (Access Token)

**Description:** Returns the authenticated user's profile information.

### Request Headers
```
Authorization: Bearer <access_token>
```

### Request Body
None

### Success Response (HTTP 200 OK)
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "john@example.com",
  "full_name": "John Doe",
  "role": "UNKNOWN",
  "is_verified": true
}
```

### Error Responses
- **HTTP 401 Unauthorized**
  - Missing or invalid token: `{"detail": "Authentication credentials were not provided."}`
  - Expired token: `{"detail": "Given token is invalid for any token type"}`

---

## 6. Token Refresh

**Endpoint:** `POST /token/refresh/`

**Authentication:** Not required

**Description:** Uses a refresh token to obtain a new access token. The refresh token is also rotated on each successful refresh.

### Request Body
```json
{
  "refresh": "string (refresh token)"
}
```

### Example Request
```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Success Response (HTTP 200 OK)
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Token Information
- New access token is valid for 60 minutes
- New refresh token is valid for 7 days
- Store both tokens as they are both rotated

### Error Responses
- **HTTP 400 Bad Request**
  - Missing refresh token: `{"refresh": ["This field may not be blank."]}`
  - Invalid refresh token: `{"detail": "Token is invalid or expired"}`
  - Expired refresh token: `{"detail": "Token is invalid or expired"}`

---

## 7. Token Verify

**Endpoint:** `POST /token/verify/`

**Authentication:** Not required

**Description:** Verifies whether an access token is valid without using it.

### Request Body
```json
{
  "token": "string (access token)"
}
```

### Example Request
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Success Response (HTTP 200 OK)
```json
{}
```

### Error Responses
- **HTTP 400 Bad Request**
  - Missing token: `{"token": ["This field may not be blank."]}`
  - Invalid token: `{"detail": "Token is invalid or expired"}`
  - Expired token: `{"detail": "Token is invalid or expired"}`

---

## 8. Forgot Password

**Endpoint:** `POST /forgot-password/`

**Authentication:** Not required

**Description:** Initiates password reset by sending a reset link to the user's email. Returns the same message regardless of whether the email exists (for security).

### Request Body
```json
{
  "email": "string (valid email format)"
}
```

### Example Request
```json
{
  "email": "john@example.com"
}
```

### Success Response (HTTP 200 OK)
```json
{
  "message": "A password reset link has been sent."
}
```

**Note:** This endpoint always returns HTTP 200 with the same message, whether or not the email exists in the system. This is for security reasons to prevent email enumeration attacks.

### Error Responses
- None specific - always returns HTTP 200 OK with the message above

---

## 9. Reset Password

**Endpoint:** `POST /reset-password/`

**Authentication:** Not required

**Description:** Resets the user's password using the reset link credentials. The reset link contains the `uid` and `token` that were sent via email.

### Request Body
```json
{
  "uid": "string (base64 encoded user ID from reset link)",
  "token": "string (token from reset link)",
  "new_password": "string"
}
```

### Password Requirements
Same as registration:
- Minimum 8 characters long
- At least one uppercase letter (A-Z)
- At least one lowercase letter (a-z)
- At least one digit (0-9)
- At least one special character

### Example Request
```json
{
  "uid": "NTUwZTg0MDAtZTI5Yi00MWQ0LWE3MTYtNDQ2NjU1NDQwMDAw",
  "token": "6b3-1b8c2f3e4d5c6b7a",
  "new_password": "NewSecurePass456!"
}
```

### Success Response (HTTP 200 OK)
```json
{
  "message": "Password reset successful"
}
```

### Error Responses
- **HTTP 400 Bad Request**
  - Invalid uid or token: `{"message": "Invalid password reset link."}`
  - Expired token: `{"message": "Invalid or expired password reset token."}`
  - Weak new password: `{"message": "Password must include at least one uppercase letter."}`
  - Missing fields: `{"field": ["This field is required."]}`

---

## Common Error Handling

### Validation Errors (HTTP 400)
When validation fails, the response includes field-specific errors:
```json
{
  "field_name": ["error message"],
  "another_field": ["error message"]
}
```

### Authentication Errors (HTTP 401)
```json
{
  "detail": "Authentication credentials were not provided." 
}
```

### Permission Errors (HTTP 403)
```json
{
  "detail": "You do not have permission to perform this action."
}
```

### Rate Limiting (HTTP 429)
```json
{
  "message": "Please wait before requesting another code."
}
```

---

## Frontend Implementation Tips

1. **Token Storage:**
   - Store access and refresh tokens securely (HttpOnly cookies or secure storage)
   - Do not expose tokens in logs or console

2. **Token Refresh Logic:**
   - Check token expiration before making requests
   - Automatically refresh tokens when access token expires
   - If refresh token is also expired, redirect to login

3. **Password Reset Flow:**
   - Extract `uid` and `token` from the reset link URL
   - Validate both before showing the password reset form
   - Send them in the reset-password request

4. **Error Handling:**
   - Display user-friendly error messages from the response
   - Handle network errors gracefully
   - Implement retry logic for temporary failures

5. **Verification Code:**
   - Code is valid for 10 minutes
   - Users can resend every 60 seconds
   - Code format: exactly 6 digits

6. **Login Security:**
   - Account locks after 5 failed login attempts
   - Lock duration: 15 minutes
   - Clear lock when user logs in successfully

---

## Example Frontend Integration Flow

### Registration and Email Verification
1. User enters full_name, email, password
2. Call `POST /register/` → Get email confirmation message
3. User receives 6-digit code via email
4. Call `POST /verify-email/` with email and code
5. Redirect to login

### Login Flow
1. User enters email and password
2. Call `POST /login/` → Get access, refresh tokens and user info
3. Store tokens securely
4. Redirect to dashboard

### Accessing Protected Resources
1. Get current user: `GET /me/` with Authorization header
2. Call other authenticated endpoints with access token

### Token Refresh
1. Before each request, check if access token is expired
2. If expired, call `POST /token/refresh/` with refresh token
3. Update stored tokens with new ones
4. Retry original request

### Password Reset
1. User requests password reset: `POST /forgot-password/`
2. User clicks link in email (contains uid and token)
3. Extract uid and token from URL
4. Call `POST /reset-password/` with uid, token, and new_password
