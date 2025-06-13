# Univention Managment Console security concepts
An overview about the security concept realization of Univention Management Console, and other components affected by it, like the Univention Portal.
This provides answers for some topics for the BSI-Grundschutz compliance.

## Content-Security-Policy
The `Content-Security-Policy` response header is set by default and its values are configurable via various UCR variables.
The default settings only allow the minimum required rights for the Dojo-based frontend to work and all UMC modules functionality.

This header is a central defense mechanism against cross-site scripting (XSS), data injection, and clickjacking attacks.
It defines an explicit whitelist of trusted sources for scripts, stylesheets, fonts, images, and other resources.
By reducing the browser's ability to load or execute content from untrusted origins, CSP greatly limits the potential impact of compromised third-party components or improperly escaped user input.

## X-Frame-Options
The `X-Frame-Options` response header is not set anymore, as it conflicts with our settings in `Content-Security-Policy`.
All Frame settings for modern and supported browsers are done via the `Content-Security-Policy`.

Previously, this header was used to control whether a page can be embedded in a <frame>, <iframe>, or <object> element.
This protects against clickjacking attacks, where malicious pages trick users into clicking hidden UI elements.
Although it is deprecated in favor of the CSP frame-ancestors directive, the protection goal remains the same: to ensure that the application UI is not silently embedded into foreign contexts.

## HTTPS only, Host header, HSTS
By default UCS allows requests to various Host headers and using `http` and `https`.
The usage of `https`-only can be activated via the UCR variable `apache2/force\_https`, which enables HTTP Strict Transport Security (HSTS).

## Referer check
All request are checked that their `Referer` request headers starts with `/univention/`.
This ensures that no vulnerability in third-party components like Appcenter Apps can do requests against UMC components.

## Cookies
The session cookie `UMCSessionId` (regardless of the login methods plain, SAML or OIDC) use a truly random value using Pythons `uuid.uuid4()`.
Cookie expiration is set for 5 years in the future, except if the UCR variable `umc/http/enforce-session-cookie` makes them a "Session cookie".
All cookies are restricted to the path `/univention/`.
The UCR variable `umc/http/enforce-secure-cookie` configures cookies to set the `secure` flag.
The `SameSite` flag is by default unset, but can be set to `Strict/Lax/None` by configuring the UCR variable `umc/http/cookie/samesite`.
The `HttpOnly` flag is not set, as it is required to be read by the Javascript frontend (see paragraphs below for details).

Correct cookie attributes are critical to session protection.
The `Secure` flag ensures cookies are not transmitted over unencrypted connections, preventing session hijacking on open networks.
The `SameSite` flag helps protect against cross-site request forgery (CSRF) by limiting how cookies are sent in cross-origin requests.
Although `HttpOnly` is not enabled in this case, compensating controls like IP binding and XSRF tokens are in place.

## Sessions are bound to IP address
The sessions are bound to IP addresses, so a stolen session ID cannot be used by the attacker.
The IP is obtained by the request IP, and in case the request goes through our Apache reverse gateway (which is always the case), it is received from the first value in Apaches `X-Forwarded-For` request header.

## XSRF-Protection and Clickjacking protection
The Session cookie `UMCSessionId` does not have the `HttpOnly` flag set, as our Javascript framework is reading the cookie to add it as request header `X-Xsrf-Protection` to all XHR requests.
That prevents native browser elements like HTML forms, HTML references in `<img src="…">` or `<iframe src="…">`, HTTP redirections or just `<a href="">` links clicked by an victim to make requests to UMC.
This mechanism, in addition with the Referer check and the Session bound to IP address proves that the request comes from our Javascript applications.
Only a XSS vulnerability in our Javascript code, which allows attackers to insert Javascript code, could circument this.
Enabling the `HttpOnly` cookie flag would break this mechanism and wouldn't help any security, as the attacker then can just do arbitrary requests in the name of the logged in user (like resetting admin passwords), from anywhere in the domain.

## XSS-Protection
The only real protection against XSS attacks is proper encoding of HTML output.
We are doing this in all places.
If one place is vulnerable, the `Content-Security-Policy` and Session-to-IP-binding will prevent some damage.

Cross-Site Scripting (XSS) is one of the most critical vulnerabilities in web applications.
While HTTP headers like X-XSS-Protection provide a basic browser-side filter (primarily for legacy clients), the core defense is always proper server-side output encoding in all HTML contexts (element content, attributes, JavaScript).
This ensures that user-supplied input cannot be interpreted as executable code, even if it is injected.
Additionally, by combining CSP, IP-bound sessions, and XSRF tokens, the damage potential of a successful injection is significantly reduced.

## HTTP method
The HTTP request method is validated, depending on the endpoint only `GET` (`HEAD`), `POST`, `PUT`, `DELETE` is allowed.
Endpoints with `GET` requests never have side effects (the method is considered `safe`).
Operations with `PUT` and `DELETE` are designed to be idempotent.

Validating HTTP methods is a fundamental part of input validation and helps prevent logic manipulation or unexpected state changes caused by inappropriate or spoofed request types.
By enforcing a clear distinction between read-only (GET) and state-changing operations (POST, PUT, DELETE), the application ensures that side effects cannot be triggered via harmless-looking links or prefetch mechanisms.

## Cache-Control
Security relevant locations, like the backend URLs, set `Cache-Control "no-cache, private' and no `Expires` header via the Apache configuration.
Other static content like HTML, Javascript, CSS, fonts, JPEG, PNG images, files set a expiration time and various `Cache-Control` values like "no-cache, public'.

Proper cache control helps avoid unintended information disclosure and stale data attacks.
Sensitive endpoints should never be cached in shared or public caches, as this might expose session data, credentials, or configuration information to unauthorized users.
Conversely, public static assets benefit from cacheability for performance reasons, as long as they don’t include sensitive content.

## Content-Type
All responses set the correct `Content-Type` response header, e.g. `application/json`, `text/html`.
This ensures, that no attack against any endpoint can force browsers into sniffing/guessing the content type based on the response payload.
All requested `Content-Type` headers are validated to allow only None, `application/json`, `application/x-www-form-urlencoded` and `multipart/form-data`.

Setting the correct Content-Type is essential for robust input validation and output handling.
Without it, browsers might try to guess the content type (so-called MIME sniffing), which can lead to security issues such as script execution in contexts where only text was expected.
Coupled with `X-Content-Type-Options: nosniff`, this ensures a consistent and secure interpretation of data.

## X-Content-Type-Options
The response header `X-Content-Type-Options` is set to `nosniff`.

This header prevents browsers from MIME-sniffing the content type of a response, forcing them to respect the declared Content-Type.
This is important to prevent attacks where a file (e.g. uploaded by a user) is interpreted as a different type, such as interpreting a .txt file as HTML or JavaScript.
By enforcing nosniff, the application mitigates the risk of content-type confusion, which can lead to code injection or XSS, particularly in combination with improperly handled user-uploaded files.

## X-XSS-Protection
The response header `X-XSS-Protection` is set to `1; mode=block`.

This header activates the built-in Cross-Site Scripting (XSS) filters in older browsers (mostly legacy versions of Internet Explorer and some Chromium-based ones).
The mode=block directive ensures that, when a potential XSS attack is detected, the page is completely blocked rather than being rendered with sanitized content.
While modern browsers rely on Content-Security-Policy (CSP) instead, this header provides an additional fallback layer for older clients.
It helps defend against reflected XSS attacks caused by injecting malicious input into web pages.

## X-Permitted-Cross-Domain-Policies
The response header `X-Permitted-Cross-Domain-Policies` is set to `master-only`.

This header instructs clients, especially Adobe Flash and other legacy plugins, to only load cross-domain policies from the master policy file (e.g., /crossdomain.xml).
By setting it to master-only, we prevent such clients from making potentially unsafe cross-domain data requests unless explicitly permitted in a centralized way.
This reduces the risk of data exfiltration through improperly configured cross-domain policies and aligns with the principle of minimizing the attack surface.

## Information disclosure
* `/univention/get/meta` and /univention/meta.json` reveal some information about the domain. The information are pretty useless for attackers, as they can be obtained in other ways anyway (e.g. via DNS).
* By default stack traces are shown on 500 Internal Server Errors. They don't contain secret information, as we have open source software. You could by analyzing the source code lines find out which UCS version is in use. But this can also just be deduced by analyzing the public HTML/Javascript/whatever files. To disable the displaying of stack traces the UCR variable `umc/http/show_tracebacks` can be set to False. But this also prevents that we can receive valuable user feedback about real product errors.

## Authentication and Authorization
UMC allows authentication via:
* HTTP Basic WWW-Authentication via the `Authorization` HTTP request header
* HTML form based plaintext credentials authentication
* SAML Single Sign-On
* OpenID Connect authentication
* HTTP Bearer WWW-Authentication with an OAuth 2.0 Access Token

Details for Authentication and Authorization can be found in [README.md](README.md).

### Brude force prevention
All above authentication methods go through the PAM stack `univention-management-console`.
PAM faillock can be configured as brute force prevention via the UCR variables `auth/faillog`, `auth/faillog/*`.

### OAuth 2.0 / OpenID Connect
See [README.md](README.md) for details about OpenID Connect realization and security mechanisms.

## Cookie banner
A cookie banner can be configured to be shown via the UCR variables `umc/cookie-banner/.*`.
